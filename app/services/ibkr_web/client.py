"""
HTTP client wrapping the CP Gateway URL.

Per IBKR docs: "Authenticating with OAuth 1.0a and OAuth 2.0 requires
client-side cookie management. A cookie with the Interactive Brokers
Web API requires users make a request to the /tickle endpoint and
capture the session token."

We POST /tickle on first use, capture the `session` token, and include
it as `Cookie: api={token}` on all subsequent requests.

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
        self._session_token: Optional[str] = None

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

    def _ensure_session_token(self):
        """Tickle once to capture the session token. Idempotent."""
        if self._session_token is not None:
            return
        import httpx
        c = self._ensure_client()
        try:
            resp = c.request("POST", "/tickle")
        except httpx.RequestError as e:
            raise GatewayUnreachable("tickle failed: " + str(e))
        if resp.status_code != 200:
            raise WebApiError("tickle returned " + str(resp.status_code) + ": " + resp.text[:200])
        try:
            body = resp.json()
        except Exception:
            raise WebApiError("tickle response not JSON: " + resp.text[:200])
        token = body.get("session")
        if not token:
            raise WebApiError("tickle response missing 'session' field: " + str(body)[:200])
        self._session_token = token
        logger.debug("Captured session token (%d chars)", len(token))

    def reset_session(self):
        self._session_token = None

    def _request(self, method: str, path: str, **kwargs) -> Any:
        import httpx
        self.limiter.wait()
        c = self._ensure_client()

        if path != "/tickle":
            self._ensure_session_token()

        headers = dict(kwargs.pop("headers", {}) or {})
        if self._session_token:
            existing = headers.get("Cookie", "")
            cookie_val = "api=" + self._session_token
            headers["Cookie"] = (existing + "; " + cookie_val) if existing else cookie_val

        try:
            resp = c.request(method, path, headers=headers, **kwargs)
        except httpx.ConnectError as e:
            raise GatewayUnreachable("CP Gateway unreachable at " + self.base_url + ": " + str(e))
        except httpx.RequestError as e:
            raise GatewayUnreachable("CP Gateway request error: " + str(e))

        if resp.status_code == 429:
            raise WebApiError("rate_limited (429) - penalty box risk; back off")
        if resp.status_code in (401, 403):
            self._session_token = None
            raise WebApiError("auth_failed (" + str(resp.status_code) + ") - session may have expired")
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
