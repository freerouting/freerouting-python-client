import base64
import json
import os
import time
import uuid
from typing import Any, Dict, Generator, Iterator, List, Optional, Union

import requests

from . import __version__

# --- Custom Exception Classes ---


class FreeroutingError(Exception):
    """Base class for Freerouting client errors."""

    pass


class FreeroutingAPIError(FreeroutingError):
    """Raised for API-level errors (e.g., bad request, server error)."""

    def __init__(self, status_code, response_text):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"API request failed: {status_code} - {response_text}")


class FreeroutingAuthError(FreeroutingError):
    """Raised for authentication errors (e.g., invalid API key)."""

    pass


def _parse_sse_events(lines: Iterator[str]) -> Generator[Dict[str, Any], None, None]:
    """Parse Server-Sent Events lines and yield decoded JSON payloads."""
    data_lines: List[str] = []
    for line in lines:
        if line is None:
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "" and data_lines:
            payload = "\n".join(data_lines)
            data_lines = []
            if not payload:
                continue
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                yield {"raw": payload}
    if data_lines:
        payload = "\n".join(data_lines)
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            yield {"raw": payload}


# --- Client Class ---


class FreeroutingClient:
    """Client library for the Freerouting API."""

    DEFAULT_HOST_NAME = f"FreeroutingPythonClient/{__version__}"
    TERMINAL_JOB_STATES = frozenset({"COMPLETED", "CANCELLED", "FAILED", "TERMINATED", "TIMED_OUT", "INVALID"})

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.freerouting.app",
        version: str = "v1",
        profile_id: Optional[str] = None,
        host_name: Optional[str] = None,
        timeout: int = 120,
    ):
        """
        Initialize the Freerouting API client.

        Args:
            api_key: Freerouting API key. Optional for local servers with authentication disabled.
            base_url: API host without the version suffix (default: https://api.freerouting.app).
            version: API version to use (default: v1). Use "dev" for mocked integration testing.
            profile_id: Optional profile ID (UUID). A new one is generated if None.
            host_name: Caller identity in ``<ToolName>/<Version>`` format (required by the API).
            timeout: Default HTTP request timeout in seconds.
        """
        self.api_key = api_key
        self.base_url = f"{base_url.rstrip('/')}/{version.lstrip('/')}"
        self.profile_id = profile_id or str(uuid.uuid4())
        self.host_name = host_name or self.DEFAULT_HOST_NAME
        self.timeout = timeout
        self.session_id: Optional[str] = None

    def _get_headers(self, *, accept: str = "application/json", include_content_type: bool = True) -> Dict[str, str]:
        """Get the headers for API requests."""
        headers = {
            "Freerouting-Profile-ID": self.profile_id,
            "Freerouting-Environment-Host": self.host_name,
            "Accept": accept,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Union[Dict[str, Any], str]] = None,
        *,
        raw_body: bool = False,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Make an API request and handle the response."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        response = None
        request_timeout = self.timeout if timeout is None else timeout

        body = None
        if data is not None:
            body = data if raw_body else json.dumps(data)

        try:
            method_upper = method.upper()
            if method_upper == "GET":
                response = requests.get(url, headers=headers, timeout=request_timeout)
            elif method_upper == "POST":
                response = requests.post(url, headers=headers, data=body, timeout=request_timeout)
            elif method_upper == "PUT":
                response = requests.put(url, headers=headers, data=body, timeout=request_timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code in (401, 403):
                raise FreeroutingAuthError(f"Authentication failed: {response.status_code} - {response.text}")
            if response.status_code not in (200, 201, 202, 204):
                raise FreeroutingAPIError(response.status_code, response.text)

            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

        except requests.exceptions.RequestException as e:
            raise FreeroutingError(f"Network error during API request to {url}: {e}") from e
        except json.JSONDecodeError as e:
            raise FreeroutingAPIError(
                response.status_code if response else "N/A",
                f"Failed to decode JSON response: {e} - Response text: {response.text if response else 'N/A'}",
            ) from e

    def _stream_sse(self, endpoint: str, *, timeout: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
        """Open an SSE stream and yield decoded JSON event payloads."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(accept="text/event-stream", include_content_type=False)
        request_timeout = self.timeout if timeout is None else timeout

        try:
            with requests.get(url, headers=headers, stream=True, timeout=request_timeout) as response:
                if response.status_code in (401, 403):
                    raise FreeroutingAuthError(f"Authentication failed: {response.status_code} - {response.text}")
                if response.status_code != 200:
                    raise FreeroutingAPIError(response.status_code, response.text)

                yield from _parse_sse_events(response.iter_lines(decode_unicode=True))
        except requests.exceptions.RequestException as e:
            raise FreeroutingError(f"Network error during SSE request to {url}: {e}") from e

    def _resolve_session_id(self, session_id: Optional[str]) -> str:
        target_session_id = session_id or self.session_id
        if not target_session_id:
            raise ValueError("No session ID provided or stored internally by create_session().")
        return target_session_id

    # --- System Endpoints ---

    def get_system_status(self) -> Dict[str, Any]:
        """Get the current status of the Freerouting service."""
        return self._make_request("GET", "/system/status")

    def get_environment(self) -> Dict[str, Any]:
        """Get information about the system environment."""
        return self._make_request("GET", "/system/environment")

    # --- Session Endpoints ---

    def create_session(self) -> Dict[str, Any]:
        """Create a new session and store the session ID internally."""
        result = self._make_request("POST", "/sessions/create")
        self.session_id = result.get("id")
        return result

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all available sessions for the current profile ID."""
        return self._make_request("GET", "/sessions/list")

    def get_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get details for a specific session."""
        target_session_id = self._resolve_session_id(session_id)
        return self._make_request("GET", f"/sessions/{target_session_id}")

    def get_session_logs(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get logs for a specific session."""
        target_session_id = self._resolve_session_id(session_id)
        return self._make_request("GET", f"/sessions/{target_session_id}/logs")

    def monitor_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Bind a session to the running GUI visualizer for live routing display."""
        target_session_id = self._resolve_session_id(session_id)
        return self._make_request("PUT", f"/sessions/{target_session_id}/monitor")

    # --- Job Endpoints ---

    def enqueue_job(self, name: str, priority: str = "NORMAL", session_id: Optional[str] = None) -> Dict[str, Any]:
        """Enqueue a new routing job within a specific session."""
        target_session_id = self._resolve_session_id(session_id)
        data = {
            "session_id": target_session_id,
            "name": name,
            "priority": priority,
        }
        return self._make_request("POST", "/jobs/enqueue", data)

    def list_jobs(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List jobs for a session. Pass session_id='all' to list every job for this profile."""
        target_session_id = self._resolve_session_id(session_id)
        return self._make_request("GET", f"/jobs/list/{target_session_id}")

    def list_all_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs belonging to the current profile, regardless of session."""
        return self._make_request("GET", "/jobs/list/all")

    def get_job(self, job_id: str, *, compact: bool = False) -> Dict[str, Any]:
        """
        Get details for a specific job by its ID.

        Args:
            job_id: The unique identifier of the job.
            compact: When True, returns a compact, token-efficient summary.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        endpoint = f"/jobs/{job_id}?compact=true" if compact else f"/jobs/{job_id}"
        return self._make_request("GET", endpoint)

    def get_effective_settings(self, job_id: str) -> Dict[str, Any]:
        """
        Get effective merged router settings for a job.

        Resolves all configuration layers (defaults, DSN, rules, CLI, and API overrides),
        board-specific optimizations, and preflight validation warnings.

        Args:
            job_id: The unique identifier of the job.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}/settings")

    def update_job_settings(self, job_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update settings for a specific job while it is still queued."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("POST", f"/jobs/{job_id}/settings", settings)

    def start_job(self, job_id: str) -> Dict[str, Any]:
        """Start processing a job."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("PUT", f"/jobs/{job_id}/start")

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a job that is in progress or pending."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("PUT", f"/jobs/{job_id}/cancel")

    def upload_input(self, job_id: str, filename: str, file_path: str) -> Dict[str, Any]:
        """Upload a Specctra DSN input file for a job."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        if not filename:
            raise ValueError("Filename must be provided.")
        if not file_path:
            raise ValueError("File path must be provided.")

        try:
            with open(file_path, "rb") as file_handle:
                file_data = file_handle.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Input file not found at: {file_path}") from None
        except OSError as e:
            raise OSError(f"Could not read input file at {file_path}: {e}") from e

        data = {
            "filename": filename,
            "data": base64.b64encode(file_data).decode("utf-8"),
        }
        return self._make_request("POST", f"/jobs/{job_id}/input", data)

    def upload_input_json(
        self,
        job_id: str,
        board_json: Union[Dict[str, Any], str],
        *,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload KiCad JSON board data for a job (raw JSON, not Base64-encoded)."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        if board_json is None or board_json == "" or board_json == {}:
            raise ValueError("Board JSON must be provided.")

        if isinstance(board_json, dict):
            payload = json.dumps(board_json)
        else:
            payload = board_json

        url = f"{self.base_url}/jobs/{job_id}/input/json"
        headers = self._get_headers()
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        try:
            response = requests.post(url, headers=headers, data=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise FreeroutingError(f"Network error during API request to {url}: {e}") from e

        if response.status_code in (401, 403):
            raise FreeroutingAuthError(f"Authentication failed: {response.status_code} - {response.text}")
        if response.status_code not in (200, 201, 202, 204):
            raise FreeroutingAPIError(response.status_code, response.text)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def upload_rules(self, job_id: str, filename: str, file_path: str) -> Dict[str, Any]:
        """
        Upload a Specctra design rules (.rules) file for a job.

        Args:
            job_id: Unique identifier of the job.
            filename: Name of the rules file (e.g., "design.rules").
            file_path: Path to the local .rules file.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        if not filename:
            raise ValueError("Filename must be provided.")
        if not file_path:
            raise ValueError("File path must be provided.")

        try:
            with open(file_path, "rb") as file_handle:
                file_data = file_handle.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Rules file not found at: {file_path}") from None
        except OSError as e:
            raise OSError(f"Could not read rules file at {file_path}: {e}") from e

        data = {
            "filename": filename,
            "data": base64.b64encode(file_data).decode("utf-8"),
        }
        return self._make_request("POST", f"/jobs/{job_id}/rules", data)

    def download_output(self, job_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Download Specctra SES output from a job."""
        if not job_id:
            raise ValueError("Job ID must be provided.")

        result = self._make_request("GET", f"/jobs/{job_id}/output")

        if output_path and result.get("data"):
            self._write_base64_file(result["data"], output_path)

        return result

    def download_output_json(self, job_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Download KiCad JSON output from a job."""
        if not job_id:
            raise ValueError("Job ID must be provided.")

        result = self._make_request("GET", f"/jobs/{job_id}/output/json")

        if output_path:
            with open(output_path, "w", encoding="utf-8") as file_handle:
                json.dump(result, file_handle, indent=2)

        return result

    def get_job_drc(self, job_id: str, *, compact: bool = False) -> Dict[str, Any]:
        """
        Get a KiCad-compatible DRC report for a job.

        Args:
            job_id: Unique identifier of the job.
            compact: When True, returns a compact token-saving DRC report summary.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        endpoint = f"/jobs/{job_id}/drc?compact=true" if compact else f"/jobs/{job_id}/drc"
        return self._make_request("GET", endpoint)

    def get_job_drc_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Get a structured DRC diagnostic summary for a job.

        Clusters violations into spatial congestion hotspots and offers layout auto-correction hints.

        Args:
            job_id: Unique identifier of the job.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}/drc/summary")

    def get_job_logs(self, job_id: str) -> List[Dict[str, Any]]:
        """Get logs for a specific job."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}/logs")

    def stream_job_logs(self, job_id: str) -> Generator[Dict[str, Any], None, None]:
        """Stream job log entries over Server-Sent Events."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        yield from self._stream_sse(f"/jobs/{job_id}/logs/stream")

    def stream_job_output(self, job_id: str) -> Generator[Dict[str, Any], None, None]:
        """Stream updated SES output payloads over Server-Sent Events."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        yield from self._stream_sse(f"/jobs/{job_id}/output/stream")

    def stream_job_output_json(self, job_id: str) -> Generator[Dict[str, Any], None, None]:
        """Stream updated KiCad JSON output payloads over Server-Sent Events."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        yield from self._stream_sse(f"/jobs/{job_id}/output/json/stream")

    @staticmethod
    def _write_base64_file(encoded_data: str, output_path: str) -> None:
        try:
            decoded_data = base64.b64decode(encoded_data)
            with open(output_path, "wb") as file_handle:
                file_handle.write(decoded_data)
        except OSError as e:
            raise OSError(f"Could not write output file to {output_path}: {e}") from e
        except (TypeError, base64.binascii.Error) as e:
            raise ValueError(f"Failed to decode base64 data from API response: {e}") from e

    # --- Single-Turn Composite Autoroute ---

    def autoroute(
        self,
        file_content: Optional[str] = None,
        *,
        dsn_file_path: Optional[str] = None,
        rules_content: Optional[str] = None,
        rules_file_path: Optional[str] = None,
        session_content: Optional[str] = None,
        session_file_path: Optional[str] = None,
        router_settings: Optional[Dict[str, Any]] = None,
        drc_settings: Optional[Dict[str, Any]] = None,
        output_formats: Optional[List[str]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Perform single-turn composite autorouting (POST /v1/autoroute).

        Executes the entire routing pipeline synchronously in a single HTTP turn.
        Accepts multi-file inputs (primary design .dsn or .json, optional .rules,
        optional initial .ses or .json), executes routing within the requested
        timeout budget, and returns all requested output representations (SES,
        KICAD_JSON, SCR, DRC_JSON, DRC_SUMMARY) and metrics in a single response.

        Args:
            file_content: Raw text content of the primary design (.dsn or KiCad .json).
            dsn_file_path: Local file path to read primary design from if file_content is not passed.
            rules_content: Optional raw text content of Specctra design rules (.rules).
            rules_file_path: Optional local path to read design rules from if rules_content is not passed.
            session_content: Optional raw text content of initial session (.ses or KiCad .json).
            session_file_path: Optional local path to read session from if session_content is not passed.
            router_settings: Optional router settings configuration overrides.
            drc_settings: Optional design rule checker settings configuration.
            output_formats: Desired output formats: 'SES', 'KICAD_JSON', 'SCR', 'DRC_JSON', 'DRC_SUMMARY'. Defaults to ['SES'].
            timeout_seconds: Maximum execution budget in seconds (default: 300).
        """
        design_text = file_content
        if design_text is None and dsn_file_path is not None:
            try:
                with open(dsn_file_path, "r", encoding="utf-8") as f:
                    design_text = f.read()
            except UnicodeDecodeError:
                with open(dsn_file_path, "rb") as f:
                    design_text = f.read().decode("latin-1")
            except OSError as e:
                raise OSError(f"Could not read primary design file at {dsn_file_path}: {e}") from e

        if design_text is None or not str(design_text).strip():
            raise ValueError("Primary design content must be provided via 'file_content' or 'dsn_file_path'.")

        rules_text = rules_content
        if rules_text is None and rules_file_path is not None:
            try:
                with open(rules_file_path, "r", encoding="utf-8") as f:
                    rules_text = f.read()
            except UnicodeDecodeError:
                with open(rules_file_path, "rb") as f:
                    rules_text = f.read().decode("latin-1")
            except OSError as e:
                raise OSError(f"Could not read rules file at {rules_file_path}: {e}") from e

        session_text = session_content
        if session_text is None and session_file_path is not None:
            try:
                with open(session_file_path, "r", encoding="utf-8") as f:
                    session_text = f.read()
            except UnicodeDecodeError:
                with open(session_file_path, "rb") as f:
                    session_text = f.read().decode("latin-1")
            except OSError as e:
                raise OSError(f"Could not read session file at {session_file_path}: {e}") from e

        payload: Dict[str, Any] = {
            "file_content": design_text,
        }
        if rules_text is not None:
            payload["rules_content"] = rules_text
        if session_text is not None:
            payload["session_content"] = session_text
        if router_settings is not None:
            payload["router_settings"] = router_settings
        if drc_settings is not None:
            payload["drc_settings"] = drc_settings
        if output_formats is not None:
            payload["output_formats"] = output_formats
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds

        http_timeout = (timeout_seconds + 30) if timeout_seconds is not None else max(self.timeout, 330)
        return self._make_request("POST", "/autoroute", data=payload, timeout=http_timeout)

    # --- Analytics Endpoints ---

    def track_user_action(
        self,
        event: str,
        properties: Optional[Dict[str, Any]] = None,
        *,
        user_id: Optional[str] = None,
        anonymous_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record an analytics event in BigQuery.

        Args:
            event: Event name (e.g. "job_started", "autoroute_completed").
            properties: Optional dictionary of event properties.
            user_id: Optional user identifier (defaults to profile_id).
            anonymous_id: Optional anonymous identifier.
        """
        if not event:
            raise ValueError("Event name must be provided.")
        payload: Dict[str, Any] = {
            "event": event,
            "properties": properties or {},
            "userId": user_id or self.profile_id,
        }
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        return self._make_request("POST", "/analytics/track", data=payload)

    def identify_user(
        self,
        traits: Dict[str, Any],
        *,
        user_id: Optional[str] = None,
        anonymous_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Associate user traits with an identity for analytics purposes.

        Args:
            traits: Dictionary of user traits (e.g. client_version, os_name, allow_telemetry).
            user_id: Optional user identifier (defaults to profile_id).
            anonymous_id: Optional anonymous identifier.
        """
        if traits is None:
            raise ValueError("Traits dictionary must be provided.")
        payload: Dict[str, Any] = {
            "traits": traits,
            "userId": user_id or self.profile_id,
        }
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        return self._make_request("POST", "/analytics/identify", data=payload)

    # --- Workflow helpers ---

    def run_routing_job(
        self,
        name: str,
        dsn_file_path: str,
        settings: Optional[Dict[str, Any]] = None,
        rules_file_path: Optional[str] = None,
        poll_interval: int = 5,
        timeout: int = 3600,
        output_path: Optional[str] = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a complete DSN routing workflow: session, enqueue, upload, start, poll, download.

        Args:
            name: Name for the routing job.
            dsn_file_path: Path to the local DSN input file.
            settings: Optional router settings (for example ``{"max_passes": 5}``).
            poll_interval: Seconds between job status checks.
            timeout: Maximum seconds to wait for completion.
            output_path: Optional local path for the decoded SES output file.
            verbose: Print progress messages while the job runs.
        """
        if not name:
            raise ValueError("Job name must be provided.")
        if not dsn_file_path:
            raise ValueError("DSN file path must be provided.")
        if poll_interval <= 0:
            raise ValueError("Poll interval must be positive.")
        if timeout <= 0:
            raise ValueError("Timeout must be positive.")

        def log(message: str) -> None:
            if verbose:
                print(message)

        if not self.session_id:
            log("No active session found, creating a new one...")
            self.create_session()
            log(f"Using session ID: {self.session_id}")

        log(f"Enqueuing job '{name}'...")
        job = self.enqueue_job(name)
        job_id = job.get("id")
        if not job_id:
            raise FreeroutingError("Failed to get job ID after enqueueing.")
        log(f"Job enqueued with ID: {job_id}")

        filename = os.path.basename(dsn_file_path)
        log(f"Uploading input file '{filename}' from '{dsn_file_path}'...")
        self.upload_input(job_id, filename, dsn_file_path)
        log("Upload complete.")

        if rules_file_path:
            rules_filename = os.path.basename(rules_file_path)
            log(f"Uploading rules file '{rules_filename}' from '{rules_file_path}'...")
            self.upload_rules(job_id, rules_filename, rules_file_path)
            log("Rules upload complete.")

        if settings:
            log("Updating job settings...")
            self.update_job_settings(job_id, settings)
            log("Settings updated.")

        log("Starting job processing...")
        self.start_job(job_id)
        log("Job started.")

        log(f"Polling job status every {poll_interval} seconds (timeout: {timeout}s)...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            job_status_response = self.get_job(job_id)
            job_state = job_status_response.get("state", "UNKNOWN")
            log(f"  Job state: {job_state} (Elapsed: {int(time.time() - start_time)}s)")

            if job_state == "COMPLETED":
                log("Job completed successfully!")
                if output_path:
                    return self.download_output(job_id, output_path)
                return self.download_output(job_id)

            if job_state in self.TERMINAL_JOB_STATES - {"COMPLETED"}:
                logs: List[Dict[str, Any]] = []
                try:
                    logs = self.get_job_logs(job_id)
                except Exception as log_error:
                    log(f"  Warning: Could not retrieve job logs: {log_error}")
                raise FreeroutingError(f"Job {job_id} ended with state: {job_state}. Logs: {logs}")

            time.sleep(poll_interval)

        raise TimeoutError(f"Job {job_id} did not complete within the {timeout} second timeout.")
