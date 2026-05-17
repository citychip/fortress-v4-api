#!/usr/bin/env python3
"""
examples/position_analysis.py — Fortress MCP: Stop-Loss, Roll & Pre-Trade Analysis
Evaluates stop-loss and roll status for active positions, then runs pre-trade
gate checks for new entry candidates. Writes results to position_analysis_output.json.

Usage:
    export FORTRESS_MCP_PATH=/path/to/fortress-mcp/fortress_mcp.py
    export FORTRESS_API_URL=http://YOUR_VPS_IP:8080
    export FORTRESS_API_TOKEN=YOUR_64_CHAR_TOKEN
    python3 examples/position_analysis.py

Edit ACTIVE_POSITIONS and NEW_CANDIDATES below to match your portfolio.
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

# ── Edit these to match your portfolio ────────────────────────────────────────
ACTIVE_POSITIONS = [
    ("MSFT", "pmcc"),
    ("AVGO", "pmcc"),
    ("VST",  "pmcc"),
    ("NFLX", "pmcc"),
    ("UNH",  "pcs"),
]

NEW_CANDIDATES = [
    ("NVDA",  "pmcc"),
    ("AMD",   "pmcc"),
    ("GOOGL", "pmcc"),
    ("META",  "pmcc"),
    ("AAPL",  "pmcc"),
]
# ─────────────────────────────────────────────────────────────────────────────


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


data: dict = {}

print("── Stop-loss evaluation ──────────────────────────────────────────────")
for ticker, _ in ACTIVE_POSITIONS:
    print(f"  evaluate_stop_loss {ticker}...")
    data[f"stop_loss_{ticker}"] = call_mcp_tool("evaluate_stop_loss", {"ticker": ticker})

print("\n── Roll evaluation ───────────────────────────────────────────────────")
for ticker, _ in ACTIVE_POSITIONS:
    print(f"  evaluate_roll {ticker}...")
    data[f"roll_{ticker}"] = call_mcp_tool("evaluate_roll", {"ticker": ticker})

print("\n── Pre-trade gate checks ─────────────────────────────────────────────")
for ticker, strategy in NEW_CANDIDATES:
    print(f"  pretrade_check {ticker} ({strategy})...")
    data[f"pretrade_{ticker}"] = call_mcp_tool(
        "pretrade_check", {"ticker": ticker, "strategy": strategy}
    )

output_path = os.path.join(os.path.dirname(__file__), "position_analysis_output.json")
with open(output_path, "w") as f:
    json.dump(data, f, indent=2)

print(f"\nResults written to {output_path}")
