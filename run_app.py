"""
Launcher: runs the Streamlit rental-price app and exposes it publicly
via an ngrok tunnel, so it can be reached from outside SageMaker Studio.

Usage:
    python run_app.py

Requires:
    pip install pyngrok streamlit boto3 --quiet

Before running, set NGROK_AUTHTOKEN below (get one free at ngrok.com)
and make sure app.py is in the same folder as this script.
"""

import subprocess
import sys
import time
import signal
import atexit
from pathlib import Path

from pyngrok import ngrok, conf


# ── CONFIGURATION ────────────────────────────────────────────────

NGROK_AUTHTOKEN = "3I4yHHTo3NjAEeAFjTDHKqhSKfR_2HJX8mLz24XirqzEqo6q"
APP_FILE = "app.py"          # must sit next to this script
PORT = 8501
STARTUP_WAIT_SECONDS = 6      # give Streamlit time to bind before tunneling


# ── VALIDATION ───────────────────────────────────────────────────

def validate_setup():
    if NGROK_AUTHTOKEN == "PASTE_YOUR_NGROK_AUTHTOKEN_HERE":
        sys.exit(
            "ERROR: set NGROK_AUTHTOKEN at the top of this script "
            "before running. Get one free at https://dashboard.ngrok.com/get-started/your-authtoken"
        )

    app_path = Path.cwd() / APP_FILE
    if not app_path.exists():
        sys.exit(
            f"ERROR: {APP_FILE} not found in {Path.cwd()}. "
            "Run this script from the same folder as your Streamlit app, "
            "or edit APP_FILE above."
        )


# ── PROCESS MANAGEMENT ──────────────────────────────────────────

streamlit_proc = None
tunnel = None


def cleanup():
    """Ensure the tunnel and subprocess are torn down on exit."""
    global streamlit_proc, tunnel

    print("\nShutting down...")

    if tunnel is not None:
        try:
            ngrok.disconnect(tunnel.public_url)
        except Exception:
            pass
        ngrok.kill()

    if streamlit_proc is not None and streamlit_proc.poll() is None:
        streamlit_proc.terminate()
        try:
            streamlit_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            streamlit_proc.kill()

    print("Done.")


def main():
    global streamlit_proc, tunnel

    validate_setup()
    atexit.register(cleanup)

    # Handle Ctrl+C / SIGTERM cleanly
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # Clear out any stale ngrok sessions from a previous run
    conf.get_default().auth_token = NGROK_AUTHTOKEN
    ngrok.kill()

    print(f"Starting Streamlit ({APP_FILE}) on port {PORT}...")

    streamlit_proc = subprocess.Popen(
        [
            "streamlit", "run", APP_FILE,
            "--server.port", str(PORT),
            "--server.address", "0.0.0.0",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
            "--server.headless", "true",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for Streamlit to actually come up before opening the tunnel
    print(f"Waiting {STARTUP_WAIT_SECONDS}s for Streamlit to bind to the port...")
    time.sleep(STARTUP_WAIT_SECONDS)

    if streamlit_proc.poll() is not None:
        # Process already died — surface the Streamlit error output
        output = streamlit_proc.stdout.read()
        sys.exit(f"ERROR: Streamlit failed to start:\n{output}")

    print("Opening ngrok tunnel...")
    try:
        tunnel = ngrok.connect(PORT, "http")
    except Exception as e:
        sys.exit(
            f"ERROR: ngrok tunnel failed to open: {e}\n"
            "If this hangs or fails outright, your SageMaker Studio domain "
            "may be configured as VpcOnly (no outbound internet access). "
            "Check with:\n"
            "  aws sagemaker describe-domain --domain-id <id> "
            "--query AppNetworkAccessType"
        )

    print("=" * 60)
    print(f"App is live at: {tunnel.public_url}")
    print("=" * 60)
    print("Press Ctrl+C to stop.\n")

    # Stream Streamlit's logs to the console so you can see requests/errors
    try:
        for line in streamlit_proc.stdout:
            print(line, end="")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
