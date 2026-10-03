#!/usr/bin/env python3
import os
import subprocess
import sys
import time

def main():
    port = os.environ.get("PORT", "8000")
    port = str(int(port))  # ensure it's a clean integer string
    
    api_base = f"http://localhost:{port}"
    os.environ["API_BASE"] = api_base
    
    # Start FastAPI uvicorn in background process
    api_cmd = [
        sys.executable, "-m", "uvicorn",
        "api.main:app",
        "--host", "0.0.0.0",
        "--port", port,
    ]
    api_proc = subprocess.Popen(api_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for API to start
    time.sleep(3)
    
    # Start Streamlit chat
    streamlit_cmd = [
        sys.executable, "-m", "streamlit",
        "run", "streamlit/chat.py",
        "--server.port", port,
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--server.fileWatcherType", "poll",
    ]
    subprocess.run(streamlit_cmd)

if __name__ == "__main__":
    main()