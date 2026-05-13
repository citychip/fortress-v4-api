"""
HTTP client wrapping the CP Gateway (ibeam) URL.

ibeam handles IBKR authentication internally — it maintains the session
and proxies all requests without requiring a client-side session cookie.
We simply send requests directly; no /tickle or cookie management needed.

Pacing: IBKR enforces 10 req/sec global per username. We add a small
local rate limiter (RPSLimiter) that sleeps between calls.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("fortress.ibkr_web.client")


class WebApiError(Exception):
    """Raised on non-recoverable Web API errors (4xx, parse, auth)."""


class GatewayUnreachable(Exception):
    """Raised when CP Gateway is not running / not responding."""


class RPSLimiter:
    """Trivial requests-per-second limiter. Thread-safe. Not async."""
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
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import httpx
            except ImportError as e:
                raise WebApiError("httpx not installed: " + str(e))
            self._client = httpx.Client(
                base_url=self.base_url,
                verify=self.verify_ssl,
                timeout=self.timeout,
                headers={"User-Agent": "fortress-dashboard/1.7"},
            )
        return self._client

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def reset_session(self):
        """No-op — ibeam manages the session internally."""
        pass

    def _request(self, method: str, path: str, **kwargs) -> Any:
        import httpx
        self.limiter.wait()
        c = self._ensure_client()

        headers = dict(kwargs.pop("headers", {}) or {})

        try:
            resp = c.request(method, path, headers=headers, **kwargs)
        except httpx.ConnectError as e:
            raise GatewayUnreachable("CP Gateway unreachable at " + self.base_url + ": " + str(e))
        except httpx.RequestError as e:
            raise GatewayUnreachable("CP Gateway request error: " + str(e))

        if resp.status_code == 429:
            raise WebApiError("rate_limited (429) - penalty box risk; back off")
        if resp.status_code in (401, 403):
            raise WebApiError("auth_failed (" + str(resp.status_code) + ") - ibeam session may need restart")
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
