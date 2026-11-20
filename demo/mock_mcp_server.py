"""Tiny newline-delimited JSON-RPC server for a safe local demo."""
import json
import sys

for line in sys.stdin:
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue

    method = msg.get("method")
    request_id = msg.get("id")

    if method == "initialize":
        response = {
            "jsonrpc": "2.0", "id": request_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "firewall-demo-server", "version": "1.0.0"}
            }
        }
    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0", "id": request_id,
            "result": {"tools": [
                {"name": "echo", "description": "Returns the supplied text",
                 "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}
            ]}
        }
    elif method == "tools/call":
        args = (msg.get("params") or {}).get("arguments") or {}
        # This output proves that the downstream tool actually executed.
        print("[MOCK SERVER EXECUTED echo]", file=sys.stderr, flush=True)
        response = {
            "jsonrpc": "2.0", "id": request_id,
            "result": {"content": [{"type": "text", "text": args.get("text", "")}]}
        }
    else:
        if request_id is None:
            continue
        response = {
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

    if request_id is not None:
        print(json.dumps(response), flush=True)
