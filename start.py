"""Start script for Render deployment.

Runs both the FastAPI backend and Streamlit chat UI in a single process
on the $PORT Render assigns. The Streamlit UI connects to the API via
the same port using the API_BASE configuration.

Run with: python -m start.py
"""
import os
import subprocess
import sys
import time


def main():
    port = os.environ.get("PORT", "8000")
    port = int(port)

    # API Base URL for Streamlit to connect to
    # On Render, both processes share the same $PORT
    api_base = f"http://localhost:{port}"

    # Configure the API base in the module before importing streamlit chat
    # We'll set it as an environment variable that the chat module reads
    os.environ["API_BASE"] = api_base

    # Start the FastAPI server in the background
    api_cmd = [
        sys.executable, "-m", "uvicorn",
        "api.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ]
    api_proc = subprocess.Popen(api_cmd)

    # Small delay to let the API start
    time.sleep(2)

    # Start Streamlit
    streamlit_cmd = [
        sys.executable, "-m", "streamlit",
        "run", "streamlit/chat.py",
        "--server.port", str(port),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--server.fileWatcherType", "poll",
        "--server.serverTimeout", "120",
        "--server.maxMessageSize", "120",
    ]

    subprocess.run(streamlit_cmd)


if __name__ == "__main__":
    main()