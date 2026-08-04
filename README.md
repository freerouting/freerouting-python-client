# Freerouting Python Client

[![PyPI version](https://badge.fury.io/py/freerouting-client.svg)](https://badge.fury.io/py/freerouting-client)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/license/MIT)
[![Python Versions](https://img.shields.io/pypi/pyversions/freerouting-client.svg)](https://pypi.org/project/freerouting-client/)

This library provides a convenient Python interface for interacting with the [Freerouting API](https://api.freerouting.app/v1) (`api.freerouting.app`). It allows you to manage routing sessions, enqueue jobs, upload designs, download results, stream progress, and monitor jobs programmatically.

**Note:** This client is currently in **Alpha**. The API and client library interface may change in future versions.

## Links

* **Main Freerouting Project:** [github.com/freerouting/freerouting](https://github.com/freerouting/freerouting)
* **Freerouting Website & API Access:** [www.freerouting.app](https://www.freerouting.app/)
* **Freerouting API Documentation:** [Freerouting API v1 Docs](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)
* **PyPI Package:** [pypi.org/project/freerouting-client/](https://pypi.org/project/freerouting-client/)
* **Issue Tracker:** [github.com/freerouting/freerouting-python-client/issues](https://github.com/freerouting/freerouting-python-client/issues)

## Installation

You can install the library directly from PyPI:

```bash
pip install freerouting-client
```

For development:

```bash
pip install -e ".[dev]"
```

## Getting Started

You'll need an API key from the [Freerouting website](https://www.freerouting.app/) to use the hosted cloud API.

```python
from freerouting import FreeroutingClient
import os

api_key = os.environ.get("FREEROUTING_API_KEY")
if not api_key:
    raise ValueError("Please set the FREEROUTING_API_KEY environment variable.")

client = FreeroutingClient(api_key=api_key)

status = client.get_system_status()
print(f"API Status: {status.get('status', 'Unknown')}")
```

### Local / self-hosted Freerouting

When running Freerouting locally with authentication disabled, omit the API key and point the client at your local server:

```python
client = FreeroutingClient(
    base_url="http://127.0.0.1:37864",
    version="v1",
)
```

## Example: Running a Full Routing Job

```python
from freerouting import FreeroutingClient, FreeroutingError

client = FreeroutingClient(api_key=os.environ["FREEROUTING_API_KEY"])

output_data = client.run_routing_job(
    name="My Python Client Test Job",
    dsn_file_path="path/to/my_board.dsn",
    settings={"max_passes": 5},
    poll_interval=10,
    output_path="routed_output.ses",
)

print(f"Output filename: {output_data.get('filename')}")
```

## API Coverage

| Area | Methods |
|------|---------|
| System | `get_system_status()`, `get_environment()` |
| Sessions | `create_session()`, `list_sessions()`, `get_session()`, `get_session_logs()`, `monitor_session()` |
| Jobs | `enqueue_job()`, `list_jobs()`, `list_all_jobs()`, `get_job()`, `update_job_settings()`, `start_job()`, `cancel_job()` |
| Input / output | `upload_input()`, `upload_input_json()`, `download_output()`, `download_output_json()`, `get_job_drc()` |
| Logs & streaming | `get_job_logs()`, `stream_job_logs()`, `stream_job_output()`, `stream_job_output_json()` |
| Workflow | `run_routing_job()` |

### KiCad JSON workflow

For the KiCad IPC bridge workflow, upload raw JSON and download JSON output:

```python
import json

with open("board.json", encoding="utf-8") as f:
    board = json.load(f)

job = client.enqueue_job("KiCad JSON test")
client.upload_input_json(job["id"], board)
client.start_job(job["id"])

# Poll with get_job(job["id"]) or stream progress:
for update in client.stream_job_output_json(job["id"]):
    print(update.get("statistics", {}))

result = client.download_output_json(job["id"], output_path="board_routed.json")
```

### DRC report

```python
drc = client.get_job_drc(job_id)
print(len(drc.get("violations", [])))
```

## Error Handling

The client raises typed exceptions:

* `FreeroutingAuthError` — invalid or missing credentials (HTTP 401/403)
* `FreeroutingAPIError` — other non-success API responses
* `FreeroutingError` — network failures and workflow errors

## Contributing

Contributions to the Freerouting Python Client are welcome. Please refer to the main [Freerouting Contribution Guide](https://github.com/freerouting/freerouting/blob/master/docs/CONTRIBUTING.md) for general guidelines and open an issue or pull request in *this* repository (`freerouting-python-client`).

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Support the Main Freerouting Project

Developing and maintaining Freerouting requires significant effort. If you find the tool useful, please consider supporting its development.

**[Sponsor @andrasfuchs on GitHub Sponsors](https://github.com/sponsors/andrasfuchs)**
