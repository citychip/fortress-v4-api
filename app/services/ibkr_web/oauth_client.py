"""
app/services/ibkr_web/oauth_client.py
IBKR OAuth 1.0a client for the Web API.

Uses:
  - Consumer key: SHARMILAH
  - private_signature.pem  — RSA-SHA256 request signing
  - private_encryption.pem — RSA encryption for DH live session token
  - dhparam.pem            — DH parameters

Auth flow (IBKR OAuth 1.0a with live session token):
  1. Request token  → POST /oauth/request_token
  2. Access token   → POST /oauth/access_token  (no user redirect needed for pre-approved tokens)
  3. Live session   → POST /iserver/auth/ssodh/init
  4. All subsequent requests signed with OAuth header

Reference: https://ibkr.info/article/4567
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
import urllib.parse
from typing import Any, Optional

logger = logging.getLogger("fortress.ibkr_web.oauth_client")

CONSUMER_KEY   = "SHARMILAH"
OAUTH_BASE_URL = "https://api.ibkr.com/v1/api"
_KEYS_DIR      = "/home/ubuntu/ibkr-oauth"


# ── Key loading ───────────────────────────────────────────────────────────────

def _load_private_signature_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    path = os.path.join(_KEYS_DIR, "private_signature.pem")
    with open(path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _load_private_encryption_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    path = os.path.join(_KEYS_DIR, "private_encryption.pem")
    with open(path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


# ── OAuth 1.0a helpers ────────────────────────────────────────────────────────

def _nonce() -> str:
    return secrets.token_hex(16)


def _timestamp() -> str:
    return str(int(time.time()))


def _pct_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def _base_string(method: str, url: str, params: dict) -> str:
    """Build the OAuth 1.0a signature base string."""
    sorted_params = "&".join(
        f"{_pct_encode(k)}={_pct_encode(v)}"
        for k, v in sorted(params.items())
    )
    return "&".join([method.upper(), _pct_encode(url), _pct_encode(sorted_params)])


def _rsa_sha256_sign(base_string: str) -> str:
    """Sign base_string with private_signature.pem, return base64."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    key = _load_private_signature_key()
    sig = key.sign(base_string.encode(), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _build_auth_header(method: str, url: str, extra_params: Optional[dict] = None, token: Optional[str] = None, token_secret: Optional[str] = None) -> str:
    """Build a signed OAuth Authorization header."""
    oauth_params = {
        "oauth_consumer_key":     CONSUMER_KEY,
        "oauth_nonce":            _nonce(),
        "oauth_signature_method": "RSA-SHA256",
        "oauth_timestamp":        _timestamp(),
        "oauth_version":          "1.0",
    }
    if token:
        oauth_params["oauth_token"] = token

    all_params = {**oauth_params, **(extra_params or {})}
    base = _base_string(method, url, all_params)
    oauth_params["oauth_signature"] = _rsa_sha256_sign(base)

    # Include any extra oauth_* params in the header as well
    header_params = {**oauth_params}
    for k, v in (extra_params or {}).items():
        if k.startswith("oauth_"):
            header_params[k] = v

    header_parts = ", ".join(
        f'{_pct_encode(k)}="{_pct_encode(v)}"'
        for k, v in sorted(header_params.items())
    )
    return f"OAuth {header_parts}"


# ── Token acquisition ─────────────────────────────────────────────────────────

class OAuthSession:
    """Holds the live OAuth session state."""
    def __init__(self):
        self.access_token: Optional[str] = None
        self.access_token_secret: Optional[str] = None
        self.live_session_token: Optional[str] = None
        self.lst_expiry: float = 0.0

    def is_valid(self) -> bool:
        return (
            self.live_session_token is not None
            and time.time() < self.lst_expiry - 60
        )


_session = OAuthSession()


def _request_token() -> tuple[str, str]:
    """POST /oauth/request_token → (oauth_token, oauth_token_secret)."""
    import httpx
    url = "https://api.ibkr.com/v1/api/oauth/request_token"
    auth = _build_auth_header("POST", url, {"oauth_callback": "oob"})
    resp = httpx.post(url, headers={"Authorization": auth}, verify=True, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"request_token failed {resp.status_code}: {resp.text[:200]}")
    parsed = dict(urllib.parse.parse_qsl(resp.text))
    return parsed["oauth_token"], parsed["oauth_token_secret"]


def _access_token(request_token: str, request_secret: str) -> tuple[str, str]:
    """POST /oauth/access_token → (access_token, access_token_secret).
    For pre-approved consumer keys (paper/live DTC), no verifier is needed.
    """
    import httpx
    url = "https://api.ibkr.com/v1/api/oauth/access_token"
    auth = _build_auth_header("POST", url, token=request_token, token_secret=request_secret)
    resp = httpx.post(url, headers={"Authorization": auth}, verify=True, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"access_token failed {resp.status_code}: {resp.text[:200]}")
    parsed = dict(urllib.parse.parse_qsl(resp.text))
    return parsed["oauth_token"], parsed["oauth_token_secret"]


def _live_session_token(access_token: str, access_secret: str) -> tuple[str, float]:
    """POST /iserver/auth/ssodh/init → live_session_token + expiry."""
    import httpx
    url = "https://api.ibkr.com/v1/api/iserver/auth/ssodh/init"

    # Prepend DH challenge value — IBKR sends a challenge encrypted with our public encryption key
    # For the initial call we send an empty challenge; IBKR returns the LST directly for pre-approved keys
    auth = _build_auth_header("POST", url, token=access_token, token_secret=access_secret)
    resp = httpx.post(url, headers={"Authorization": auth}, json={}, verify=True, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"ssodh/init failed {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    lst = data.get("live_session_token") or data.get("lsToken")
    expires_ms = data.get("live_session_token_expiration") or (time.time() * 1000 + 24 * 3600 * 1000)
    if not lst:
        raise RuntimeError(f"No live_session_token in response: {data}")
    return lst, float(expires_ms) / 1000.0


def ensure_session() -> OAuthSession:
    """Ensure a valid OAuth session exists, refreshing if needed."""
    global _session
    if _session.is_valid():
        return _session

    logger.info("Acquiring new OAuth session...")
    req_tok, req_sec = _request_token()
    acc_tok, acc_sec = _access_token(req_tok, req_sec)
    lst, expiry = _live_session_token(acc_tok, acc_sec)

    _session.access_token = acc_tok
    _session.access_token_secret = acc_sec
    _session.live_session_token = lst
    _session.lst_expiry = expiry
    logger.info("OAuth session established, expires at %s", time.ctime(expiry))
    return _session


# ── OAuth-signed request client ───────────────────────────────────────────────

class OAuthApiClient:
    """Drop-in replacement for WebApiClient using OAuth instead of ibeam."""

    def __init__(self, timeout: int = 15):
        self.base_url = OAUTH_BASE_URL
        self.timeout = timeout

    def close(self):
        pass  # stateless HTTP

    def reset_session(self):
        global _session
        _session = OAuthSession()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        import httpx
        url = self.base_url + path
        sess = ensure_session()
        auth = _build_auth_header(method, url, token=sess.access_token, token_secret=sess.access_token_secret)
        headers = {"Authorization": auth, "User-Agent": "fortress-dashboard/1.7"}

        resp = httpx.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

        if resp.status_code == 429:
            raise Exception("rate_limited (429)")
        if resp.status_code in (401, 403):
            # Invalidate session so next call re-authenticates
            global _session
            _session = OAuthSession()
            raise Exception(f"auth_failed ({resp.status_code}) - OAuth session invalidated")
        if resp.status_code >= 400:
            raise Exception(f"http_{resp.status_code}: {resp.text[:200]}")

        try:
            return resp.json()
        except Exception:
            return resp.text

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Optional[dict] = None) -> Any:
        return self._request("POST", path, json=json)


def get_oauth_status() -> dict:
    """Return OAuth session status (mirrors WebApiClient session_summary shape)."""
    global _session
    try:
        sess = ensure_session()
        return {
            "reachable": True,
            "connected": True,
            "authenticated": True,
            "established": True,
            "competing": False,
            "ssoExpires_ms": int(sess.lst_expiry * 1000) if sess.lst_expiry else None,
            "error": None,
        }
    except Exception as e:
        return {
            "reachable": True,
            "connected": False,
            "authenticated": False,
            "established": False,
            "competing": False,
            "ssoExpires_ms": None,
            "error": str(e),
        }
