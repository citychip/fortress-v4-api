"""
QuantData Daily Options Market Data Pipeline
Portfolio Strategy v3.2 — the trader YOUR_IBKR_ACCOUNT_ID

Collects and summarizes options market data each trading day:
  - SPX/SPY macro regime (GEX walls, net drift, OI, net flow)
  - IV Rank for all active names (entry eligibility filter)
  - Order flow statistics (call vs put premium bias)
  - Strategy-specific flags (IVR gate, regime, put spread eligibility)

Output: Markdown report saved to ~/quantdata_reports/QuantData_YYYY-MM-DD.md
"""

import json
import pathlib
from datetime import datetime, timezone, timedelta
from curl_cffi import requests
import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_PATH = pathlib.Path.home() / ".quantdata-mcp" / "config.json"
REPORTS_DIR = pathlib.Path.home() / "quantdata_reports"
REPORTS_DIR.mkdir(exist_ok=True)

config = json.loads(CONFIG_PATH.read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
PAGE_ID = config["page_id"]
TOOLS = config["tools"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"
USER_ID = "a7da66dc-7c6e-4e72-bc1e-555e686adc72"

HEADERS = {
    "accept": "application/json",
    "authorization": TOKEN,
    "cookie": COOKIE,
    "origin": "https://v3.quantdata.us",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "content-type": "application/json",
}

# Active universe from Portfolio Strategy v3.2 §3
TICKERS = {
    "macro": ["SPX", "SPY"],
    "tier1": ["MSFT", "AVGO", "NFLX", "VST", "GOOGL", "AMZN", "AMD", "MSTR"],
    "tier2": ["META", "AAPL", "NVDA"],
}
ALL_TICKERS = TICKERS["macro"] + TICKERS["tier1"] + TICKERS["tier2"]
TIER_MAP = {t: "Macro" for t in TICKERS["macro"]}
TIER_MAP.update({t: "Tier 1" for t in TICKERS["tier1"]})
TIER_MAP.update({t: "Tier 2" for t in TICKERS["tier2"]})

# ET timezone (UTC-4 in summer / UTC-5 in winter)
ET = timezone(timedelta(hours=-4))

# ─────────────────────────────────────────────────────────────────────────────
# API Client
# ─────────────────────────────────────────────────────────────────────────────

session = requests.Session(impersonate="chrome110")
session.headers.update(HEADERS)


def fetch(endpoint: str, tool_key: str) -> dict:
    """Fetch data from a QuantData tool endpoint."""
    tid = TOOLS.get(tool_key)
    if not tid:
        return {}
    try:
        resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=20)
        if resp.status_code == 200:
            return resp.json().get("response", {})
    except Exception as e:
        print(f"  [WARN] Failed to fetch {tool_key}: {e}")
    return {}


# Tool type metadata templates
TOOL_METADATA_TEMPLATES = {
    "OPTIONS_IV_RANK_CHART": lambda ticker: {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "lookBackPeriod": 365,
        "maturity": 30,
        "type": "OPTIONS_IV_RANK_CHART",
    },
    "OPTIONS_EXPOSURE_BY_STRIKE_CHART": lambda ticker: {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "greekModeType": "GAMMA",
        "isNet": True,
        "representationModeType": "PER_ONE_PERCENT_MOVE",
        "type": "OPTIONS_EXPOSURE_BY_STRIKE_CHART",
    },
    "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART": lambda ticker: {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "type": "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART",
    },
    "OPTIONS_NET_FLOW_CHART": lambda ticker: {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "type": "OPTIONS_NET_FLOW_CHART",
    },
    "OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE": lambda ticker: {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "type": "OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE",
    },
}


def update_tool_ticker(tool_key: str, ticker: str, tool_type: str, created_time: int):
    """Switch a tool's ticker filter by updating its metadata via PUT /api/tool."""
    tid = TOOLS.get(tool_key)
    if not tid:
        return
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    template_fn = TOOL_METADATA_TEMPLATES.get(tool_type)
    if template_fn:
        metadata = template_fn(ticker)
    else:
        metadata = {
            "filter": {
                "contractType": {"filterOperationType": "EQUALS", "value": []},
                "ticker": {"filterOperationType": "EQUALS", "value": ticker},
            },
            "lookBackPeriod": 365,
            "maturity": 30,
            "type": tool_type,
        }
    payload = {
        "id": tid,
        "userId": USER_ID,
        "filterGroupIds": [],
        "metadata": metadata,
        "pageId": PAGE_ID,
        "createdTime": created_time,
        "lastUpdatedTime": now_ms,
    }
    try:
        session.put(f"{BASE_URL}/tool", json=payload, timeout=10)
    except Exception as e:
        print(f"  [WARN] Failed to update tool filter for {ticker}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Data Extraction Helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_iv_rank(data: dict, date: str) -> dict:
    """Extract today's IV rank data for calls and puts."""
    ivr_map = data.get("sessionDateToIVRankData", {})
    today_data = ivr_map.get(date, {})
    price = data.get("stockPriceInCents", 0) / 100
    ct_data = today_data.get("contractTypeToIVData", {})

    call_iv = ct_data.get("CALL", {})
    put_iv = ct_data.get("PUT", {})

    def calc_ivr(iv_dict):
        last = iv_dict.get("lastIV", 0)
        lo = iv_dict.get("windowMinIV", 0)
        hi = iv_dict.get("windowMaxIV", 1)
        if hi > lo:
            return round((last - lo) / (hi - lo) * 100, 1)
        return 0.0

    call_ivr = calc_ivr(call_iv)
    put_ivr = calc_ivr(put_iv)
    avg_ivr = round((call_ivr + put_ivr) / 2, 1) if (call_ivr or put_ivr) else 0.0

    return {
        "price": price,
        "call_iv": round(call_iv.get("lastIV", 0), 2),
        "put_iv": round(put_iv.get("lastIV", 0), 2),
        "call_ivr": call_ivr,
        "put_ivr": put_ivr,
        "avg_ivr": avg_ivr,
        "eligible_put_spread": avg_ivr >= 25,
    }


def extract_net_drift(data: dict) -> dict:
    """Extract net drift summary — cumulative direction."""
    entries = data.get("netDrift", [])
    if not entries:
        return {"direction": "N/A", "call_premium_cum": 0, "put_premium_cum": 0,
                "net_premium": 0, "entry_count": 0}

    call_cum = sum(e[1] for e in entries if len(e) > 1)
    put_cum = sum(e[2] for e in entries if len(e) > 2)
    net = call_cum - put_cum
    direction = "BULLISH" if net > 0 else "BEARISH"

    return {
        "direction": direction,
        "call_premium_cum": round(call_cum / 1e6, 2),
        "put_premium_cum": round(put_cum / 1e6, 2),
        "net_premium": round(net / 1e6, 2),
        "entry_count": len(entries),
    }


def extract_net_flow(data: dict) -> dict:
    """Extract net flow summary — cumulative call vs put flow."""
    entries = data.get("netFlow", [])
    if not entries:
        return {"call_flow": 0, "put_flow": 0, "bias": "N/A", "ratio": 0}

    call_total = sum(e[1] for e in entries if len(e) > 1)
    put_total = sum(e[2] for e in entries if len(e) > 2)
    bias = "CALL-HEAVY" if call_total > put_total else "PUT-HEAVY"

    return {
        "call_flow": round(call_total / 1e6, 2),
        "put_flow": round(put_total / 1e6, 2),
        "bias": bias,
        "ratio": round(call_total / put_total, 2) if put_total else 0,
    }


def extract_gex_walls(data: dict, top_n: int = 5) -> dict:
    """Extract top GEX walls by strike."""
    exp_map = data.get("expirationDateToStrikePriceInCentsToContractExposureMap", {})
    price = data.get("stockPriceInCents", 0) / 100

    strike_totals = {}
    for exp_date, strikes in exp_map.items():
        for strike_cents, ct_data in strikes.items():
            strike = int(strike_cents) / 100
            call_exp = ct_data.get("CALL", 0)
            put_exp = ct_data.get("PUT", 0)
            if strike not in strike_totals:
                strike_totals[strike] = {"call": 0, "put": 0}
            strike_totals[strike]["call"] += call_exp
            strike_totals[strike]["put"] += put_exp

    net_gex = {s: d["call"] + d["put"] for s, d in strike_totals.items()}
    sorted_strikes = sorted(net_gex.items(), key=lambda x: x[1], reverse=True)
    call_walls = [(s, round(v / 1e6, 1)) for s, v in sorted_strikes if v > 0][:top_n]
    put_walls = [(s, round(v / 1e6, 1)) for s, v in sorted_strikes if v < 0][:top_n]
    near_zero = sorted(net_gex.items(), key=lambda x: abs(x[1]))
    flip_zone = near_zero[0][0] if near_zero else None

    return {
        "price": price,
        "call_walls": call_walls,
        "put_walls": put_walls,
        "flip_zone": flip_zone,
    }


def extract_oi_walls(data: dict, top_n: int = 5) -> dict:
    """Extract top OI strikes for calls and puts."""
    oi_map = data.get("strikePricesInCentsToPutCallOpenInterest", {})
    call_oi = {}
    put_oi = {}
    for strike_cents, d in oi_map.items():
        strike = int(strike_cents) / 100
        call_oi[strike] = d.get("callOpenInterest", 0)
        put_oi[strike] = d.get("putOpenInterest", 0)

    top_calls = sorted(call_oi.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_puts = sorted(put_oi.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return {"top_call_oi": top_calls, "top_put_oi": top_puts}


def extract_order_flow(data: dict) -> dict:
    """Extract order flow statistics — call vs put premium by trade side."""
    stats = data.get("statistics", {}).get(
        "optionsOrderFlowContractTradeSideStatisticsSumMap", {}
    )

    def sum_premium(ct_stats):
        return sum(d.get("premiumInCentsSum", 0) for d in ct_stats.values()) / 1e8

    call_premium = sum_premium(stats.get("CALL", {}))
    put_premium = sum_premium(stats.get("PUT", {}))
    bias = "CALL-HEAVY" if call_premium > put_premium else "PUT-HEAVY"
    call_aa = stats.get("CALL", {}).get("AA", {}).get("premiumInCentsSum", 0) / 1e8
    put_bb = stats.get("PUT", {}).get("BB", {}).get("premiumInCentsSum", 0) / 1e8

    return {
        "call_premium_M": round(call_premium, 2),
        "put_premium_M": round(put_premium, 2),
        "bias": bias,
        "aggressive_call_buy_M": round(call_aa, 2),
        "aggressive_put_sell_M": round(put_bb, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-Ticker IV Rank Collection
# ─────────────────────────────────────────────────────────────────────────────

# Fetch the IV rank tool's creation time once (needed for PUT updates)
def get_tool_created_time(tool_key: str) -> int:
    tid = TOOLS.get(tool_key)
    try:
        resp = session.get(f"{BASE_URL}/tool/{tid}", timeout=10)
        if resp.status_code == 200:
            return resp.json()["response"]["toolDTO"]["createdTime"]
    except Exception:
        pass
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def collect_ticker_data(date: str) -> dict:
    """Collect IV rank, GEX/OI, Dark Pool, and Flow for all tickers."""
    created_time = get_tool_created_time("iv_rank")
    results = {}
    
    today_et = datetime.now(ET).strftime("%Y-%m-%d")
    start_90d = (datetime.now(ET) - timedelta(days=90)).strftime("%Y-%m-%d")

    for ticker in ALL_TICKERS:
        print(f"  Fetching data for: {ticker}...")
        ticker_data = {}
        
        # 1. IV Rank (also used for HV vs IV)
        update_tool_ticker("iv_rank", ticker, "OPTIONS_IV_RANK_CHART", created_time)
        iv_data = fetch("options/iv-rank", "iv_rank")
        if iv_data:
            ticker_data["iv"] = extract_iv_rank(iv_data, date)
            
        # 2. GEX by Strike
        update_tool_ticker("exposure_by_strike", ticker, "OPTIONS_EXPOSURE_BY_STRIKE_CHART", created_time)
        gex_data = fetch("options/exposure/strike", "exposure_by_strike")
        if gex_data:
            ticker_data["gex"] = extract_gex_walls(gex_data, top_n=3)
            
        # 3. OI by Strike
        update_tool_ticker("oi_by_strike", ticker, "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART", created_time)
        oi_data = fetch("options/open-interest/strike", "oi_by_strike")
        if oi_data:
            ticker_data["oi"] = extract_oi_walls(oi_data, top_n=3)
            
        # 4. Dark Pool Levels
        # Need custom update payload for dark pool due to date range
        dp_id = TOOLS.get("dark_pool_levels")
        if dp_id:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            payload = {
                "id": dp_id,
                "userId": USER_ID,
                "filterGroupIds": [],
                "metadata": {
                    "tableMetadata": {"sort": {"field": "PRICE_IN_CENTS", "sortDirectionType": "DESCENDING"}},
                    "filter": {"ticker": {"filterOperationType": "EQUALS", "value": ticker}},
                    "maximumLevelCount": 50,
                    "sessionDateStart": start_90d,
                    "sessionDateEnd": today_et,
                    "type": "DARK_POOL_LEVELS_TABLE"
                },
                "pageId": PAGE_ID,
                "createdTime": created_time,
                "lastUpdatedTime": now_ms,
            }
            try:
                session.put(f"{BASE_URL}/tool", json=payload, timeout=10)
                dp_data = fetch("equities/dark-pool/levels", "dark_pool_levels")
                if dp_data:
                    levels_map = dp_data.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
                    sorted_levels = sorted(levels_map.items(), key=lambda x: x[1].get("notionalValueInCentsSum", 0), reverse=True)
                    top_levels = [(int(k)/100, v.get("notionalValueInCentsSum", 0)/1e8) for k, v in sorted_levels[:3]]
                    ticker_data["dark_pool"] = top_levels
            except Exception as e:
                print(f"    [WARN] Failed DP for {ticker}: {e}")

        # 5. Live Whale Flow (Net Flow) - only for Tier 1
        if ticker in TICKERS["tier1"]:
            update_tool_ticker("net_flow", ticker, "OPTIONS_NET_FLOW_CHART", created_time)
            nf_data = fetch("options/net-flow", "net_flow")
            if nf_data:
                ticker_data["whale_flow"] = extract_net_flow(nf_data)
                
        results[ticker] = ticker_data

    # Reset tools to SPX
    update_tool_ticker("iv_rank", "SPX", "OPTIONS_IV_RANK_CHART", created_time)
    update_tool_ticker("exposure_by_strike", "SPX", "OPTIONS_EXPOSURE_BY_STRIKE_CHART", created_time)
    update_tool_ticker("oi_by_strike", "SPX", "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART", created_time)
    
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Report Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(date: str, ticker_data_map: dict, spx_gex: dict, spx_drift: dict,
                    spx_flow: dict, spx_oi: dict, spx_order_flow: dict) -> str:
    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    price = spx_gex.get("price", 0)
    flip = spx_gex.get("flip_zone")
    call_walls = spx_gex.get("call_walls", [])
    put_walls = spx_gex.get("put_walls", [])
    top_call_oi = spx_oi.get("top_call_oi", [])
    top_put_oi = spx_oi.get("top_put_oi", [])

    drift_dir = spx_drift.get("direction", "N/A")
    drift_icon = "🟢" if drift_dir == "BULLISH" else "🔴"
    flow_bias = spx_flow.get("bias", "N/A")
    flow_icon = "🟢" if flow_bias == "CALL-HEAVY" else "🔴"
    of_bias = spx_order_flow.get("bias", "N/A")
    of_icon = "🟢" if of_bias == "CALL-HEAVY" else "🔴"

    bullish_signals = sum([
        drift_dir == "BULLISH",
        flow_bias == "CALL-HEAVY",
        of_bias == "CALL-HEAVY",
    ])
    regime = "BULLISH" if bullish_signals >= 2 else "BEARISH"
    regime_icon = "🟢" if regime == "BULLISH" else "🔴"

    eligible_tickers = [t for t in ALL_TICKERS if ticker_data_map.get(t, {}).get("iv") and ticker_data_map[t]["iv"]["eligible_put_spread"]]
    ineligible_tickers = [t for t in ALL_TICKERS if ticker_data_map.get(t, {}).get("iv") and not ticker_data_map[t]["iv"]["eligible_put_spread"]]

    lines = [
        f"# QuantData Daily Report — {date}",
        f"*Generated: {now_et} | Portfolio Strategy v3.2*",
        "",
        "---",
        "",
        "## 1. Macro Regime — SPX",
        "",
        f"**Current Price:** ${price:,.2f}" + (f"  |  **GEX Flip Zone:** ${flip:,.0f}" if flip else ""),
        "",
        "### GEX Walls (Gamma Exposure)",
        "",
        "| Side | Strike | Net GEX ($M) |",
        "|------|--------|--------------|",
    ]
    for s, v in call_walls:
        lines.append(f"| Call Wall | ${s:,.0f} | +{v} |")
    for s, v in put_walls:
        lines.append(f"| Put Wall  | ${s:,.0f} | {v} |")

    lines += [
        "",
        "### Open Interest Walls",
        "",
        "| Side | Strike | OI Contracts |",
        "|------|--------|--------------|",
    ]
    for s, v in top_call_oi[:3]:
        lines.append(f"| Call OI | ${s:,.0f} | {v:,} |")
    for s, v in top_put_oi[:3]:
        lines.append(f"| Put OI  | ${s:,.0f} | {v:,} |")

    lines += [
        "",
        "### Net Drift (Cumulative Premium Flow)",
        "",
        f"**Direction:** {drift_icon} {drift_dir}",
        f"- Call Premium: ${spx_drift.get('call_premium_cum', 0):.1f}M",
        f"- Put Premium: ${spx_drift.get('put_premium_cum', 0):.1f}M",
        f"- Net: ${spx_drift.get('net_premium', 0):.1f}M",
        f"- Data points: {spx_drift.get('entry_count', 0)}",
        "",
        "### Net Flow",
        "",
        f"**Bias:** {flow_icon} {flow_bias}",
        f"- Call Flow: ${spx_flow.get('call_flow', 0):.1f}M",
        f"- Put Flow: ${spx_flow.get('put_flow', 0):.1f}M",
        f"- Call/Put Ratio: {spx_flow.get('ratio', 0):.2f}x",
        "",
        "### Order Flow Statistics",
        "",
        f"**Premium Bias:** {of_icon} {of_bias}",
        f"- Total Call Premium: ${spx_order_flow.get('call_premium_M', 0):.2f}M",
        f"- Total Put Premium: ${spx_order_flow.get('put_premium_M', 0):.2f}M",
        f"- Aggressive Call Buys (AA): ${spx_order_flow.get('aggressive_call_buy_M', 0):.2f}M",
        f"- Aggressive Put Sells (BB): ${spx_order_flow.get('aggressive_put_sell_M', 0):.2f}M",
        "",
        "---",
        "",
        "## 2. IV Rank — Entry Eligibility (§4 Quality Filter)",
        "",
        "> **Rule:** IVR > 25 required before entering new put credit spreads or Jade Lizards.",
        "",
        "| Ticker | Tier | Price | Call IV | Put IV | Avg IVR | Put Spread Eligible |",
        "|--------|------|-------|---------|--------|---------|---------------------|",
    ]

    for ticker in ALL_TICKERS:
        d = ticker_data_map.get(ticker, {}).get("iv")
        if d:
            eligible = "✅ YES" if d["eligible_put_spread"] else "❌ NO"
            # Simulate HV vs IV comparison (since HV isn't directly exposed in the same endpoint, we use IV rank as proxy for now)
            iv_crush = "🔥 CRUSH" if d["avg_ivr"] > 50 else "-"
            lines.append(
                f"| {ticker} | {TIER_MAP.get(ticker, '-')} | ${d['price']:,.2f} | "
                f"{d['call_iv']:.1f}% | {d['put_iv']:.1f}% | {d['avg_ivr']:.1f} | {eligible} | {iv_crush} |"
            )
        else:
            lines.append(f"| {ticker} | {TIER_MAP.get(ticker, '-')} | N/A | N/A | N/A | N/A | ❓ | - |")

    lines += [
        "",
        "---",
        "",
        "## 3. Tier 1 & 2 Execution Engines (GEX, Dark Pools, Whale Flow)",
        "",
        "> **Workflow:** Cross-reference GEX/OI walls with Clean Decision Chart technicals. Watch Dark Pool levels as Hard Floors. Confirm Whale Flow bias before entry.",
        ""
    ]

    for ticker in TICKERS["tier1"] + TICKERS["tier2"]:
        tdata = ticker_data_map.get(ticker, {})
        gex = tdata.get("gex", {})
        oi = tdata.get("oi", {})
        dp = tdata.get("dark_pool", [])
        wf = tdata.get("whale_flow", {})
        
        lines.append(f"### {ticker} Execution Profile")
        
        # Dark Pool
        if dp:
            dp_str = ", ".join([f"${p:,.2f} ({v:.1f}M)" for p, v in dp])
            lines.append(f"- **Dark Pool Hard Floors:** {dp_str}")
        
        # Whale Flow
        if wf:
            bias = wf.get("bias", "N/A")
            icon = "🟢" if bias == "CALL-HEAVY" else "🔴"
            lines.append(f"- **Live Whale Flow:** {icon} {bias} (Call/Put Ratio: {wf.get('ratio', 0):.2f}x)")
            
        # GEX / OI Walls
        cw = gex.get("call_walls", [])
        pw = gex.get("put_walls", [])
        cw_str = ", ".join([f"${s:,.0f}" for s, v in cw]) if cw else "None"
        pw_str = ", ".join([f"${s:,.0f}" for s, v in pw]) if pw else "None"
        lines.append(f"- **GEX Walls:** Calls at {cw_str} | Puts at {pw_str}")
        
        lines.append("")

    lines += [
        "",
        "---",
        "",
        "## 3. Strategy Flags",
        "",
        f"**Put Spread / Jade Lizard Eligible (IVR ≥ 25):** {', '.join(eligible_tickers) if eligible_tickers else 'None'}",
        f"**Below IVR Threshold (IVR < 25):** {', '.join(ineligible_tickers) if ineligible_tickers else 'None'}",
        "",
        "### Macro Regime Summary",
        "",
        "| Signal | Value |",
        "|--------|-------|",
        f"| Net Drift | {drift_icon} {drift_dir} |",
        f"| Net Flow | {flow_icon} {flow_bias} |",
        f"| Order Flow | {of_icon} {of_bias} |",
        f"| **Overall Regime** | **{regime_icon} {regime}** |",
        "",
        f"> **{bullish_signals}/3 bullish signals** — "
        f"{'Proceed with new entries per strategy rules.' if bullish_signals >= 2 else 'Caution: bearish regime. Pause new entries unless VIX confirms.'}",
        "",
        "---",
        "",
        f"*End of QuantData Daily Report — {date}*",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# AI Summary
# ─────────────────────────────────────────────────────────────────────────────

def generate_ai_summary(report_md: str) -> str:
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=400,
            system=(
                "You are a quantitative options analyst assistant for the trader, "
                "who runs a PMCC/diagonal/put-credit-spread/Jade Lizard portfolio "
                "(Portfolio Strategy v3.2). Summarize the QuantData report in 3-5 "
                "concise bullet points focused on actionable insights: "
                "regime direction, which tickers are eligible for new put spreads, "
                "and any notable GEX/drift signals. Be direct and brief."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Summarize this QuantData daily report:

{report_md[:3000]}",
                },
            ],
        )
        return response.content[0].text
    except Exception as e:
        return f"AI summary unavailable: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"QuantData Daily Pipeline — {today}")
    print(f"{'='*60}\n")

    # 1. Collect all per-ticker data (IV, GEX, Dark Pool, Whale Flow)
    print("Step 1: Collecting per-ticker data engines...")
    ticker_data_map = collect_ticker_data(today)

    # 2. Collect SPX macro data (reset tool to SPX first)
    print("\nStep 2: Collecting SPX macro data...")
    iv_created = get_tool_created_time("iv_rank")
    update_tool_ticker("iv_rank", "SPX", "OPTIONS_IV_RANK_CHART", iv_created)

    print("  Fetching GEX/exposure by strike...")
    gex_raw = fetch("options/exposure/strike", "exposure_by_strike")
    spx_gex = extract_gex_walls(gex_raw)

    print("  Fetching net drift...")
    drift_raw = fetch("options/net-drift", "net_drift")
    spx_drift = extract_net_drift(drift_raw)

    print("  Fetching net flow...")
    flow_raw = fetch("options/net-flow", "net_flow")
    spx_flow = extract_net_flow(flow_raw)

    print("  Fetching OI by strike...")
    oi_raw = fetch("options/open-interest/strike", "oi_by_strike")
    spx_oi = extract_oi_walls(oi_raw)

    print("  Fetching order flow...")
    of_raw = fetch("options/order-flow/consolidated", "order_flow")
    spx_order_flow = extract_order_flow(of_raw)

    # 3. Generate report
    print("\nStep 3: Generating report...")
    report_md = generate_report(
        today, ticker_data_map, spx_gex, spx_drift, spx_flow, spx_oi, spx_order_flow
    )

    # 4. AI summary
    print("Step 4: Generating AI summary...")
    ai_summary = generate_ai_summary(report_md)
    full_report = f"## AI Summary\n\n{ai_summary}\n\n---\n\n{report_md}"

    # 5. Save report
    report_path = REPORTS_DIR / f"QuantData_{today}.md"
    report_path.write_text(full_report)
    print(f"\nReport saved: {report_path}")

    print("\n" + "="*60)
    print("AI SUMMARY:")
    print("="*60)
    print(ai_summary)
    print("="*60)

    return str(report_path)


if __name__ == "__main__":
    run_pipeline()
