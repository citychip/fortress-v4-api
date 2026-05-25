"""
QuantData Daily GEX & OI Profile Report
Generates a focused report of Gamma Exposure walls, Open Interest walls,
and Dark Pool hard floors for all tickers in Portfolio Strategy v3.2.
"""

import json
import pathlib
import time
from datetime import datetime, timezone, timedelta
from curl_cffi import requests
import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH = pathlib.Path.home() / ".quantdata-mcp" / "config.json"
config = json.loads(CONFIG_PATH.read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
PAGE_ID = config["page_id"]
TOOLS = config["tools"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"
USER_ID = "a7da66dc-7c6e-4e72-bc1e-555e686adc72"
ET = timezone(timedelta(hours=-4))

HEADERS = {
    "accept": "application/json",
    "authorization": TOKEN,
    "cookie": COOKIE,
    "origin": "https://v3.quantdata.us",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "content-type": "application/json",
}
session = requests.Session(impersonate="chrome110")
session.headers.update(HEADERS)

# Tickers from Portfolio Strategy v3.2
TICKERS = {
    "macro":  ["SPX", "SPY"],
    "tier1":  ["MSFT", "AVGO", "NFLX", "VST", "UNH", "GOOGL", "AMZN", "AMD", "MSTR"],
    "tier2":  ["META", "AAPL", "NVDA"],
}
ALL_TICKERS = TICKERS["macro"] + TICKERS["tier1"] + TICKERS["tier2"]
TIER_MAP = {t: "Macro" for t in TICKERS["macro"]}
TIER_MAP.update({t: "Tier 1" for t in TICKERS["tier1"]})
TIER_MAP.update({t: "Tier 2" for t in TICKERS["tier2"]})

REPORT_DIR = pathlib.Path.home() / "quantdata_reports"
REPORT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# API Helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_tool_created_time(tool_key: str) -> int:
    try:
        tid = TOOLS.get(tool_key)
        if tid:
            resp = session.get(f"{BASE_URL}/tool/{tid}", timeout=10)
            if resp.status_code == 200:
                return resp.json()["response"]["toolDTO"]["createdTime"]
    except Exception:
        pass
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def update_tool(tool_key: str, metadata: dict, created_time: int):
    tid = TOOLS.get(tool_key)
    if not tid:
        return
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
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
        print(f"  [WARN] update_tool failed: {e}")


def fetch(endpoint: str, tool_key: str) -> dict:
    tid = TOOLS.get(tool_key)
    if not tid:
        return {}
    try:
        resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=12)
        if resp.status_code == 200:
            return resp.json().get("response", {})
    except Exception as e:
        print(f"  [WARN] fetch {tool_key}: {e}")
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Data Collection
# ─────────────────────────────────────────────────────────────────────────────
def collect_gex_oi_dp(ticker: str, created_time: int, today_et: str, start_90d: str) -> dict:
    """Collect GEX, OI, and Dark Pool data for a single ticker."""
    result = {}

    # GEX by Strike
    gex_meta = {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "greekModeType": "GAMMA",
        "isNet": True,
        "representationModeType": "PER_ONE_PERCENT_MOVE",
        "type": "OPTIONS_EXPOSURE_BY_STRIKE_CHART",
    }
    update_tool("exposure_by_strike", gex_meta, created_time)
    gex_data = fetch("options/exposure/strike", "exposure_by_strike")
    if gex_data:
        result["gex"] = extract_gex(gex_data)

    # OI by Strike
    oi_meta = {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "type": "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART",
    }
    update_tool("oi_by_strike", oi_meta, created_time)
    oi_data = fetch("options/open-interest/strike", "oi_by_strike")
    if oi_data:
        result["oi"] = extract_oi(oi_data)

    # Dark Pool Levels
    dp_id = TOOLS.get("dark_pool_levels")
    if dp_id:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dp_payload = {
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
            session.put(f"{BASE_URL}/tool", json=dp_payload, timeout=10)
            dp_data = fetch("equities/dark-pool/levels", "dark_pool_levels")
            if dp_data:
                levels_map = dp_data.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
                sorted_levels = sorted(
                    levels_map.items(),
                    key=lambda x: x[1].get("notionalValueInCentsSum", 0),
                    reverse=True
                )
                result["dark_pool"] = [
                    (int(k) / 100, v.get("notionalValueInCentsSum", 0) / 1e8)
                    for k, v in sorted_levels[:5]
                ]
                result["price"] = dp_data.get("stockPriceInCents", 0) / 100
        except Exception as e:
            print(f"  [WARN] Dark Pool for {ticker}: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Extraction Helpers
# ─────────────────────────────────────────────────────────────────────────────
def extract_gex(data: dict, top_n: int = 5) -> dict:
    exp_map = data.get("expirationDateToStrikePriceInCentsToContractExposureMap", {})
    price = data.get("stockPriceInCents", 0) / 100
    strike_totals = {}
    for exp_date, strikes in exp_map.items():
        for sc, ct_data in strikes.items():
            s = int(sc) / 100
            strike_totals[s] = strike_totals.get(s, 0) + ct_data.get("CALL", 0) + ct_data.get("PUT", 0)
    sorted_s = sorted(strike_totals.items(), key=lambda x: x[1], reverse=True)
    call_walls = [(s, round(v / 1e6, 1)) for s, v in sorted_s if v > 0][:top_n]
    put_walls  = [(s, round(v / 1e6, 1)) for s, v in sorted_s if v < 0][:top_n]
    near_zero  = sorted(strike_totals.items(), key=lambda x: abs(x[1]))
    flip_zone  = near_zero[0][0] if near_zero else None
    return {"price": price, "call_walls": call_walls, "put_walls": put_walls, "flip_zone": flip_zone}


def extract_oi(data: dict, top_n: int = 5) -> dict:
    oi_map = data.get("strikePricesInCentsToPutCallOpenInterest", {})
    call_oi, put_oi = {}, {}
    for sc, d in oi_map.items():
        s = int(sc) / 100
        call_oi[s] = d.get("callOpenInterest", 0)
        put_oi[s]  = d.get("putOpenInterest", 0)
    top_calls = sorted(call_oi.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_puts  = sorted(put_oi.items(),  key=lambda x: x[1], reverse=True)[:top_n]
    return {"top_call_oi": top_calls, "top_put_oi": top_puts}


# ─────────────────────────────────────────────────────────────────────────────
# Report Generation
# ─────────────────────────────────────────────────────────────────────────────
def generate_report(date: str, ticker_profiles: dict) -> str:
    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")

    lines = [
        f"# QuantData GEX & OI Profile Report — {date}",
        f"*Generated: {now_et} | Portfolio Strategy v3.2*",
        "",
        "> **How to use:** GEX Call Walls act as price ceilings where dealer hedging creates resistance. "
        "GEX Put Walls are support zones. Dark Pool Hard Floors are institutional price anchors — "
        "treat a break of the top Dark Pool level as a Thesis Stop. "
        "OI walls mark where the most contracts are concentrated, often acting as pinning targets near expiry.",
        "",
        "---",
        "",
    ]

    for ticker in ALL_TICKERS:
        d = ticker_profiles.get(ticker, {})
        gex = d.get("gex", {})
        oi  = d.get("oi", {})
        dp  = d.get("dark_pool", [])
        price = d.get("price", gex.get("price", 0))
        tier  = TIER_MAP.get(ticker, "-")

        lines.append(f"## {ticker} — {tier}")
        if price:
            lines.append(f"**Current Price:** ${price:,.2f}")
        lines.append("")

        # GEX Section
        lines.append("### Gamma Exposure (GEX) Walls")
        call_walls = gex.get("call_walls", [])
        put_walls  = gex.get("put_walls", [])
        flip_zone  = gex.get("flip_zone")

        if call_walls or put_walls:
            lines.append("| Side | Strike | Net GEX ($M) | vs Price |")
            lines.append("|------|--------|--------------|----------|")
            for s, v in call_walls:
                diff = f"+{s - price:.1f}" if price else "—"
                lines.append(f"| 📈 Call Wall | ${s:,.0f} | +{v:.1f} | {diff} |")
            for s, v in put_walls:
                diff = f"{s - price:.1f}" if price else "—"
                lines.append(f"| 📉 Put Wall  | ${s:,.0f} | {v:.1f} | {diff} |")
        else:
            lines.append("*No significant GEX walls detected.*")

        if flip_zone and price:
            direction = "above" if price > flip_zone else "below"
            lines.append(f"\n**GEX Flip Zone:** ${flip_zone:,.0f} — Price is **{direction}** the flip zone.")

        lines.append("")

        # OI Section
        lines.append("### Open Interest (OI) Walls")
        top_calls = oi.get("top_call_oi", [])
        top_puts  = oi.get("top_put_oi", [])

        if top_calls or top_puts:
            lines.append("| Side | Strike | OI Contracts | vs Price |")
            lines.append("|------|--------|--------------|----------|")
            for s, v in top_calls:
                diff = f"+{s - price:.1f}" if price else "—"
                lines.append(f"| 📈 Call OI | ${s:,.0f} | {v:,} | {diff} |")
            for s, v in top_puts:
                diff = f"{s - price:.1f}" if price else "—"
                lines.append(f"| 📉 Put OI  | ${s:,.0f} | {v:,} | {diff} |")
        else:
            lines.append("*No OI data available.*")

        lines.append("")

        # Dark Pool Section
        lines.append("### Dark Pool Hard Floors")
        if dp:
            lines.append("| Rank | Price Level | Notional Volume ($M) | vs Price |")
            lines.append("|------|-------------|----------------------|----------|")
            for i, (p, vol) in enumerate(dp, 1):
                diff = f"{p - price:.2f}" if price else "—"
                marker = " ← **Thesis Stop**" if i == 1 else ""
                lines.append(f"| #{i} | ${p:,.2f} | {vol:.1f}M{marker} | {diff} |")
        else:
            lines.append("*No Dark Pool data available.*")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_ai_commentary(report_text: str) -> str:
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=600,
            system=(
                "You are a senior options strategist analyzing QuantData GEX and OI profiles "
                "for Portfolio Strategy v3.2. The strategy sells premium via put credit spreads, "
                "PMCCs, diagonals, and Jade Lizards on high-IV stocks. "
                "GEX Call Walls = resistance (safe zone for short calls above). "
                "GEX Put Walls = support (safe zone for short puts below). "
                "Dark Pool floors = hard institutional support — break = thesis stop. "
                "OI walls = pinning targets near expiry. "
                "Write 5-7 concise, actionable bullet points covering: "
                "(1) which tickers have the clearest structural support for put spreads, "
                "(2) any GEX flip zones to watch, "
                "(3) notable Dark Pool floors that define risk levels, "
                "(4) OI pinning targets for the nearest expiry, "
                "(5) any tickers to avoid due to thin or unclear structure."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Here is today's GEX & OI profile report:

{report_text[:6000]}"
                }
            ],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"[AI commentary unavailable: {e}]"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    today_et = today
    start_90d = (datetime.now(ET) - timedelta(days=90)).strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"QuantData GEX & OI Profile Report — {today}")
    print("=" * 60)

    created_time = get_tool_created_time("exposure_by_strike")
    ticker_profiles = {}

    for ticker in ALL_TICKERS:
        print(f"  Collecting: {ticker}...", end=" ", flush=True)
        try:
            ticker_profiles[ticker] = collect_gex_oi_dp(ticker, created_time, today_et, start_90d)
            gex = ticker_profiles[ticker].get("gex", {})
            dp  = ticker_profiles[ticker].get("dark_pool", [])
            cw  = len(gex.get("call_walls", []))
            pw  = len(gex.get("put_walls", []))
            print(f"GEX {cw}C/{pw}P walls, {len(dp)} DP levels")
        except Exception as e:
            print(f"ERROR: {e}")
            ticker_profiles[ticker] = {}

    # Reset tools to SPX
    print("\nResetting tools to SPX...")
    spx_gex_meta = {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": "SPX"},
        },
        "greekModeType": "GAMMA",
        "isNet": True,
        "representationModeType": "PER_ONE_PERCENT_MOVE",
        "type": "OPTIONS_EXPOSURE_BY_STRIKE_CHART",
    }
    spx_oi_meta = {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": "SPX"},
        },
        "type": "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART",
    }
    update_tool("exposure_by_strike", spx_gex_meta, created_time)
    update_tool("oi_by_strike", spx_oi_meta, created_time)

    print("Generating report...")
    report_md = generate_report(today, ticker_profiles)

    print("Generating AI commentary...")
    commentary = generate_ai_commentary(report_md)

    # Prepend AI commentary
    header = f"## Strategist Commentary\n\n{commentary}\n\n---\n\n"
    final_report = report_md.replace("---\n\n", "---\n\n" + header, 1)

    report_path = REPORT_DIR / f"GEX_OI_{today}.md"
    report_path.write_text(final_report)
    print(f"\nReport saved: {report_path}")

    print("\n" + "=" * 60)
    print("STRATEGIST COMMENTARY:")
    print("=" * 60)
    print(commentary)
    print("=" * 60)

    return str(report_path)


if __name__ == "__main__":
    main()
