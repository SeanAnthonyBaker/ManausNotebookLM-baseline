import requests
import json
import sys

def test_process_query():
    url = "http://localhost:5000/api/process_query"
    payload = {
        "notebooklm_url": "https://notebooklm.google.com/notebook/974894e1-d636-4df2-906a-fac1baeb3c67", 
        "query": "What is the summary of this notebook?",
        "timeout": 300
    }
    
    print(f"Sending request to {url}...")
    try:
        with requests.post(url, json=payload, stream=True) as response:
            if response.status_code != 200:
                print(f"Error: Received status code {response.status_code}")
                print(response.text)
                return

            print("Response stream started:")
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        data_str = decoded_line[6:]
                        try:
                            data = json.loads(data_str)
                            if 'chunk' in data:
                                print(data['chunk'], end='', flush=True)
                            elif 'status' in data:
                                print(f"\n[STATUS]: {data['status']}")
                            elif 'error' in data:
                                print(f"\n[ERROR]: {data['error']}")
                            elif 'message' in data:
                                print(f"\n[MESSAGE]: {data['message']}")
                        except json.JSONDecodeError:
                            print(f"\n[RAW]: {decoded_line}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_process_query()
