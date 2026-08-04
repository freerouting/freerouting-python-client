# tests/test_client.py

import json
from unittest import mock

import pytest
import requests

from freerouting import (
    FreeroutingClient,
    FreeroutingError,
    FreeroutingAPIError,
    FreeroutingAuthError,
    __version__,
)
from freerouting.client import _parse_sse_events


@pytest.fixture
def api_key():
    return "test_api_key_123"


@pytest.fixture
def client(api_key):
    return FreeroutingClient(api_key=api_key, base_url="http://test.invalid")


def test_package_version_matches_client_host_name():
    assert FreeroutingClient.DEFAULT_HOST_NAME == f"FreeroutingPythonClient/{__version__}"


def test_client_initialization(client, api_key):
    assert client.api_key == api_key
    assert client.base_url == "http://test.invalid/v1"
    assert client.session_id is None
    assert isinstance(client.profile_id, str)
    assert client.host_name == f"FreeroutingPythonClient/{__version__}"


def test_client_initialization_custom_params(api_key):
    client = FreeroutingClient(
        api_key=api_key,
        base_url="http://localhost:8080",
        version="dev",
        profile_id="custom-profile-id",
        host_name="pytest-runner/1.0",
        timeout=30,
    )
    assert client.base_url == "http://localhost:8080/dev"
    assert client.profile_id == "custom-profile-id"
    assert client.host_name == "pytest-runner/1.0"
    assert client.timeout == 30


def test_client_initialization_without_api_key():
    client = FreeroutingClient(base_url="http://127.0.0.1:37864")
    assert client.api_key is None
    assert "Authorization" not in client._get_headers()


@mock.patch("requests.get")
def test_get_system_status_success(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.content = b'{"status":"OK"}'
    mock_response.json.return_value = {"status": "OK", "message": "Service is running"}
    mock_get.return_value = mock_response

    status = client.get_system_status()

    assert status == {"status": "OK", "message": "Service is running"}
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "http://test.invalid/v1/system/status"
    assert kwargs["headers"]["Authorization"] == f"Bearer {client.api_key}"


@mock.patch("requests.post")
def test_create_session_success(mock_post, client):
    session_id = "session-xyz-789"
    mock_response = mock.Mock()
    mock_response.status_code = 201
    mock_response.content = b'{"id":"session-xyz-789"}'
    mock_response.json.return_value = {"id": session_id, "status": "created"}
    mock_post.return_value = mock_response

    session_details = client.create_session()

    assert session_details == {"id": session_id, "status": "created"}
    assert client.session_id == session_id


@mock.patch("requests.put")
def test_start_job_success(mock_put, client):
    job_id = "job-abc-123"
    mock_response = mock.Mock()
    mock_response.status_code = 202
    mock_response.content = b""
    mock_put.return_value = mock_response

    result = client.start_job(job_id)

    assert result == {}


@mock.patch("requests.get")
def test_download_output_no_content(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 204
    mock_response.content = b""
    mock_get.return_value = mock_response

    result = client.download_output("job-123")

    assert result == {}


@mock.patch("requests.get")
def test_get_job_drc_success(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.content = b'{"violations":[]}'
    mock_response.json.return_value = {"$schema": "https://schemas.kicad.org/drc.v1.json", "violations": []}
    mock_get.return_value = mock_response

    report = client.get_job_drc("job-123")

    assert report["violations"] == []
    mock_get.assert_called_once_with(
        "http://test.invalid/v1/jobs/job-123/drc",
        headers=client._get_headers(),
        timeout=client.timeout,
    )


@mock.patch("requests.get")
def test_list_all_jobs_success(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.content = b"[]"
    mock_response.json.return_value = [{"id": "job-1"}]
    mock_get.return_value = mock_response

    jobs = client.list_all_jobs()

    assert jobs == [{"id": "job-1"}]
    mock_get.assert_called_once_with(
        "http://test.invalid/v1/jobs/list/all",
        headers=client._get_headers(),
        timeout=client.timeout,
    )


@mock.patch("requests.put")
def test_monitor_session_success(mock_put, client):
    client.session_id = "session-1"
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.content = b'{"success":true}'
    mock_response.json.return_value = {"success": True}
    mock_put.return_value = mock_response

    result = client.monitor_session()

    assert result["success"] is True


@mock.patch("requests.post")
def test_upload_input_json_with_dict(mock_post, client):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.content = b'{"id":"job-1"}'
    mock_response.json.return_value = {"id": "job-1", "state": "QUEUED"}
    mock_post.return_value = mock_response

    board = {"board": {"layers": []}}
    result = client.upload_input_json("job-1", board)

    assert result["id"] == "job-1"
    args, kwargs = mock_post.call_args
    assert args[0] == "http://test.invalid/v1/jobs/job-1/input/json"
    assert json.loads(kwargs["data"]) == board


@mock.patch("requests.get")
def test_make_request_api_error(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 404
    mock_response.text = "Resource Not Found"
    mock_get.return_value = mock_response

    with pytest.raises(FreeroutingAPIError) as excinfo:
        client.get_system_status()

    assert excinfo.value.status_code == 404
    assert "Resource Not Found" in str(excinfo.value)


@mock.patch("requests.get")
def test_make_request_auth_error(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials provided"
    mock_get.return_value = mock_response

    with pytest.raises(FreeroutingAuthError) as excinfo:
        client.get_system_status()

    assert "Authentication failed: 401" in str(excinfo.value)


def test_get_session_no_id_error(client):
    client.session_id = None
    with pytest.raises(ValueError, match="No session ID provided or stored internally"):
        client.get_session()


def test_enqueue_job_no_id_error(client):
    client.session_id = None
    with pytest.raises(ValueError, match="No session ID provided or stored internally"):
        client.enqueue_job(name="test_job")


def test_get_job_no_id(client):
    with pytest.raises(ValueError, match="Job ID must be provided"):
        client.get_job(job_id="")


def test_upload_input_no_params(client):
    with pytest.raises(ValueError, match="Job ID must be provided"):
        client.upload_input(job_id="", filename="f", file_path="p")
    with pytest.raises(ValueError, match="Filename must be provided"):
        client.upload_input(job_id="j", filename="", file_path="p")
    with pytest.raises(ValueError, match="File path must be provided"):
        client.upload_input(job_id="j", filename="f", file_path="")


def test_parse_sse_events():
    lines = [
        "data: {\"message\":\"starting\"}",
        "",
        "data: {\"message\":\"done\"}",
        "",
    ]
    events = list(_parse_sse_events(iter(lines)))
    assert events == [{"message": "starting"}, {"message": "done"}]


@mock.patch("requests.get")
def test_stream_job_logs(mock_get, client):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = [
        'data: {"level":"INFO","message":"Routing started"}',
        "",
    ]
    mock_response.__enter__ = mock.Mock(return_value=mock_response)
    mock_response.__exit__ = mock.Mock(return_value=False)
    mock_get.return_value = mock_response

    events = list(client.stream_job_logs("job-123"))

    assert events == [{"level": "INFO", "message": "Routing started"}]
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Accept"] == "text/event-stream"


@mock.patch("freerouting.client.FreeroutingClient.download_output")
@mock.patch("freerouting.client.FreeroutingClient.start_job")
@mock.patch("freerouting.client.FreeroutingClient.upload_input")
@mock.patch("freerouting.client.FreeroutingClient.enqueue_job")
@mock.patch("freerouting.client.FreeroutingClient.create_session")
@mock.patch("freerouting.client.FreeroutingClient.get_job")
@mock.patch("freerouting.client.time.sleep", return_value=None)
@mock.patch("freerouting.client.os.path.basename", return_value="board.dsn")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data=b"(pcb)")
def test_run_routing_job_success(
    mock_open_file,
    mock_basename,
    mock_sleep,
    mock_get_job,
    mock_create_session,
    mock_enqueue_job,
    mock_upload_input,
    mock_start_job,
    mock_download_output,
    client,
    tmp_path,
):
    dsn_path = tmp_path / "board.dsn"
    dsn_path.write_bytes(b"(pcb)")

    mock_create_session.return_value = {"id": "session-1"}
    mock_enqueue_job.return_value = {"id": "job-1"}
    mock_get_job.side_effect = [
        {"state": "RUNNING"},
        {"state": "COMPLETED"},
    ]
    mock_download_output.return_value = {"filename": "board.ses", "data": "c2Vz"}

    result = client.run_routing_job(
        name="test",
        dsn_file_path=str(dsn_path),
        poll_interval=1,
        timeout=60,
        verbose=False,
    )

    assert result["filename"] == "board.ses"
    mock_create_session.assert_called_once()
    mock_enqueue_job.assert_called_once()
    mock_upload_input.assert_called_once()
    mock_start_job.assert_called_once_with("job-1")
