#!/usr/bin/env python3
"""
examples/gex_scan.py — Fortress MCP: Dark Pool Floors & GEX Walls Scan
Calls get_dp_floors_and_gex for every ticker in the active universe and
writes the results to gex_scan_output.json.

Usage:
    export FORTRESS_MCP_PATH=/path/to/fortress-mcp/fortress_mcp.py
    export FORTRESS_API_URL=http://YOUR_VPS_IP:8080
    export FORTRESS_API_TOKEN=YOUR_64_CHAR_TOKEN
    python3 examples/gex_scan.py [TICKER1 TICKER2 ...]

    If no tickers are passed, defaults to the portfolio universe tickers.
"""
import subprocess
import json
import os
import sys
import time

MCP_PATH = os.environ.get(
    "FORTRESS_MCP_PATH",
    os.path.join(os.path.dirname(__file__), "..", "fortress_mcp.py"),
)

env = os.environ.copy()

DEFAULT_TICKERS = ["SPY", "SPX", "MSFT", "AVGO", "VST", "NFLX", "UNH", "NVDA", "AMZN"]


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


tickers = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_TICKERS
results: dict = {}

for ticker in tickers:
    print(f"get_dp_floors_and_gex {ticker}...")
    results[ticker] = call_mcp_tool("get_dp_floors_and_gex", {"ticker": ticker})

output_path = os.path.join(os.path.dirname(__file__), "gex_scan_output.json")
with open(output_path, "w") as f:
    json.dump(results, f, indent=2)

print(f"\nResults written to {output_path}")
print("\n=== GEX RESULTS ===")
print(json.dumps(results, indent=2))
