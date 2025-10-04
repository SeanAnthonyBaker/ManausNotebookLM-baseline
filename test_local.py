#!/usr/bin/env python3
"""
Local test script for the NotebookLM Automation API.
This script runs a series of live tests against a running instance of the application.
"""

import sys
import requests
import time
import json
import argparse

# Add the src directory to Python path
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def check_flask_app_import():
    """A simple pre-check to ensure the Flask app can be imported."""
    print("▶️  Running: Basic Flask app import check...")
    try:
        from main import app
        # A simple check to ensure the app object is valid
        with app.app_context():
            pass
        print("✅ PASSED: Flask app imports and context works.")
        return True
    except ImportError as e:
        print(f"❌ FAILED: Could not import Flask app from main.py. Error: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Error during Flask app context check. Error: {e}")
        return False

def _test_streaming_query(base_url, args):
    """
    Performs the streaming query test.
    This is a helper for run_api_tests to keep the streaming logic separate.
    """
    query_text = args.query
    notebook_url_to_test = args.notebook_url

    with requests.post(
        f"{base_url}/api/query",
        json={"query": query_text, "notebooklm_url": notebook_url_to_test},
        stream=True,
        timeout=180
    ) as r:
        r.raise_for_status()  # Will raise an HTTPError for bad responses (4xx or 5xx)
        
        full_response = ""
        print("   Streaming response:", end='', flush=True)
        for line in r.iter_lines():
            if line.startswith(b'data:'):
                data = json.loads(line.decode('utf-8').split('data: ', 1)[1])
                if 'chunk' in data:
                    print(data['chunk'], end='', flush=True)
                    full_response += data['chunk']
        print("\n   Stream finished.")
    return full_response

def run_api_tests(args):
    """Run tests against a live server, reporting all results."""
    base_url = "http://localhost:5000"
    successes = 0
    failures = 0

    print("🌐 Testing Live Server Endpoints...")

    # --- Health Check ---
    print("▶️  Running: Server Health Check...")
    try:
        health_response = requests.get(f"{base_url}/api/status", timeout=10)
        health_response.raise_for_status()
        print("✅ PASSED: Server is running.")
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: Server is not responding at {base_url}. Please start the server first.")
        print(f"   Error: {e}")
        return False

    def run_test(name, test_func, expected_status=200, check_json=None):
        nonlocal successes, failures
        print(f"▶️  Running: {name}")
        try:
            response = test_func()
            if response.status_code != expected_status:
                print(f"❌ FAILED: Expected status {expected_status}, got {response.status_code}")
                try:
                    # Try to pretty-print JSON error if available
                    print(f"   Response: {json.dumps(response.json(), indent=2)}")
                except json.JSONDecodeError:
                    # Fallback to raw text if not JSON
                    print(f"   Response: {response.text[:200]}")
                failures += 1
                return None

            json_data = None
            if "application/json" in response.headers.get("Content-Type", ""):
                json_data = response.json()

            if check_json and not check_json(json_data):
                print("❌ FAILED: JSON content check failed.")
                print(f"   Response JSON: {json.dumps(json_data, indent=2)}")
                failures += 1
                return None

            print("✅ PASSED")
            successes += 1
            return response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text
        except requests.exceptions.RequestException as e:
            print(f"❌ FAILED with connection error: {e}")
            failures += 1
            return None

    # --- API Test Sequence ---
    print("\n--- Testing User API ---")
    run_test(
        "GET /api/users (initially empty)",
        lambda: requests.get(f"{base_url}/api/users", timeout=5),
        check_json=lambda data: isinstance(data, list) and len(data) == 0
    )

    print("\n--- Testing Stateless Query API ---")
    run_test(
        "POST /api/query (streaming)",
        lambda: _test_streaming_query(base_url, args),
        expected_status=200, # _test_streaming_query will raise for non-200
        check_json=lambda data: isinstance(data, str) and len(data) > 0
    )

    print("-" * 50)
    print(f"Test Summary: {successes} passed, {failures} failed.")
    return failures == 0

def print_instructions():
    """Prints instructions for how to run the application and tests."""
    print("""\
🚀 NotebookLM Automation - Local Testing Script
================================================
This script can perform two actions:
1. A basic check to ensure the Flask app is importable (default).
2. A suite of live API tests against a running server (if called with --api).

------------------------------------------------
✅ Basic Flask app import check passed!
------------------------------------------------

📋 To run the full application stack (Flask App + Selenium):

1. **(One-Time Setup) Create Application Credentials:**
   This allows the application to authenticate with Google Cloud services.
   Run this command in your terminal and follow the browser prompts:
   `gcloud auth application-default login`
   Then, copy the generated credentials into the `.gcloud` directory in your project root.

2. **Start the Application:**
   - **On Windows:** Open a Command Prompt or PowerShell and run:
     `start.bat`
   - **On macOS/Linux:** Open a terminal and run:
     `./start.sh`

   This will build and start both the `app` and `selenium` services using docker-compose.
   The services will be available at:
   - Flask API: http://localhost:5000
   - VNC Viewer: http://localhost:7900 (password: secret)

3. **Run Live API Tests:**
   Once the services are running and healthy, open a new terminal and run:
   `python test_local.py --api`
""")

def get_args():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Local test script for NotebookLM Automation API.")
    parser.add_argument('--api', action='store_true', help='Run the live API tests against a running server.')
    parser.add_argument('--query', type=str, default="What is the capital of France?", help='The query to send for the streaming test.')
    parser.add_argument('--notebook_url', type=str, default="https://notebooklm.google.com/", help='The NotebookLM URL to test against.')
    return parser.parse_args()

def main():
    """Main entry point for the test script."""
    args = get_args()

    if args.api:
        # Run the live API tests
        return run_api_tests(args)
    else:
        # Run the basic import check and print instructions
        if not check_flask_app_import():
            return False
        print_instructions()
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
