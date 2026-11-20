"""Interactive smoke test: starts firewall and sends a tools/call request."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cmd = [
    sys.executable, str(ROOT / "run.py"),
    "--command", sys.executable, "--args", "-u", str(ROOT / "demo" / "mock_mcp_server.py")
]
proc = subprocess.Popen(
    cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.PIPE, text=True, bufsize=1
)

def read_response():
    for line in proc.stdout:
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("id") == 7:
            print("\nResponse from firewall/downstream:")
            print(json.dumps(msg, indent=2))
            return

threading.Thread(target=read_response, daemon=True).start()

def read_diagnostics():
    for line in proc.stderr:
        print(line, end="", file=sys.stderr)

threading.Thread(target=read_diagnostics, daemon=True).start()
request = {
    "jsonrpc": "2.0", "id": 7, "method": "tools/call",
    "params": {"name": "echo", "arguments": {"text": "Hello from the MCP Firewall"}}
}
proc.stdin.write(json.dumps(request) + "\n")
proc.stdin.flush()

print("Approval popup opened. Choose Allow or Block.")
try:
    time.sleep(15)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
