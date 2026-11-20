# MCP Firewall (Python MVP)

A local STDIO JSON-RPC proxy that pauses MCP `tools/call` requests until a user approves or blocks them.

## Scope and limitations

- Implements a **local STDIO proxy** suitable as a Claude Desktop MCP server command.
- Intercepts `tools/call`; other JSON-RPC messages are forwarded.
- A blocked request receives JSON-RPC error `-32001`.
- Requests are handled on separate worker threads, so multiple calls can await approval concurrently.
- The popup is configured to stay above other windows.
- This MVP does **not** intercept Claude Web. Claude Web needs a remotely hosted MCP gateway using Streamable HTTP and must be explicitly configured to use that gateway.
- This is a take-home MVP, not a hardened production security boundary. Review transport framing, cancellation, lifecycle, authentication, and platform-specific behavior before production use.

## Requirements

- Python 3.10+
- macOS / Windows / Linux desktop session
- A working Qt display environment
- `pip install -r requirements.txt`

## Run the safe local demo

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python run.py --command python --args -u demo/mock_mcp_server.py
```

The process is now waiting for MCP JSON-RPC messages on stdin. In a **second terminal**, send an initialize request:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"manual-test","version":"1.0"}}}' | python run.py --command python --args -u demo/mock_mcp_server.py
```

For interactive approval testing, use the included harness:

```bash
python demo/manual_client.py
```

The harness starts the firewall and sends a tool call. The popup appears; choose Allow or Block. The harness prints the response. On Allow, the mock server prints `[MOCK SERVER EXECUTED echo]` to its stderr. On Block, that execution marker must **not** appear and the harness receives error `-32001`.

## Claude Desktop configuration

First install dependencies in a stable virtual environment and use absolute paths. Add a server entry to Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "filesystem-protected": {
      "command": "/ABSOLUTE/PATH/TO/.venv/bin/python",
      "args": [
        "/ABSOLUTE/PATH/TO/mcp-firewall/run.py",
        "--command", "npx",
        "--args", "-y",
        "@modelcontextprotocol/server-filesystem",
        "/ABSOLUTE/PATH/TO/SAFE/TEST/DIRECTORY"
      ]
    }
  }
}
```

Important: this example passes the filesystem server's arguments to the proxy. For complex commands, use a small wrapper script or extend the CLI to accept a JSON config file; avoid putting secrets in command-line arguments.

Restart Claude Desktop after editing its config. Ask Claude to list files in the configured test directory. The approval popup should appear for each `tools/call`.

## Architecture

Claude Desktop -> this process (MCP STDIO proxy) -> real MCP server.

The proxy launches the downstream server as a child process. It reads newline-delimited JSON-RPC messages from Claude, detects `method == "tools/call"`, and waits for a decision from the Qt UI. Allow forwards the original message. Block returns a JSON-RPC error with code `-32001` without forwarding the request. Downstream stdout is relayed to Claude; downstream stderr is relayed to the firewall's stderr.

## Security notes

- Closing the popup and timing out both fail closed.
- Do not expose this proxy to untrusted local users or remote clients.
- Validate server configuration and executable paths before production use.
- A production implementation should handle MCP cancellation notifications, server-initiated requests, content-length framing where applicable, process restart, graceful Qt shutdown, and Streamable HTTP.
