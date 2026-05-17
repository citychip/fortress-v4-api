#!/usr/bin/env python3
"""
examples/briefing.py — Fortress MCP: Live Portfolio Briefing
Calls get_briefing, get_capability, get_alerts, and get_positions via the
MCP server and prints a structured summary to stdout.

Usage:
    export FORTRESS_MCP_PATH=/path/to/fortress-mcp/fortress_mcp.py
    export FORTRESS_API_URL=http://YOUR_VPS_IP:8080
    export FORTRESS_API_TOKEN=YOUR_64_CHAR_TOKEN
    python3 examples/briefing.py
"""
import subprocess
import json
import os
import time

MCP_PATH = os.environ.get(
    "FORTRESS_MCP_PATH",
    os.path.join(os.path.dirname(__file__), "..", "fortress_mcp.py"),
)

env = os.environ.copy()


def call_mcp_tool(tool_name: str, arguments: dict | None = None) -> dict | str | None:
    """Spawn the MCP server as a subprocess, call one tool, return the result."""
    if arguments is None:
        arguments = {}
    proc = subprocess.Popen(
        ["python3", MCP_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    messages = [
        json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "example-script", "version": "1.0"},
            },
        }) + "\n",
        json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }) + "\n",
    ]
    for msg in messages:
        proc.stdin.write(msg.encode())
    proc.stdin.flush()
    time.sleep(3)
    proc.terminate()
    out = proc.stdout.read().decode()
    for line in out.strip().split("\n"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            if d.get("id") == 2:
                content = d.get("result", {}).get("content", [])
                if content:
                    text = content[0].get("text", "")
                    try:
                        return json.loads(text)
                    except Exception:
                        return text
        except Exception:
            pass
    return None


print("=" * 60)
print("FORTRESS DASHBOARD — LIVE MCP BRIEFING")
print("=" * 60)

print("\n[1/4] Fetching portfolio briefing...")
briefing = call_mcp_tool("get_briefing")
if briefing:
    print(json.dumps(briefing, indent=2))

print("\n[2/4] Fetching Greeks backend capability...")
capability = call_mcp_tool("get_capability")
if capability:
    print(json.dumps(capability, indent=2))

print("\n[3/4] Fetching active alerts...")
alerts = call_mcp_tool("get_alerts")
if alerts:
    print(json.dumps(alerts, indent=2))

print("\n[4/4] Fetching positions...")
positions = call_mcp_tool("get_positions")
if positions:
    print(json.dumps(positions, indent=2))

print("\n" + "=" * 60)
print("END OF MCP BRIEFING")
print("=" * 60)
