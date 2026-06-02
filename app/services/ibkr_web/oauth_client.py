"""
app/services/ibkr_web/oauth_client.py
IBKR OAuth 1.0a — implementation based on Voyz/ibind (github.com/Voyz/ibind)
Uses pycryptodome (pip install pycryptodome).

Auth flow:
  1. Load access_token + access_token_secret from IBKR Self Service Portal files
  2. Extract DH prime from dhparam.pem
  3. POST /oauth/live_session_token (RSA-SHA256 signed, DH challenge in OAuth params)
  4. Compute Live Session Token from DH response
  5. POST /iserver/auth/ssodh/init (HMAC-SHA256 signed with LST)
  6. All subsequent requests signed with HMAC-SHA256 using LST
"""
from __future__ import annotations

import base64
import logging
import os
import re
import secrets
import string
import subprocess
import time
from typing import Any, Optional
from urllib import parse

from Crypto.Cipher import PKCS1_v1_5 as PKCS1_v1_5_Cipher   # nosec
from Crypto.Hash import SHA256, HMAC, SHA1                    # nosec
from Crypto.PublicKey import RSA                               # nosec
from Crypto.Signature import PKCS1_v1_5 as PKCS1_v1_5_Sig    # nosec

logger = logging.getLogger("fortress.ibkr_web.oauth_client")

CONSUMER_KEY = "SHARMILAH"
BASE_URL     = "https://api.ibkr.com/v1/api"
REALM        = "limited_poa"
_KEYS_DIR    = "/home/ubuntu/ibkr-oauth"

_ACCESS_TOKEN_FILE        = _KEYS_DIR + "/access_token.txt"
_ACCESS_TOKEN_SECRET_FILE = _KEYS_DIR + "/access_token_secret.txt"

_STRING_ENCODING    = "utf-8"
_INT_BASE           = 16
_KEY_VALUE_SEP      = "="
_DH_GENERATOR       = 2


# ── Key / token helpers (ibind-style) ────────────────────────────────────────

def _read_rsa_key(path: str) -> RSA.RsaKey:
    with open(path) as f:
        return RSA.importKey(f.read())


def _load_stored_access_token() -> tuple[str, str]:
    with open(_ACCESS_TOKEN_FILE) as f:
        token = f.read().strip()
    with open(_ACCESS_TOKEN_SECRET_FILE) as f:
        secret = f.read().strip()
    if not token or not secret:
        raise ValueError("access_token files are empty")
    return token, secret


def _extract_dh_prime() -> str:
    """Extract DH prime hex string from dhparam.pem (ibind wiki method)."""
    result = subprocess.run(
        ["openssl", "dhparam", "-in", os.path.join(_KEYS_DIR, "dhparam.pem"), "-text"],
        capture_output=True, text=True,
    ).stdout
    match = re.search(r"(?:prime|P):\s*((?:\s*[0-9a-fA-F:]+\s*)+)", result)
    if not match:
        raise RuntimeError("Could not extract DH prime from dhparam.pem")
    return re.sub(r"[\s:]", "", match.group(1))


# ── ibind OAuth functions (verbatim / lightly adapted) ───────────────────────

def _generate_nonce() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))


def _generate_timestamp() -> str:
    return str(int(time.time()))


def _calculate_prepend(access_token_secret: str, encryption_key: RSA.RsaKey) -> str:
    """Decrypt access_token_secret → hex prepend."""
    cipher = PKCS1_v1_5_Cipher.new(encryption_key)
    decrypted = cipher.decrypt(base64.b64decode(access_token_secret), None)
    return decrypted.hex()


def _generate_dh_random() -> str:
    """256-bit random as hex string."""
    return hex(secrets.randbits(256))[2:]


def _generate_dh_challenge(dh_prime: str, dh_random: str) -> str:
    return hex(pow(_DH_GENERATOR, int(dh_random, _INT_BASE), int(dh_prime, _INT_BASE)))[2:]


def _generate_base_string(
    method: str,
    url: str,
    headers: dict,
    prepend: Optional[str] = None,
    extra_params: Optional[dict] = None,
) -> str:
    """Build OAuth base string (ibind's generate_base_string)."""
    params = {**headers}
    if extra_params:
        params.update(extra_params)
    params_str = "&".join(f"{k}{_KEY_VALUE_SEP}{v}" for k, v in sorted(params.items()))
    base = "&".join([method, parse.quote_plus(url), parse.quote_plus(params_str)])
    if prepend is not None:
        base = f"{prepend}{base}"
    return base


def _rsa_sha256_sign(base_string: str, sig_key: RSA.RsaKey) -> str:
    """RSA-SHA256 signature, URL-encoded (ibind's generate_rsa_sha_256_signature)."""
    encoded = base_string.encode(_STRING_ENCODING)
    h = SHA256.new(encoded)
    sig = PKCS1_v1_5_Sig.new(sig_key).sign(h)
    b64 = base64.encodebytes(sig).decode(_STRING_ENCODING).replace("\n", "")
    return parse.quote_plus(b64)


def _hmac_sha256_sign(base_string: str, lst: str) -> str:
    """HMAC-SHA256 signature using LST as key, URL-encoded (ibind's generate_hmac_sha_256_signature)."""
    h = HMAC.new(bytes(base64.b64decode(lst)), digestmod=SHA256)
    h.update(base_string.encode(_STRING_ENCODING))
    return parse.quote_plus(base64.b64encode(h.digest()).decode(_STRING_ENCODING))


def _build_auth_header(params: dict) -> str:
    """Build Authorization header string (ibind's generate_authorization_header_string).
    realm comes first, then sorted params.
    """
    pairs = ", ".join(f'{k}{_KEY_VALUE_SEP}"{v}"' for k, v in sorted(params.items()))
    return f'OAuth realm="{REALM}", {pairs}'


def _to_byte_array(x: int) -> list[int]:
    """Convert int to byte array with optional leading zero (ibind's to_byte_array)."""
    hex_str = hex(x)[2:]
    if len(hex_str) % 2:
        hex_str = "0" + hex_str
    ba = []
    if len(bin(x)[2:]) % 8 == 0:
        ba.append(0)
    for i in range(0, len(hex_str), 2):
        ba.append(int(hex_str[i:i+2], _INT_BASE))
    return ba


def _calculate_lst(dh_prime: str, dh_random: str, dh_response: str, prepend: str) -> str:
    """Compute live session token (ibind's calculate_live_session_token)."""
    prepend_bytes = bytearray.fromhex(prepend)
    dh_rand_int   = int(dh_random, _INT_BASE)
    dh_resp_int   = int(dh_response, _INT_BASE)
    shared        = pow(dh_resp_int, dh_rand_int, int(dh_prime, _INT_BASE))
    h = HMAC.new(bytes(_to_byte_array(shared)), digestmod=SHA1)
    h.update(bytes(prepend_bytes))
    return base64.b64encode(h.digest()).decode(_STRING_ENCODING)


def _validate_lst(lst: str, lst_signature: str) -> bool:
    """Validate computed LST against IBKR-provided signature."""
    h = HMAC.new(bytes(base64.b64decode(lst)), digestmod=SHA1)
    h.update(CONSUMER_KEY.encode(_STRING_ENCODING))
    return h.hexdigest() == lst_signature


def _make_oauth_headers(
    method: str,
    url: str,
    lst: Optional[str] = None,
    extra_params: Optional[dict] = None,
    sig_key: Optional[RSA.RsaKey] = None,
    prepend: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Build the full HTTP headers dict for an OAuth request."""
    sig_method = "RSA-SHA256" if lst is None else "HMAC-SHA256"
    oauth = {
        "oauth_consumer_key":      CONSUMER_KEY,
        "oauth_nonce":             _generate_nonce(),
        "oauth_signature_method": sig_method,
        "oauth_timestamp":         _generate_timestamp(),
        "oauth_token":             access_token or _load_stored_access_token()[0],
    }
    base = _generate_base_string(method, url, oauth, prepend=prepend, extra_params=extra_params)
    if lst is None:
        oauth["oauth_signature"] = _rsa_sha256_sign(base, sig_key)
    else:
        oauth["oauth_signature"] = _hmac_sha256_sign(base, lst)
    # Include extra_params (e.g. diffie_hellman_challenge) in the Authorization header
    if extra_params:
        oauth.update(extra_params)
    return {
        "Accept":          "*/*",
        "Accept-Encoding": "gzip,deflate",
        "Authorization":   _build_auth_header(oauth),
        "Connection":      "keep-alive",
        "Host":            "api.ibkr.com",
        "User-Agent":      "ibind",
    }


# ── Session management ────────────────────────────────────────────────────────

class OAuthSession:
    def __init__(self):
        self.access_token:  Optional[str] = None
        self.lst:           Optional[str] = None
        self.lst_expiry:    float         = 0.0

    def is_valid(self) -> bool:
        return self.lst is not None and time.time() < self.lst_expiry - 60


_session = OAuthSession()
_dh_prime: Optional[str] = None


def _get_dh_prime() -> str:
    global _dh_prime
    if _dh_prime is None:
        _dh_prime = _extract_dh_prime()
        logger.info("DH prime extracted (%d hex chars)", len(_dh_prime))
    return _dh_prime


def ensure_session() -> OAuthSession:
    global _session
    if _session.is_valid():
        return _session

    logger.info("Acquiring OAuth Live Session Token (ibind flow)...")
    acc_tok, acc_sec = _load_stored_access_token()
    dh_prime  = _get_dh_prime()
    enc_key   = _read_rsa_key(os.path.join(_KEYS_DIR, "private_encryption.pem"))
    sig_key   = _read_rsa_key(os.path.join(_KEYS_DIR, "private_signature.pem"))

    prepend    = _calculate_prepend(acc_sec, enc_key)
    dh_random  = _generate_dh_random()
    dh_challenge = _generate_dh_challenge(dh_prime, dh_random)
    logger.info("DH challenge: %d hex chars", len(dh_challenge))

    url = f"{BASE_URL}/oauth/live_session_token"
    headers = _make_oauth_headers(
        method="POST", url=url,
        sig_key=sig_key, prepend=prepend,
        extra_params={"diffie_hellman_challenge": dh_challenge},
        access_token=acc_tok,
    )

    import httpx
    resp = httpx.post(url, headers=headers, verify=True, timeout=30)
    if not resp.is_success:
        raise RuntimeError(f"live_session_token failed {resp.status_code}: {resp.text[:300]}")

    data          = resp.json()
    dh_response   = data["diffie_hellman_response"]
    lst_signature = data["live_session_token_signature"]
    lst_expiry_ms = data["live_session_token_expiration"]

    lst = _calculate_lst(dh_prime, dh_random, dh_response, prepend)

    if _validate_lst(lst, lst_signature):
        logger.info("LST validated OK ✓ — expires %s", time.ctime(lst_expiry_ms / 1000))
    else:
        logger.warning("LST validation MISMATCH — continuing anyway")

    _session.access_token = acc_tok
    _session.lst          = lst
    _session.lst_expiry   = float(lst_expiry_ms) / 1000.0

    # Initialize brokerage session
    ssodh_url = f"{BASE_URL}/iserver/auth/ssodh/init"
    ssodh_headers = _make_oauth_headers("POST", ssodh_url, lst=lst, access_token=acc_tok)
    ssodh_resp = httpx.post(ssodh_url, headers=ssodh_headers, verify=True, timeout=30)
    logger.info("ssodh/init: %s — %s", ssodh_resp.status_code, ssodh_resp.text[:150])
    if not ssodh_resp.is_success:
        raise RuntimeError(f"ssodh/init failed {ssodh_resp.status_code}: {ssodh_resp.text[:200]}")

    return _session


# ── API client ────────────────────────────────────────────────────────────────

class OAuthApiClient:
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

        headers = _make_oauth_headers(method, url, lst=sess.lst, access_token=sess.access_token)
        resp = httpx.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

        if resp.status_code == 429:
            raise Exception("rate_limited (429)")
        if resp.status_code in (401, 403):
            global _session
            _session = OAuthSession()
            raise Exception(f"auth_failed ({resp.status_code}) — OAuth session invalidated")
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
