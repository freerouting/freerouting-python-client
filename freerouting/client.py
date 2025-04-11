import requests
import base64
import json
import time
import uuid
import os # Added for os.path.basename
from typing import Dict, Any, Optional, List, Union

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

# --- Client Class ---

class FreeroutingClient:
    """Client library for the Freerouting API."""

    def __init__(self, api_key: str, base_url: str = "https://api.freerouting.app", version: str = "v1",
                 profile_id: Optional[str] = None, host_name: str = "FreeroutingPythonClient/2.1.0"):
        """
        Initialize the Freerouting API client.

        Args:
            api_key: Your Freerouting API key.
            base_url: The base URL for the API (default: https://api.freerouting.app).
            version: API version to use (default: v1).
            profile_id: Optional profile ID (GUID). A new one is generated if None.
            host_name: Name and version of the software making API calls.
        """
        if not api_key:
            raise ValueError("API key must be provided.")
        self.api_key = api_key
        # Ensure no trailing slash on base_url and leading slash on version if present
        self.base_url = f"{base_url.rstrip('/')}/{version.lstrip('/')}"
        self.profile_id = profile_id or str(uuid.uuid4())
        self.host_name = host_name
        self.session_id = None # Stores the ID of the most recently created session

    def _get_headers(self) -> Dict[str, str]:
        """Get the headers for API requests."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Freerouting-Profile-ID": self.profile_id,
            "Freerouting-Environment-Host": self.host_name,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        return headers

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make an API request and handle response.

        Args:
            method: HTTP method (GET, POST, PUT).
            endpoint: API endpoint path (e.g., "/system/status").
            data: Optional dictionary for POST/PUT request body.

        Returns:
            The JSON response dictionary from the API.

        Raises:
            ValueError: If an unsupported HTTP method is provided.
            FreeroutingAuthError: If authentication fails (401 or 403 status).
            FreeroutingAPIError: For other non-successful API responses.
            requests.exceptions.RequestException: For network-level errors.
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        response = None

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, data=json.dumps(data) if data else None)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, data=json.dumps(data) if data else None)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Check for specific HTTP errors after the request
            if response.status_code in (401, 403):
                raise FreeroutingAuthError(f"Authentication failed: {response.status_code} - {response.text}")
            if response.status_code not in (200, 201, 202):
                 raise FreeroutingAPIError(response.status_code, response.text)

            # For successful responses that might return empty content (like 202 Accepted)
            if response.status_code == 202 and not response.content:
                return {} # Return empty dict or adjust as needed based on API spec

            return response.json()

        except requests.exceptions.RequestException as e:
            # Re-raise network errors for the user to handle
            raise FreeroutingError(f"Network error during API request to {url}: {e}") from e
        except json.JSONDecodeError as e:
             # Handle cases where the response is not valid JSON
            raise FreeroutingAPIError(response.status_code if response else 'N/A', f"Failed to decode JSON response: {e} - Response text: {response.text if response else 'N/A'}")


    # --- System Endpoints ---
    def get_system_status(self) -> Dict:
        """Get the current status of the Freerouting service.

        Returns:
            A dictionary containing the system status.

        Raises:
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        return self._make_request("GET", "/system/status")

    def get_environment(self) -> Dict:
        """Get information about the system environment.

        Returns:
            A dictionary containing environment information.

        Raises:
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        return self._make_request("GET", "/system/environment")

    # --- Session Endpoints ---
    def create_session(self) -> Dict:
        """Create a new session and store the session ID internally.

        Returns:
            A dictionary containing the new session details, including the ID.

        Raises:
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        result = self._make_request("POST", "/sessions/create")
        self.session_id = result.get("id") # Store the new session ID
        return result

    def list_sessions(self) -> List[Dict]:
        """List all available sessions for the current profile ID.

        Returns:
            A list of dictionaries, each representing a session.

        Raises:
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        return self._make_request("GET", "/sessions/list")

    def get_session(self, session_id: Optional[str] = None) -> Dict:
        """Get details for a specific session.

        Args:
            session_id: The ID of the session to retrieve. Uses the internally
                        stored session ID if None.

        Returns:
            A dictionary containing the session details.

        Raises:
            ValueError: If no session ID is provided or stored internally.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        target_session_id = session_id or self.session_id
        if not target_session_id:
            raise ValueError("No session ID provided or stored internally by create_session().")
        return self._make_request("GET", f"/sessions/{target_session_id}")

    def get_session_logs(self, session_id: Optional[str] = None) -> List[Dict]:
        """Get logs for a specific session.

        Args:
            session_id: The ID of the session for which to retrieve logs.
                        Uses the internally stored session ID if None.

        Returns:
            A list of dictionaries, each representing a log entry.

        Raises:
            ValueError: If no session ID is provided or stored internally.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        target_session_id = session_id or self.session_id
        if not target_session_id:
            raise ValueError("No session ID provided or stored internally by create_session().")
        return self._make_request("GET", f"/sessions/{target_session_id}/logs")

    # --- Job Endpoints ---
    def enqueue_job(self, name: str, priority: str = "NORMAL", session_id: Optional[str] = None) -> Dict:
        """Enqueue a new routing job within a specific session.

        Args:
            name: A user-defined name for the job.
            priority: Job priority ("LOW", "NORMAL", "HIGH"). Defaults to "NORMAL".
            session_id: The ID of the session to associate the job with.
                        Uses the internally stored session ID if None.

        Returns:
            A dictionary containing the details of the enqueued job, including its ID.

        Raises:
            ValueError: If no session ID is provided or stored internally.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        target_session_id = session_id or self.session_id
        if not target_session_id:
            raise ValueError("No session ID provided or stored internally by create_session().")

        data = {
            "session_id": target_session_id,
            "name": name,
            "priority": priority
        }
        return self._make_request("POST", "/jobs/enqueue", data)

    def list_jobs(self, session_id: Optional[str] = None) -> List[Dict]:
        """List all jobs for a specific session.

        Args:
            session_id: The ID of the session for which to list jobs.
                        Uses the internally stored session ID if None.

        Returns:
            A list of dictionaries, each representing a job in the session.

        Raises:
            ValueError: If no session ID is provided or stored internally.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        target_session_id = session_id or self.session_id
        if not target_session_id:
            raise ValueError("No session ID provided or stored internally by create_session().")
        return self._make_request("GET", f"/jobs/list/{target_session_id}")

    def get_job(self, job_id: str) -> Dict:
        """Get details for a specific job by its ID.

        Args:
            job_id: The unique ID of the job.

        Returns:
            A dictionary containing the job details.

        Raises:
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}")

    def update_job_settings(self, job_id: str, settings: Dict[str, Any]) -> Dict:
        """Update settings for a specific job.

        Args:
            job_id: The unique ID of the job.
            settings: A dictionary containing the settings to update.

        Returns:
            A dictionary confirming the update (structure may vary based on API).

        Raises:
            ValueError: If job_id is not provided.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("POST", f"/jobs/{job_id}/settings", settings)

    def start_job(self, job_id: str) -> Dict:
        """Start processing a job.

        Args:
            job_id: The unique ID of the job to start.

        Returns:
            A dictionary confirming the start action (structure may vary based on API, might be empty).

        Raises:
            ValueError: If job_id is not provided.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        # Expects 202 Accepted, potentially with empty body
        return self._make_request("PUT", f"/jobs/{job_id}/start")


    def cancel_job(self, job_id: str) -> Dict:
        """Cancel a job that is in progress or pending.

        Args:
            job_id: The unique ID of the job to cancel.

        Returns:
            A dictionary confirming the cancel action (structure may vary based on API, might be empty).

        Raises:
            ValueError: If job_id is not provided.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
         # Expects 202 Accepted, potentially with empty body
        return self._make_request("PUT", f"/jobs/{job_id}/cancel")

    def upload_input(self, job_id: str, filename: str, file_path: str) -> Dict:
        """Upload input file (e.g., DSN) for a job.

        Args:
            job_id: The unique ID of the job.
            filename: The desired filename on the server side.
            file_path: The local path to the file to upload.

        Returns:
            A dictionary confirming the upload (structure may vary based on API).

        Raises:
            ValueError: If job_id, filename, or file_path is not provided.
            FileNotFoundError: If the file at file_path does not exist.
            IOError: If the file cannot be read.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        if not filename:
            raise ValueError("Filename must be provided.")
        if not file_path:
            raise ValueError("File path must be provided.")

        try:
            with open(file_path, "rb") as f:
                file_data = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Input file not found at: {file_path}")
        except IOError as e:
            raise IOError(f"Could not read input file at {file_path}: {e}") from e

        data = {
            "filename": filename,
            "data": base64.b64encode(file_data).decode("utf-8") # Base64 encode binary data
        }
        return self._make_request("POST", f"/jobs/{job_id}/input", data)

    def download_output(self, job_id: str, output_path: Optional[str] = None) -> Dict:
        """Download output (e.g., SES file) from a completed job.

        If output_path is provided, the decoded data is written to that file path.

        Args:
            job_id: The unique ID of the completed job.
            output_path: Optional local file path to save the decoded output data.

        Returns:
            The dictionary result from the API, which should include 'filename'
            and base64 encoded 'data'.

        Raises:
            ValueError: If job_id is not provided.
            IOError: If output_path is provided but cannot be written to.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors (e.g., job not completed, output not found).
            FreeroutingError: For network errors.
            KeyError: If the response dictionary is missing 'data' when output_path is specified.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")

        result = self._make_request("GET", f"/jobs/{job_id}/output")

        if output_path:
            if "data" not in result:
                 raise KeyError("API response for download_output did not contain 'data' field needed to save file.")
            try:
                # Decode base64 data before writing
                decoded_data = base64.b64decode(result["data"])
                with open(output_path, "wb") as f:
                    f.write(decoded_data)
            except (IOError, OSError) as e:
                 raise IOError(f"Could not write output file to {output_path}: {e}") from e
            except (TypeError, base64.binascii.Error) as e:
                 raise ValueError(f"Failed to decode base64 data from API response: {e}") from e

        return result

    def get_job_logs(self, job_id: str) -> List[Dict]:
        """Get logs for a specific job.

        Args:
            job_id: The unique ID of the job.

        Returns:
            A list of dictionaries, each representing a log entry for the job.

        Raises:
            ValueError: If job_id is not provided.
            FreeroutingAuthError: If authentication fails.
            FreeroutingAPIError: For other API request errors.
            FreeroutingError: For network errors.
        """
        if not job_id:
            raise ValueError("Job ID must be provided.")
        return self._make_request("GET", f"/jobs/{job_id}/logs")

    # --- Workflow helpers ---
    def run_routing_job(self, name: str, dsn_file_path: str, settings: Optional[Dict] = None,
                        poll_interval: int = 5, timeout: int = 3600) -> Dict:
        """
        Run a complete routing job workflow: create session (if needed), enqueue job,
        upload DSN, update settings (optional), start job, poll for completion,
        and download the result.

        Args:
            name: Name for the routing job.
            dsn_file_path: Path to the local DSN input file.
            settings: Optional dictionary of router settings to apply.
            poll_interval: Time in seconds between job status checks (default: 5).
            timeout: Maximum time in seconds to wait for job completion (default: 3600).

        Returns:
            The output result dictionary from the API after job completion,
            typically containing filename and base64 encoded data of the SES file.

        Raises:
            ValueError: If name or dsn_file_path is not provided, or poll_interval/timeout invalid.
            FileNotFoundError: If the dsn_file_path does not exist.
            IOError: If the dsn_file_path cannot be read.
            TimeoutError: If the job does not complete within the specified timeout.
            FreeroutingError (and subclasses): For any API or network errors during the workflow.
        """
        if not name:
            raise ValueError("Job name must be provided.")
        if not dsn_file_path:
            raise ValueError("DSN file path must be provided.")
        if poll_interval <= 0:
             raise ValueError("Poll interval must be positive.")
        if timeout <= 0:
             raise ValueError("Timeout must be positive.")

        try:
            # 1. Ensure session exists
            if not self.session_id:
                print("No active session found, creating a new one...")
                self.create_session()
                print(f"Using session ID: {self.session_id}")

            # 2. Create job
            print(f"Enqueuing job '{name}'...")
            job = self.enqueue_job(name) # Uses self.session_id implicitly
            job_id = job.get("id")
            if not job_id:
                raise FreeroutingError("Failed to get job ID after enqueueing.")
            print(f"Job enqueued with ID: {job_id}")

            # 3. Upload input file (Using robust path handling)
            filename = os.path.basename(dsn_file_path)
            print(f"Uploading input file '{filename}' from '{dsn_file_path}'...")
            self.upload_input(job_id, filename, dsn_file_path)
            print("Upload complete.")

            # 4. Update settings if provided
            if settings:
                print("Updating job settings...")
                self.update_job_settings(job_id, settings)
                print("Settings updated.")

            # 5. Start the job
            print("Starting job processing...")
            self.start_job(job_id)
            print("Job started.")

            # 6. Poll for completion
            print(f"Polling job status every {poll_interval} seconds (timeout: {timeout}s)...")
            start_time = time.time()
            while time.time() - start_time < timeout:
                job_status_response = self.get_job(job_id)
                job_state = job_status_response.get("state", "UNKNOWN")
                print(f"  Job state: {job_state} (Elapsed: {int(time.time() - start_time)}s)")

                if job_state == "COMPLETED":
                    print("Job completed successfully!")
                    return self.download_output(job_id) # Return the download response
                elif job_state in ("CANCELLED", "FAILED"):
                    # Attempt to get logs for failed/cancelled jobs for more info
                    logs = []
                    try:
                        logs = self.get_job_logs(job_id)
                    except Exception as log_e:
                        print(f"  Warning: Could not retrieve job logs: {log_e}")
                    raise FreeroutingError(f"Job {job_id} ended with state: {job_state}. Logs: {logs}")

                time.sleep(poll_interval)

            # If loop finishes without completion
            raise TimeoutError(f"Job {job_id} did not complete within the {timeout} second timeout.")

        # Catch potential errors during the workflow
        except (FreeroutingError, ValueError, FileNotFoundError, IOError, TimeoutError) as e:
            # Re-raise the caught exception to the caller
            raise e
        except Exception as e:
            # Catch any unexpected errors
            raise FreeroutingError(f"An unexpected error occurred during run_routing_job: {e}") from e