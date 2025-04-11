import os
import base64
import sys
from freerouting import FreeroutingClient # Import your client library
from freerouting.client import FreeroutingError, FreeroutingAPIError, FreeroutingAuthError # Import specific errors

# --- Configuration ---

# 1. API Key: Best practice is to use an environment variable.
#    Set FREEROUTING_API_KEY in your terminal before running the script:
#    export FREEROUTING_API_KEY='your_actual_api_key' (Linux/macOS)
#    set FREEROUTING_API_KEY=your_actual_api_key (Windows Cmd)
#    $env:FREEROUTING_API_KEY='your_actual_api_key' (Windows PowerShell)
api_key = os.environ.get("FREEROUTING_API_KEY")

if not api_key:
    print("ERROR: FREEROUTING_API_KEY environment variable not set.")
    print("Please set the variable with your API key before running.")
    sys.exit(1) # Exit if API key is missing

# 2. Input File Path:
#    Update this path to point to your "Mars-64-revE.dsn" file.
#    If the file is in the same directory as this script, just the filename is okay.
dsn_file_path = "Mars-64-revE.dsn"

# 3. Output File Path (Optional): Where to save the resulting .ses file
#    The filename will be taken from the API response, saving in the script's directory.
output_directory = "." # Save in the current directory

# 4. Job Name (Optional): A descriptive name for the job
job_name = "Test_Mars_64_revE_Routing"

# --- Check Input File ---
if not os.path.exists(dsn_file_path):
    print(f"ERROR: Input DSN file not found at '{dsn_file_path}'")
    print("Please ensure the file exists and the path is correct.")
    sys.exit(1)

# --- Initialize Client ---
print("Initializing FreeroutingClient...")
# You can specify base_url and version if connecting to a local instance or different API version
# client = FreeroutingClient(api_key=api_key, base_url="http://localhost:8080", version="dev")
client = FreeroutingClient(api_key=api_key)
print("Client initialized.")

# --- Run the Routing Job ---
print(f"\nAttempting to run routing job '{job_name}' for file '{dsn_file_path}'...")

try:
    # Use the high-level workflow helper
    # It handles session creation, upload, start, polling, and download data retrieval
    output_data = client.run_routing_job(
        name=job_name,
        dsn_file_path=dsn_file_path,
        # settings={"router_passes": 10}, # Optional: Add custom router settings here if needed
        poll_interval=3,  # Check status every 3 seconds
        timeout=1800      # Wait up to 30 minutes (adjust as needed)
    )

    print("\n------------------------------------")
    print("🎉 Routing Job Completed Successfully! 🎉")
    print("------------------------------------")

    # --- Save the Output File ---
    output_filename = output_data.get("filename", f"{os.path.splitext(job_name)[0]}_output.ses")
    output_filepath = os.path.join(output_directory, output_filename)

    if "data" in output_data:
        print(f"Saving output file to: {output_filepath}")
        try:
            decoded_data = base64.b64decode(output_data["data"])
            with open(output_filepath, "wb") as f:
                f.write(decoded_data)
            print("Output file saved successfully.")
        except (IOError, OSError, base64.binascii.Error, TypeError) as save_e:
            print(f"\nERROR: Could not save output file '{output_filepath}': {save_e}")
            print("Raw Base64 data might still be available in the response dictionary below.")
    else:
        print("\nWarning: Output 'data' field missing in the response. Cannot save file.")

    # Optional: Print the full response dictionary (excluding the potentially large data field)
    # response_copy = output_data.copy()
    # response_copy.pop('data', None) # Remove data field for cleaner printing
    # print("\nAPI Response (metadata):")
    # import json
    # print(json.dumps(response_copy, indent=2))


# --- Handle Potential Errors ---
except FreeroutingAuthError as e:
    print(f"\n------------------------------------")
    print(f"❌ ERROR: Authentication Failed! ❌")
    print(f"------------------------------------")
    print(f"Details: {e}")
    print("Please check your API key and ensure it's correctly set in the environment variable.")

except FreeroutingAPIError as e:
    print(f"\n------------------------------------")
    print(f"❌ ERROR: API Request Failed! ❌")
    print(f"------------------------------------")
    print(f"Status Code: {e.status_code}")
    print(f"Response: {e.response_text}")

except FreeroutingError as e: # Catch base Freerouting errors (includes network, job failures from run_routing_job)
    print(f"\n------------------------------------")
    print(f"❌ ERROR: Freerouting Client Error! ❌")
    print(f"------------------------------------")
    print(f"Details: {e}")

except FileNotFoundError as e: # Specific catch for the input file check
    print(f"\n------------------------------------")
    print(f"❌ ERROR: Input File Not Found! ❌")
    print(f"------------------------------------")
    print(f"Details: {e}") # Already printed specific message above

except TimeoutError as e:
    print(f"\n------------------------------------")
    print(f"❌ ERROR: Job Timed Out! ❌")
    print(f"------------------------------------")
    print(f"Details: {e}")
    print(f"The job did not complete within the specified timeout period.")

except Exception as e: # Catch any other unexpected errors
    print(f"\n------------------------------------")
    print(f"❌ ERROR: An Unexpected Error Occurred! ❌")
    print(f"------------------------------------")
    print(f"Details: {e}")
    import traceback
    traceback.print_exc() # Print full traceback for unexpected errors

finally:
    print("\n--- Test script finished ---")