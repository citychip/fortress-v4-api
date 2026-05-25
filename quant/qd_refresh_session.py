#!/usr/bin/env python3
"""
QuantData Session Refresh Script
=================================
Logs in to v3.quantdata.us using email/password credentials, extracts the
fresh JWT token and session cookie, writes them to ~/.quantdata-mcp/config.json,
and restarts the fortress-dashboard service.

Usage:
    python3 qd_refresh_session.py

Cron (refresh daily at 06:00):
    0 6 * * * /usr/bin/python3 /home/ubuntu/Fortress_Dashboard/quant/qd_refresh_session.py >> /var/log/qd_refresh.log 2>&1

Environment variables (optional overrides):
    QD_EMAIL      QuantData login email
    QD_PASSWORD   QuantData login password
"""

import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

try:
    from curl_cffi import requests as cffi_req
except ImportError:
    print("ERROR: curl_cffi not installed. Run: pip install curl_cffi")
    sys.exit(1)

# ── Credentials ───────────────────────────────────────────────────────────────
QD_EMAIL    = os.environ.get("QD_EMAIL",    "citychip@gmail.com")
QD_PASSWORD = os.environ.get("QD_PASSWORD", "Stevev55!")

# ── Constants ─────────────────────────────────────────────────────────────────
QD_BASE         = "https://core-lb-prod.quantdata.us/api"
LOGIN_ENDPOINT  = "user/authentication/login"
QD_CONFIG_PATH  = pathlib.Path.home() / ".quantdata-mcp" / "config.json"
SERVICE_NAME    = "fortress-dashboard"

BROWSER_HEADERS = {
    "accept":           "application/json, text/plain, */*",
    "accept-language":  "en-US,en;q=0.9",
    "content-type":     "application/json",
    "origin":           "https://v3.quantdata.us",
    "referer":          "https://v3.quantdata.us/login",
    "sec-ch-ua":        '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest":   "empty",
    "sec-fetch-mode":   "cors",
    "sec-fetch-site":   "cross-site",
    "user-agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def warm_up_session(sess) -> None:
    """Visit the login page to acquire Cloudflare clearance cookies."""
    try:
        sess.get("https://v3.quantdata.us/login", timeout=15)
    except Exception as e:
        log(f"WARN: Session warm-up failed (non-fatal): {e}")


def login(sess) -> dict:
    """
    POST to the login endpoint and return the response JSON.
    Raises RuntimeError on failure.
    """
    payload = {"usernameOrEmail": QD_EMAIL, "password": QD_PASSWORD}
    url = f"{QD_BASE}/{LOGIN_ENDPOINT}"
    resp = sess.post(url, json=payload, timeout=20)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Login failed: HTTP {resp.status_code} — {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Login response is not JSON: {e} — {resp.text[:200]}")

    return data


def extract_credentials(login_data: dict, resp_cookies: dict) -> tuple[str, str]:
    """
    Extract the JWT token and build the cookie string from the login response.
    Returns (token, cookie_string).
    """
    # Token is in response.userSessionDTO.token
    resp_body = login_data.get("response", login_data)
    session_dto = resp_body.get("userSessionDTO", resp_body)
    token = (
        session_dto.get("token")
        or resp_body.get("token")
        or resp_body.get("authToken")
        or resp_body.get("accessToken")
        or resp_body.get("jwt")
        or ""
    )
    if not token:
        raise RuntimeError(
            f"Could not find token in login response. Keys: {list(resp_body.keys())}"
        )

    # Build cookie string from response cookies + token cookie
    cookie_parts = []
    for k, v in resp_cookies.items():
        cookie_parts.append(f"{k}={v}")
    # Always include the token cookie (QuantData widget endpoints need it)
    if f"token={token}" not in " ".join(cookie_parts):
        cookie_parts.append(f"token={token}")

    cookie_str = "; ".join(cookie_parts)
    return token, cookie_str


def update_config(token: str, cookie: str) -> None:
    """Write fresh token and cookie to ~/.quantdata-mcp/config.json."""
    QD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    cfg = {}
    if QD_CONFIG_PATH.exists():
        try:
            cfg = json.loads(QD_CONFIG_PATH.read_text())
        except Exception:
            cfg = {}

    cfg["auth_token"] = token
    cfg["cookie"]     = cookie

    # Decode userId from JWT payload and store explicitly so _set_global_filter works
    try:
        import base64
        payload_b64 = token.split(".")[1]
        payload_b64 += "==" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        uid = payload.get("userId", "")
        if uid:
            cfg["user_id"] = uid
            log(f"user_id decoded from JWT: {uid}")
    except Exception as e:
        log(f"Warning: could not decode user_id from JWT: {e}")

    QD_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    log(f"Config updated: {QD_CONFIG_PATH}")


def restart_service() -> bool:
    """Restart the fortress-dashboard systemd service. Returns True on success."""
    try:
        # Use nohup + background so the restart doesn't block this script.
        # systemctl restart can hang if the service takes >30s to stop.
        subprocess.Popen(
            ["bash", "-c",
             f"sleep 1 && systemctl restart {SERVICE_NAME} >> /var/log/qd_refresh.log 2>&1"],
            start_new_session=True,
        )
        log(f"Service '{SERVICE_NAME}' restart triggered (background).")
        return True
    except Exception as e:
        log(f"WARN: Could not trigger service restart: {e}")
        return False


def verify_token(token: str, cookie: str) -> bool:
    """Quick sanity-check: call iv_rank to confirm the new token works."""
    try:
        cfg = json.loads(QD_CONFIG_PATH.read_text())
        iv_rank_id = cfg.get("tools", {}).get("iv_rank", "")
        if not iv_rank_id:
            log("WARN: No iv_rank tool ID in config — skipping verification.")
            return True

        sess = cffi_req.Session(impersonate="chrome110")
        sess.headers.update({
            "accept":        "application/json",
            "authorization": token,
            "cookie":        cookie,
            "origin":        "https://v3.quantdata.us",
            "user-agent":    BROWSER_HEADERS["user-agent"],
        })
        r = sess.get(
            f"{QD_BASE}/options/iv-rank/{iv_rank_id}",
            timeout=15
        )
        if r.status_code == 200:
            log("Token verification: PASS (iv_rank returned 200)")
            return True
        else:
            log(f"Token verification: FAIL (iv_rank returned HTTP {r.status_code})")
            return False
    except Exception as e:
        log(f"Token verification error: {e}")
        return False


def main():
    log("=== QuantData Session Refresh ===")
    log(f"Account: {QD_EMAIL}")

    # 1. Create session with Chrome impersonation
    sess = cffi_req.Session(impersonate="chrome110")
    sess.headers.update(BROWSER_HEADERS)

    # 2. Warm up (get Cloudflare cookies)
    log("Warming up session...")
    warm_up_session(sess)

    # 3. Login
    log(f"Logging in via POST {QD_BASE}/{LOGIN_ENDPOINT}...")
    try:
        login_data = login(sess)
    except RuntimeError as e:
        log(f"ERROR: {e}")
        sys.exit(1)

    # 4. Extract credentials
    try:
        token, cookie = extract_credentials(login_data, dict(sess.cookies))
    except RuntimeError as e:
        log(f"ERROR: {e}")
        log(f"Full login response: {json.dumps(login_data, indent=2)[:1000]}")
        sys.exit(1)

    log(f"Token obtained: {token[:40]}...")
    log(f"Cookie length: {len(cookie)} chars")

    # 5. Update config file
    update_config(token, cookie)

    # 6. Verify token works
    verify_token(token, cookie)

    # 7. Restart service
    restart_service()

    log("=== Refresh complete ===")


if __name__ == "__main__":
    main()
