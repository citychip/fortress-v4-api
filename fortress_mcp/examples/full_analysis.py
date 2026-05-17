#!/usr/bin/env python3
"""
examples/full_analysis.py — Fortress MCP: Full Portfolio Data Dump
Calls all major read-only tools in sequence and writes the combined output
to full_analysis_output.json. Useful as a daily snapshot or CI health check.

Usage:
    export FORTRESS_MCP_PATH=/path/to/fortress-mcp/fortress_mcp.py
    export FORTRESS_API_URL=http://YOUR_VPS_IP:8080
    export FORTRESS_API_TOKEN=YOUR_64_CHAR_TOKEN
    python3 examples/full_analysis.py
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


TOOLS: list[tuple[str, str, dict]] = [
    ("briefing",          "get_briefing",          {}),
    ("positions",         "get_positions",          {}),
    ("positions_raw",     "get_positions",          {"aggregated": False}),
    ("capability",        "get_capability",         {}),
    ("candidates",        "get_candidates",         {}),
    ("calendar",          "get_calendar",           {"window_days": 30}),
    ("universe",          "get_universe",           {}),
    ("alerts",            "get_alerts",             {}),
    ("journal",           "get_journal",            {"limit": 10}),
    ("settings",          "get_settings",           {}),
    ("spy_hedge",         "get_spy_hedge_coverage", {}),
    ("ibkr_status",       "get_ibkr_status",        {}),
]

data: dict = {}
for key, tool, args in TOOLS:
    print(f"Calling {tool}...", flush=True)
    data[key] = call_mcp_tool(tool, args)

output_path = os.path.join(os.path.dirname(__file__), "full_analysis_output.json")
with open(output_path, "w") as f:
    json.dump(data, f, indent=2)

print(f"\nAll data collected. Written to {output_path}")
print(f"Keys: {list(data.keys())}")
