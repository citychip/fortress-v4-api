"""
qd_mcp_client.py — QuantData MCP client helper for Manus / sandbox environments.

This module provides a lightweight Python interface to the `quantdata-mcp` stdio
server, allowing any script in the Fortress build to call QuantData MCP tools
without needing a registered MCP connector.

Prerequisites
-------------
Install the quantdata-mcp package:
    sudo pip3 install quantdata-mcp

Configure credentials at ~/.quantdata-mcp/config.json:
    {
      "auth_token": "<your QuantData JWT token>",
      "instance_id": "<your QuantData user ID>",
      "page_id":     "<your MCP Agentic Page ID>",
      "tools":       {},
      "pages":       []
    }

Usage
-----
    from qd_mcp_client import call_qd_tool

    snapshot = call_qd_tool("qd_get_market_snapshot", {"ticker": "SPY"})
    print(snapshot["text"])

    dp_floors = call_qd_tool("qd_get_dark_pool_levels", {"ticker": "NVDA"})
    gex       = call_qd_tool("qd_get_exposure_by_strike", {"ticker": "MSFT"})

Available tools (quantdata-mcp v1.27.0 — 47 tools)
---------------------------------------------------
Market overview:    qd_get_market_snapshot, qd_get_net_drift, qd_get_dark_pool_levels
GEX / DEX / CEX:   qd_get_exposure_by_strike, qd_get_exposure_by_expiration
Order flow:         qd_get_order_flow, qd_get_unconsolidated_flow, qd_get_heat_map,
                    qd_get_interval_map, qd_get_gainers_losers
Volatility:         qd_get_volatility_skew, qd_get_term_structure, qd_get_volatility_drift
OI / Max Pain:      qd_get_oi_change, qd_get_oi_by_expiration, qd_get_oi_over_time,
                    qd_get_max_pain_over_time
Contract detail:    qd_get_contract_price, qd_get_contract_statistics
Equity tape:        qd_get_equity_prints, qd_get_stock_price_time
News:               qd_get_news_articles
Page management:    qd_create_page, qd_list_pages, qd_add_tool_to_page, qd_run_page,
                    qd_delete_page, qd_set_page_date
Filter groups:      qd_list_filter_groups, qd_get_filter_group, qd_save_filter_group,
                    qd_update_filter_group, qd_delete_filter_group, qd_apply_filter_group,
                    qd_detach_filter_group, qd_clone_public_filter_group,
                    qd_search_public_filter_groups, qd_add_filter_clause,
                    qd_remove_filter_clause, qd_update_filter_clause, qd_list_filter_fields,
                    qd_save_filter_group_advanced, qd_add_or_branch
Time control:       qd_set_tool_time, qd_reset_to_live

Notes
-----
- Each call_qd_tool() invocation spawns a fresh subprocess. For bulk calls,
  consider using the persistent client pattern (see examples/qd_bulk_fetch.py).
- The QuantData JWT token expires periodically. Re-login at v3.quantdata.us
  and update ~/.quantdata-mcp/config.json if you receive 401 errors.
- GEX strike maps are empty outside market hours — this is expected QuantData
  behaviour. Dark Pool floors are persistent and always available.
"""
from __future__ import annotations

import json
import subprocess
import time
from typing import Any


def call_qd_tool(tool_name: str, args: dict[str, Any] | None = None, timeout: float = 10.0) -> dict:
    """
    Call a QuantData MCP tool via the quantdata-mcp stdio server.

    Parameters
    ----------
    tool_name : str
        The canonical MCP tool name, e.g. ``"qd_get_market_snapshot"``.
    args : dict, optional
        Tool arguments. Defaults to an empty dict (uses QuantData defaults:
        ticker=SPX, date=today, expiration=0DTE).
    timeout : float
        Seconds to wait for the tool response. Default 10s. Increase for
        slow tools like ``qd_get_order_flow`` with large date ranges.

    Returns
    -------
    dict
        Parsed JSON response from the tool, or ``{"text": "<raw text>"}``
        if the response is plain text, or ``{"error": "<message>"}`` on failure.
    """
    proc = subprocess.Popen(
        ["quantdata-mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def _send_recv(msg: dict, wait: float = 1.5) -> dict:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        time.sleep(wait)
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else {}

    try:
        # MCP handshake
        _send_recv({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fortress-mcp-client", "version": "1.0"},
            },
        })

        # Tool call
        result = _send_recv(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args or {}},
            },
            wait=timeout,
        )

        if "error" in result:
            return {"error": result["error"].get("message", str(result["error"]))}

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            raw = content[0]["text"]
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"text": raw}

        return result

    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        proc.terminate()


if __name__ == "__main__":
    # Quick smoke test — run with: python3 qd_mcp_client.py
    print("Testing qd_get_market_snapshot for SPY...")
    r = call_qd_tool("qd_get_market_snapshot", {"ticker": "SPY"})
    text = r.get("text", json.dumps(r, indent=2))
    print(text[:2000])
