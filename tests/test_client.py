# tests/test_client.py

import pytest
from unittest import mock # For mocking requests
import requests # Need this to mock its methods and exceptions
import json # For JSONDecodeError simulation if needed (though requests.exceptions handles it)

# --- Corrected Imports ---
# Import directly from the client module where they are defined
from freerouting.client import (
    FreeroutingClient,
    FreeroutingError,
    FreeroutingAPIError,
    FreeroutingAuthError
)


# --- Fixtures ---

@pytest.fixture
def api_key():
    """Provides a dummy API key for tests."""
    return "test_api_key_123"

@pytest.fixture
def client(api_key):
    """Provides a FreeroutingClient instance for tests."""
    # Using a non-standard base_url ensures we definitely don't hit the real API
    return FreeroutingClient(api_key=api_key, base_url="http://test.invalid")

# --- Test Cases ---

def test_client_initialization(client, api_key):
    """Test if the client initializes correctly with mandatory args."""
    assert client.api_key == api_key
    assert client.base_url == "http://test.invalid/v1" # Default version is v1
    assert client.session_id is None
    assert isinstance(client.profile_id, str)

def test_client_initialization_custom_params(api_key):
    """Test client initialization with custom parameters."""
    client = FreeroutingClient(
        api_key=api_key,
        base_url="http://localhost:8080",
        version="dev",
        profile_id="custom-profile-id",
        host_name="pytest-runner/1.0"
    )
    assert client.base_url == "http://localhost:8080/dev"
    assert client.profile_id == "custom-profile-id"
    assert client.host_name == "pytest-runner/1.0"

def test_client_initialization_no_api_key():
    """Test that ValueError is raised if no API key is provided."""
    with pytest.raises(ValueError, match="API key must be provided"):
        FreeroutingClient(api_key="")


# --- Mocking API Calls ---

@mock.patch('requests.get') # Patch where it's used by the client
def test_get_system_status_success(mock_get, client):
    """Test a successful GET request (e.g., get_system_status)."""
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "OK", "message": "Service is running"}
    mock_get.return_value = mock_response

    status = client.get_system_status()

    assert status == {"status": "OK", "message": "Service is running"}
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "http://test.invalid/v1/system/status"
    assert "Authorization" in kwargs['headers']
    assert kwargs['headers']['Authorization'] == f"Bearer {client.api_key}"

@mock.patch('requests.post')
def test_create_session_success(mock_post, client):
    """Test a successful POST request (e.g., create_session)."""
    session_id = "session-xyz-789"
    mock_response = mock.Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": session_id, "status": "created"}
    mock_post.return_value = mock_response

    session_details = client.create_session()

    assert session_details == {"id": session_id, "status": "created"}
    assert client.session_id == session_id
    mock_post.assert_called_once_with(
        "http://test.invalid/v1/sessions/create",
        headers=client._get_headers(),
        data=None # No data payload expected for this call
    )

@mock.patch('requests.put')
def test_start_job_success(mock_put, client):
    """Test a successful PUT request returning 202 Accepted (e.g., start_job)."""
    job_id = "job-abc-123"
    mock_response = mock.Mock()
    mock_response.status_code = 202
    mock_response.content = b'' # Simulate empty response body for 202
    # Make .json() raise an error if called, as per client._make_request handling
    mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "doc", 0)
    mock_put.return_value = mock_response

    result = client.start_job(job_id)

    assert result == {} # Expect empty dict for 202 with no body
    mock_put.assert_called_once_with(
        f"http://test.invalid/v1/jobs/{job_id}/start",
        headers=client._get_headers(),
        data=None
    )

@mock.patch('requests.get')
def test_make_request_api_error(mock_get, client):
    """Test handling of a non-2xx API error response (e.g., 404)."""
    mock_response = mock.Mock()
    mock_response.status_code = 404
    mock_response.text = "Resource Not Found"
    mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "doc", 0)
    mock_get.return_value = mock_response

    with pytest.raises(FreeroutingAPIError) as excinfo:
        client.get_system_status() # Any method using _make_request with GET

    assert excinfo.value.status_code == 404
    assert "Resource Not Found" in str(excinfo.value)
    assert "API request failed: 404" in str(excinfo.value)

@mock.patch('requests.get')
def test_make_request_auth_error(mock_get, client):
    """Test handling of a 401 Unauthorized error."""
    mock_response = mock.Mock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials provided"
    mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "doc", 0)
    mock_get.return_value = mock_response

    with pytest.raises(FreeroutingAuthError) as excinfo:
        client.get_system_status()

    assert "Authentication failed: 401" in str(excinfo.value)
    assert "Invalid credentials provided" in str(excinfo.value)


def test_get_session_no_id_error(client):
    """Test that get_session raises ValueError if no session ID is available."""
    client.session_id = None
    with pytest.raises(ValueError, match="No session ID provided or stored internally"):
        client.get_session()

def test_enqueue_job_no_id_error(client):
    """Test that enqueue_job raises ValueError if no session ID is available."""
    client.session_id = None
    with pytest.raises(ValueError, match="No session ID provided or stored internally"):
        client.enqueue_job(name="test_job")

# --- Value Error tests for missing IDs ---
def test_get_job_no_id(client):
    """Test ValueError if job_id is empty string for get_job."""
    with pytest.raises(ValueError, match="Job ID must be provided"):
        client.get_job(job_id="")

def test_start_job_no_id(client):
    """Test ValueError if job_id is empty string for start_job."""
    with pytest.raises(ValueError, match="Job ID must be provided"):
        client.start_job(job_id="")

def test_upload_input_no_params(client):
    """Test ValueErrors for missing parameters in upload_input."""
    with pytest.raises(ValueError, match="Job ID must be provided"):
        client.upload_input(job_id="", filename="f", file_path="p")
    with pytest.raises(ValueError, match="Filename must be provided"):
        client.upload_input(job_id="j", filename="", file_path="p")
    with pytest.raises(ValueError, match="File path must be provided"):
        client.upload_input(job_id="j", filename="f", file_path="")


# --- TODO: Add more tests! ---
# - Test methods like upload_input with file mocking (e.g., using mock_open)
# - Test download_output (mocking GET and checking file write if path provided)
# - Test run_routing_job workflow (requires more complex mocking of multiple steps)
# - Test network errors (patch requests.get/post/put to raise requests.exceptions.RequestException)