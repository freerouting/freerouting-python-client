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

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get details for a specific job by its ID."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}")

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

    def get_job_drc(self, job_id: str) -> Dict[str, Any]:
        """Get a KiCad-compatible DRC report for a job."""
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}/drc")

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

    # --- Workflow helpers ---

    def run_routing_job(
        self,
        name: str,
        dsn_file_path: str,
        settings: Optional[Dict[str, Any]] = None,
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
