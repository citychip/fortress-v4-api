"""
IBKR Web API client (Client Portal Gateway).

Replaces the legacy TWS Gateway path for Greeks-backed sync. Two-tiered
session model per the IBKR docs:

  - Outer read-only session (CP Gateway login + cookie + /tickle loop)
  - Brokerage session (required for /iserver/* endpoints — market data,
    snapshots, contract chain, orders)

This package never executes orders. Snapshot pattern is two-step
(preflight then read) per docs.

Modules:
  - client.py      — httpx wrapper with auth, retry, pacing
  - session.py     — login state, /tickle loop, status polling
  - capability.py  — OPRA detection + backend selection helper
  - portfolio.py   — /portfolio/* endpoint wrappers
  - secdef.py      — /iserver/secdef/* — ticker → conid resolution
  - snapshot.py    — /iserver/marketdata/snapshot two-step pattern
"""

__version__ = "0.1.0"

# Field tags verified against cpapi-v1 docs (May 4, 2026)
FIELD_TAGS = {
    "last":       "31",
    "bid":        "84",
    "bid_size":   "85",
    "ask":        "86",
    "ask_size":   "88",
    "last_size":  "7059",
    "iv_underlying": "7283",   # underlying-level IV (NOT per-strike)
    "open_today": "7295",
    "close_today":"7296",
    "delta":      "7308",
    "gamma":      "7309",
    "theta":      "7310",
    "vega":       "7311",
    "iv_strike":  "7633",      # per-strike IV — use this for chain matching
    "mark":       "7635",
}

# Standard fields list our sync requests on each snapshot call
SNAPSHOT_FIELDS = [
    FIELD_TAGS["last"],
    FIELD_TAGS["bid"], FIELD_TAGS["bid_size"],
    FIELD_TAGS["ask"], FIELD_TAGS["ask_size"],
    FIELD_TAGS["last_size"],
    FIELD_TAGS["delta"], FIELD_TAGS["gamma"], FIELD_TAGS["theta"], FIELD_TAGS["vega"],
    FIELD_TAGS["iv_strike"],
    FIELD_TAGS["mark"],
]


def make_client(cfg_fn=None):
    """
    Factory: returns the right IBKR client based on security.ibkr_auth_mode.
      'ibeam'  → WebApiClient (CP Gateway / ibeam)
      'oauth'  → OAuthApiClient (OAuth 1.0a direct to api.ibkr.com)
    """
    if cfg_fn is None:
        from app.services.config_store import cfg as cfg_fn
    mode = cfg_fn('security.ibkr_auth_mode') or 'ibeam'
    if mode == 'oauth':
        from app.services.ibkr_web.oauth_client import OAuthApiClient
        return OAuthApiClient()
    else:
        from app.services.ibkr_web.client import WebApiClient
        gateway_url = cfg_fn('security.cp_gateway_url') or 'https://localhost:5000'
        verify_ssl  = bool(cfg_fn('security.cp_gateway_verify_ssl') or False)
        timeout_s   = int(cfg_fn('security.cp_gateway_timeout_s') or 15)
        return WebApiClient(gateway_url=gateway_url, verify_ssl=verify_ssl, request_timeout_s=timeout_s)


def get_session_status(cfg_fn=None):
    """Return session summary dict regardless of auth mode."""
    if cfg_fn is None:
        from app.services.config_store import cfg as cfg_fn
    mode = cfg_fn('security.ibkr_auth_mode') or 'ibeam'
    if mode == 'oauth':
        from app.services.ibkr_web.oauth_client import get_oauth_status
        return get_oauth_status()
    else:
        from app.services.ibkr_web.client import WebApiClient
        from app.services.ibkr_web import session as web_session
        gateway_url = cfg_fn('security.cp_gateway_url') or 'https://localhost:5000'
        verify_ssl  = bool(cfg_fn('security.cp_gateway_verify_ssl') or False)
        timeout_s   = int(cfg_fn('security.cp_gateway_timeout_s') or 15)
        client = WebApiClient(gateway_url=gateway_url, verify_ssl=verify_ssl, request_timeout_s=timeout_s)
        try:
            return web_session.session_summary(client)
        finally:
            client.close()
