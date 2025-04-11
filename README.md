# Freerouting Python Client

[![PyPI version](https://badge.fury.io/py/freerouting-client.svg)](https://badge.fury.io/py/freerouting-client)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Versions](https://img.shields.io/pypi/pyversions/freerouting-client.svg)](https://pypi.org/project/freerouting-client/)
**Development Status:** Alpha

This library provides a convenient Python interface for interacting with the [Freerouting API](https://api.freerouting.app/v1) (`api.freerouting.app`). It allows you to manage routing sessions, enqueue jobs, upload designs, download results, and monitor progress programmatically.

**Note:** This client is currently in **Alpha**. The API and client library interface may change in future versions.

## Links

* **Main Freerouting Project:** [github.com/freerouting/freerouting](https://github.com/freerouting/freerouting)
* **Freerouting Website & API Access:** [www.freerouting.app](https://www.freerouting.app/)
* **Freerouting API Documentation:** [Freerouting API v1 Docs](https://github.com/freerouting/freerouting/blob/master/docs/API_v1.md)
* **PyPI Package:** [pypi.org/project/freerouting-client/](https://pypi.org/project/freerouting-client/)
* **Issue Tracker:** [github.com/freerouting/freerouting-python-client/issues](https://github.com/freerouting/freerouting-python-client/issues)

## Installation

You can install the library directly from PyPI:

```bash
pip install freerouting-client
```

## Getting Started

You'll need an API key from the [Freerouting website](https://www.freerouting.app/) to use the client.

```python
from freerouting import FreeroutingClient
import os

# --- Configuration ---
# It's recommended to use environment variables for sensitive data like API keys
api_key = os.environ.get("FREEROUTING_API_KEY")
if not api_key:
    raise ValueError("Please set the FREEROUTING_API_KEY environment variable.")

# Optional: If using a local Freerouting instance or a different API version
# base_url = "http://localhost:8080"
# version = "dev"
# client = FreeroutingClient(api_key=api_key, base_url=base_url, version=version)

# Default usage (connecting to api.freerouting.app/v1)
client = FreeroutingClient(api_key=api_key)

# --- Basic Usage ---
try:
    # Check API status
    status = client.get_system_status()
    print(f"API Status: {status.get('status', 'Unknown')}")

    # Create a session (optional, run_routing_job does this if needed)
    # session = client.create_session()
    # print(f"Created session ID: {session.get('id')}")

except Exception as e: # Consider catching specific FreeroutingError exceptions
    print(f"An error occurred: {e}")


# --- Example: Running a Full Routing Job ---
# Ensure you have a DSN file (e.g., 'my_board.dsn') available

dsn_file = "path/to/your/my_board.dsn" # CHANGE THIS PATH
job_name = "My Python Client Test Job"

if not os.path.exists(dsn_file):
    print(f"Error: Input file not found at {dsn_file}")
else:
    print(f"\nStarting routing job '{job_name}' for file '{dsn_file}'...")
    try:
        # run_routing_job handles session creation, upload, start, polling, and download
        output_data = client.run_routing_job(
            name=job_name,
            dsn_file_path=dsn_file,
            # settings={"router_passes": 5}, # Optional: Provide router settings
            poll_interval=10 # Check status every 10 seconds
            # timeout=600 # Max wait time in seconds (default 3600)
        )

        print("Job completed successfully!")

        # The output_data contains the result, including the base64 encoded SES file
        output_filename = output_data.get("filename", "routed_output.ses")
        output_filepath = f"./{output_filename}" # Save in current directory

        # Decode and save the output .ses file
        if "data" in output_data:
            import base64
            with open(output_filepath, "wb") as f:
                f.write(base64.b64decode(output_data["data"]))
            print(f"Output saved to: {output_filepath}")
        else:
            print("Warning: Output data field missing in response.")
        # print("Full output response:", output_data)

    except Exception as e: # Replace with specific exceptions if defined
        print(f"Routing job failed: {e}")

```

## Contributing

Contributions to the Freerouting Python Client are welcome\! Please refer to the main [Freerouting Contribution Guide](https://www.google.com/search?q=https://github.com/freerouting/freerouting/blob/master/docs/CONTRIBUTING.md) for general guidelines and open an issue or pull request in *this* repository (`freerouting-python-client`).

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

## 🙏 Support the Main Freerouting Project

Developing and maintaining Freerouting requires significant effort. If you find the tool useful, please consider supporting its development\!

**[Sponsor @andrasfuchs on GitHub Sponsors](https://github.com/sponsors/andrasfuchs)**