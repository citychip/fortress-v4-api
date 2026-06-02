"""
app/services/ibkr_web/oauth_client.py
IBKR OAuth 1.0a First-Party client (Self Service Portal / consumer credential flow).

Auth flow (per https://ibkrcampus.com/campus/ibkr-api-page/oauth-1-0a-extended/):
  1. Load stored access_token + access_token_secret from IBKR Self Service Portal
  2. Compute prepend = decrypt(access_token_secret, private_encryption_key).hex()
  3. POST /oauth/live_session_token:
       - DH challenge in OAuth Authorization header params
       - base_string = prepend + "POST&" + url + "&" + sorted_params
       - Signed with RSA-SHA256 (private_signature_key)
  4. Compute LST from response using HMAC-SHA1(K_bytes, prepend_bytes)
  5. POST /iserver/auth/ssodh/init (signed with HMAC-SHA256 using LST)
  6. All subsequent requests signed with HMAC-SHA256 using LST
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import logging
import os
import random
import secrets
import time
import urllib.parse
from typing import Any, Optional

logger = logging.getLogger("fortress.ibkr_web.oauth_client")

CONSUMER_KEY   = "SHARMILAH"
BASE_URL       = "https://api.ibkr.com/v1/api"
REALM          = "limited_poa"   # "test_realm" for TESTCONS paper key
_KEYS_DIR      = "/home/ubuntu/ibkr-oauth"

_ACCESS_TOKEN_FILE        = _KEYS_DIR + "/access_token.txt"
_ACCESS_TOKEN_SECRET_FILE = _KEYS_DIR + "/access_token_secret.txt"


# ── Key loading ───────────────────────────────────────────────────────────────

def _load_signature_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    with open(os.path.join(_KEYS_DIR, "private_signature.pem"), "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _load_encryption_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    with open(os.path.join(_KEYS_DIR, "private_encryption.pem"), "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _load_dh_params():
    from cryptography.hazmat.primitives.serialization import load_pem_parameters
    with open(os.path.join(_KEYS_DIR, "dhparam.pem"), "rb") as f:
        params = load_pem_parameters(f.read())
    pn = params.parameter_numbers()
    return pn.p, pn.g   # prime, generator


def _load_stored_access_token() -> tuple[str, str]:
    with open(_ACCESS_TOKEN_FILE) as f:
        token = f.read().strip()
    with open(_ACCESS_TOKEN_SECRET_FILE) as f:
        secret = f.read().strip()
    if not token or not secret:
        raise ValueError("access_token files are empty")
    return token, secret


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def _nonce() -> str:
    return secrets.token_hex(16)


def _timestamp() -> str:
    return str(int(time.time()))


def _rsa_sha256_sign(data: bytes) -> str:
    """Sign bytes with private_signature.pem using RSA-SHA256/PKCS1v15. Return base64 str."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    key = _load_signature_key()
    sig = key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _decrypt_with_encryption_key(ciphertext_b64: str) -> bytes:
    """Decrypt base64-encoded ciphertext using private_encryption.pem / PKCS1v15."""
    from cryptography.hazmat.primitives.asymmetric import padding
    key = _load_encryption_key()
    return key.decrypt(base64.b64decode(ciphertext_b64), padding.PKCS1v15())


def _build_rsa_auth_header(method: str, url: str, oauth_params: dict, prepend: str = "") -> str:
    """Build RSA-SHA256 signed OAuth Authorization header.

    For LST requests the base string is prepended with the decrypted secret hex.
    For other RSA requests (request_token etc.) prepend is empty string.
    """
    # Build params string (sorted, all params including dh_challenge if present)
    params_string = "&".join(
        f"{_pct_encode(k)}={_pct_encode(v)}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = (
        prepend
        + method.upper()
        + "&"
        + _pct_encode(url)
        + "&"
        + _pct_encode(params_string)
    )
    signature = _rsa_sha256_sign(base_string.encode("utf-8"))

    # Build header (realm omitted from signature, added after)
    header_params = {**oauth_params}
    header_params["oauth_signature"] = _pct_encode(signature)

    header_parts = ", ".join(
        f'{k}="{v}"'
        for k, v in sorted(header_params.items())
    )
    return "OAuth realm=\"" + REALM + "\", " + header_parts


def _build_hmac_auth_header(method: str, url: str, oauth_params: dict, lst: str) -> str:
    """Build HMAC-SHA256 signed OAuth Authorization header using the Live Session Token."""
    params_string = "&".join(
        f"{_pct_encode(k)}={_pct_encode(v)}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = (
        method.upper()
        + "&"
        + _pct_encode(url)
        + "&"
        + _pct_encode(params_string)
    )
    lst_key = base64.b64decode(lst)
    sig_bytes = _hmac.new(lst_key, base_string.encode("utf-8"), hashlib.sha256).digest()
    signature = _pct_encode(base64.b64encode(sig_bytes).decode())

    header_params = {**oauth_params}
    header_params["oauth_signature"] = signature

    header_parts = ", ".join(
        f'{k}="{v}"'
        for k, v in sorted(header_params.items())
    )
    return f"OAuth {header_parts}"


# ── Live Session Token flow ───────────────────────────────────────────────────

def _acquire_live_session_token(access_token: str, access_token_secret: str) -> tuple[str, float]:
    """Full LST flow per IBKR OAuth 1.0a extended documentation.

    Returns (live_session_token, expiry_unix_timestamp).
    """
    import httpx

    # Step 1: Compute prepend
    decrypted_secret = _decrypt_with_encryption_key(access_token_secret)
    prepend = decrypted_secret.hex()
    prepend_bytes = bytes.fromhex(prepend)
    logger.info("Prepend computed (%d bytes)", len(prepend_bytes))

    # Step 2: DH challenge
    dh_prime, dh_generator = _load_dh_params()
    dh_random = random.getrandbits(256)
    dh_challenge = hex(pow(dh_generator, dh_random, dh_prime))[2:]
    logger.info("DH challenge computed (%d hex chars)", len(dh_challenge))

    # Step 3: Build OAuth params for LST request (dh_challenge IN params, NOT body)
    url = f"{BASE_URL}/oauth/live_session_token"
    oauth_params = {
        "diffie_hellman_challenge": dh_challenge,
        "oauth_consumer_key":       CONSUMER_KEY,
        "oauth_nonce":              _nonce(),
        "oauth_signature_method":  "RSA-SHA256",
        "oauth_timestamp":          _timestamp(),
        "oauth_token":              access_token,
    }

    # Step 4: Sign with RSA, base_string prefixed with prepend
    auth_header = _build_rsa_auth_header("POST", url, oauth_params, prepend=prepend)

    # Step 5: POST /oauth/live_session_token — NO BODY
    headers = {
        "Accept":          "*/*",
        "Accept-Encoding": "gzip,deflate",
        "Authorization":   auth_header,
        "Connection":      "keep-alive",
        "Host":            "api.ibkr.com",
        "User-Agent":      "python/3.12",
    }
    logger.info("Requesting Live Session Token...")
    resp = httpx.post(url, headers=headers, verify=True, timeout=30)
    if not resp.is_success:
        raise RuntimeError(f"live_session_token failed {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    dh_response         = data["diffie_hellman_response"]
    lst_signature       = data["live_session_token_signature"]
    lst_expiration_ms   = data["live_session_token_expiration"]

    # Step 6: Compute K = dh_response ^ dh_random mod dh_prime
    B = int(dh_response, 16)
    K = pow(B, dh_random, dh_prime)

    hex_str_K = hex(K)[2:]
    if len(hex_str_K) % 2:
        hex_str_K = "0" + hex_str_K
    hex_bytes_K = bytes.fromhex(hex_str_K)
    if len(bin(K)[2:]) % 8 == 0:
        hex_bytes_K = bytes(1) + hex_bytes_K

    # Step 7: computed_lst = base64(HMAC-SHA1(key=K_bytes, msg=prepend_bytes))
    computed_lst = base64.b64encode(
        _hmac.new(hex_bytes_K, prepend_bytes, hashlib.sha1).digest()
    ).decode()

    # Step 8: Validate
    validation = _hmac.new(
        base64.b64decode(computed_lst),
        CONSUMER_KEY.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()

    if validation == lst_signature:
        logger.info("LST validated OK — expires %s", time.ctime(lst_expiration_ms / 1000))
    else:
        logger.warning("LST validation mismatch — computed=%s received=%s", validation, lst_signature)

    return computed_lst, float(lst_expiration_ms) / 1000.0


def _init_brokerage_session(lst: str) -> dict:
    """POST /iserver/auth/ssodh/init using HMAC-SHA256 signed with LST."""
    import httpx

    url = f"{BASE_URL}/iserver/auth/ssodh/init"
    oauth_params = {
        "oauth_consumer_key":       CONSUMER_KEY,
        "oauth_nonce":              _nonce(),
        "oauth_signature_method":  "HMAC-SHA256",
        "oauth_timestamp":          _timestamp(),
        "oauth_token":              _load_stored_access_token()[0],
    }
    auth_header = _build_hmac_auth_header("POST", url, oauth_params, lst)
    headers = {
        "Accept":          "*/*",
        "Accept-Encoding": "gzip,deflate",
        "Authorization":   auth_header,
        "Connection":      "keep-alive",
        "Host":            "api.ibkr.com",
        "User-Agent":      "python/3.12",
    }

    logger.info("ssodh/init: POST %s", url)
    resp = httpx.post(url, headers=headers, verify=True, timeout=30)
    logger.info("ssodh/init response: %s — %s", resp.status_code, resp.text[:200])
    if not resp.is_success:
        raise RuntimeError(f"ssodh/init failed {resp.status_code}: {resp.text[:200]}")
    return resp.json()


# ── Session management ────────────────────────────────────────────────────────

class OAuthSession:
    def __init__(self):
        self.access_token:        Optional[str]   = None
        self.access_token_secret: Optional[str]   = None
        self.live_session_token:  Optional[str]   = None
        self.lst_expiry:          float           = 0.0

    def is_valid(self) -> bool:
        return self.live_session_token is not None and time.time() < self.lst_expiry - 60


_session = OAuthSession()


def ensure_session() -> OAuthSession:
    global _session
    if _session.is_valid():
        return _session

    logger.info("Acquiring new OAuth Live Session Token (First Party flow)...")
    acc_tok, acc_sec = _load_stored_access_token()
    lst, expiry = _acquire_live_session_token(acc_tok, acc_sec)

    _session.access_token        = acc_tok
    _session.access_token_secret = acc_sec
    _session.live_session_token  = lst
    _session.lst_expiry          = expiry

    # Initialize brokerage session (required before API calls)
    ssodh = _init_brokerage_session(lst)
    logger.info("Brokerage session initialized: %s", ssodh)

    return _session


# ── API client ────────────────────────────────────────────────────────────────

class OAuthApiClient:
    """Drop-in replacement for WebApiClient using IBKR OAuth 1.0a."""

    def __init__(self, timeout: int = 15):
        self.base_url = BASE_URL
        self.timeout  = timeout

    def close(self):
        pass

    def reset_session(self):
        global _session
        _session = OAuthSession()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        import httpx
        url  = self.base_url + path
        sess = ensure_session()

        acc_tok = sess.access_token or _load_stored_access_token()[0]
        oauth_params = {
            "oauth_consumer_key":       CONSUMER_KEY,
            "oauth_nonce":              _nonce(),
            "oauth_signature_method":  "HMAC-SHA256",
            "oauth_timestamp":          _timestamp(),
            "oauth_token":              acc_tok,
        }
        auth_header = _build_hmac_auth_header(method, url, oauth_params, sess.live_session_token)
        headers = {
            "Accept":          "*/*",
            "Accept-Encoding": "gzip,deflate",
            "Authorization":   auth_header,
            "Connection":      "keep-alive",
            "Host":            "api.ibkr.com",
            "User-Agent":      "python/3.12",
        }

        resp = httpx.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        if resp.status_code == 429:
            raise Exception("rate_limited (429)")
        if resp.status_code in (401, 403):
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


# ── Status probe ──────────────────────────────────────────────────────────────

def get_oauth_status() -> dict:
    global _session
    try:
        sess = ensure_session()
        return {
            "reachable": True, "connected": True,
            "authenticated": True, "established": True,
            "competing": False,
            "ssoExpires_ms": int(sess.lst_expiry * 1000) if sess.lst_expiry else None,
            "error": None,
        }
    except Exception as e:
        return {
            "reachable": True, "connected": False,
            "authenticated": False, "established": False,
            "competing": False, "ssoExpires_ms": None,
            "error": str(e),
        }
