"""
HTTP client — CP Gateway (legacy httpx) or ibind OAuth 1.0a.

When IBIND_USE_OAUTH=True (set in systemd override.conf) all calls go
through ibind's IbkrClient directly — no CP Gateway needed.
Legacy httpx path is kept as fallback when OAuth is not configured.

Pacing: IBKR enforces ~10 req/sec global per username.
"""
from __future__ import annotations
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("fortress.ibkr_web.client")


class WebApiError(Exception):
    """Raised on non-recoverable Web API errors (4xx, parse, auth)."""


class GatewayUnreachable(Exception):
    """Raised when CP Gateway is not running / not responding."""


class RPSLimiter:
    """Trivial requests-per-second limiter. Thread-safe."""
    def __init__(self, max_per_second: int = 8):
        self.min_interval = 1.0 / float(max_per_second)
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


# ── ibind singleton ──────────────────────────────────────────────────────────

_ibind_client = None
_ibind_lock = threading.Lock()
_ibind_error: Optional[str] = None


def _get_ibind_client():
    global _ibind_client, _ibind_error
    if _ibind_client is not None:
        return _ibind_client
    with _ibind_lock:
        if _ibind_client is not None:
            return _ibind_client
        try:
            from ibind import IbkrClient
            account_id = os.environ.get("IBIND_ACCOUNT_ID", "U7453366")
            _ibind_client = IbkrClient(
            account_id=account_id,
            timeout=5,
            max_retries=1,
            auto_register_shutdown=False,
        )
            _ibind_error = None
            logger.info(f"ibind IbkrClient ready (account={account_id})")
            return _ibind_client
        except Exception as exc:
            _ibind_error = str(exc)
            logger.error(f"ibind IbkrClient init failed: {exc}")
            raise GatewayUnreachable(f"ibind init failed: {exc}")


def reset_ibind_client():
    """Tear down singleton — next call re-initialises OAuth."""
    global _ibind_client, _ibind_error
    with _ibind_lock:
        if _ibind_client is not None:
            try:
                _ibind_client.close()
            except Exception:
                pass
            _ibind_client = None
        _ibind_error = None
    logger.info("ibind IbkrClient reset — will re-init on next call")


# ── WebApiClient ─────────────────────────────────────────────────────────────

class WebApiClient:
    def __init__(
        self,
        gateway_url: str = "https://localhost:5000",
        verify_ssl: bool = False,
        request_timeout_s: int = 15,
        max_per_second: int = 8,
    ):
        self.base_url = gateway_url.rstrip("/") + "/v1/api"
        self.verify_ssl = verify_ssl
        self.timeout = request_timeout_s
        self.limiter = RPSLimiter(max_per_second)
        self._http_client = None
        # Use ibind when config store toggle is on (falls back to env var)
        try:
            from app.services.config_store import cfg as _cfg
            self._use_ibind = bool(_cfg("security.ibkr_use_ibind_oauth"))
        except Exception:
            self._use_ibind = os.environ.get("IBIND_USE_OAUTH", "").lower() in ("1", "true", "yes")

    def _ensure_http_client(self):
        if self._http_client is None:
            try:
                import httpx
            except ImportError as e:
                raise WebApiError("httpx not installed: " + str(e))
            self._http_client = httpx.Client(
                base_url=self.base_url,
                verify=self.verify_ssl,
                timeout=self.timeout,
                headers={"User-Agent": "fortress-dashboard/1.7"},
            )
        return self._http_client

    def close(self):
        """Close httpx client if open. ibind singleton is NOT closed here."""
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None

    def reset_session(self):
        """Session is managed externally (ibeam or ibind)."""
        pass

    # ── dispatch ────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> Any:
        if self._use_ibind:
            return self._ibind_request(method, path, **kwargs)
        return self._http_request(method, path, **kwargs)

    def _ibind_request(self, method: str, path: str, **kwargs) -> Any:
        """Route through ibind IbkrClient (OAuth 1.0a)."""
        self.limiter.wait()
        try:
            c = _get_ibind_client()
            clean = path.lstrip("/")
            if method.upper() == "GET":
                result = c.get(clean, params=kwargs.get("params"))
            else:
                result = c.post(clean, json=kwargs.get("json"))
            return result.data if hasattr(result, "data") else result
        except GatewayUnreachable:
            raise
        except Exception as exc:
            msg = str(exc)
            if any(x in msg for x in ("401", "403", "Unauthorized", "Forbidden")):
                raise WebApiError(f"ibind auth error: {exc}")
            if any(x in msg.lower() for x in ("connect", "timeout", "network", "resolve")):
                raise GatewayUnreachable(f"ibind connection error: {exc}")
            raise WebApiError(f"ibind error: {exc}")

    def _http_request(self, method: str, path: str, **kwargs) -> Any:
        """Legacy: direct httpx to CP Gateway."""
        import httpx
        self.limiter.wait()
        c = self._ensure_http_client()
        headers = dict(kwargs.pop("headers", {}) or {})
        try:
            resp = c.request(method, path, headers=headers, **kwargs)
        except httpx.ConnectError as e:
            raise GatewayUnreachable("CP Gateway unreachable at " + self.base_url + ": " + str(e))
        except httpx.RequestError as e:
            raise GatewayUnreachable("CP Gateway request error: " + str(e))
        if resp.status_code == 429:
            raise WebApiError("rate_limited (429) - back off")
        if resp.status_code in (401, 403):
            raise WebApiError("auth_failed (" + str(resp.status_code) + ")")
        if resp.status_code >= 500:
            raise GatewayUnreachable("CP Gateway 5xx: " + str(resp.status_code) + " " + resp.text[:200])
        if resp.status_code >= 400:
            raise WebApiError("http_" + str(resp.status_code) + ": " + resp.text[:200])
        try:
            return resp.json()
        except Exception:
            return resp.text

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Optional[dict] = None) -> Any:
        return self._request("POST", path, json=json)
