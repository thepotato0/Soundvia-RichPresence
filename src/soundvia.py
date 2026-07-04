from __future__ import annotations

import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterable, Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests

__all__ = [
    "SoundviaAuthError",
    "SoundviaToken",
    "AppLimits",
    "AppInfo",
    "StatusResponse",
    "SoundviaOAuth",
    "SoundviaClient",
    "authorize_interactive",
]

BASE_URL = "https://soundvia.eu"


class SoundviaAuthError(Exception):
    """Raised when authentication with soundvia fails."""


@dataclass
class SoundviaToken:
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    obtained_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> Optional[float]:
        if self.expires_in is None:
            return None
        return self.obtained_at + self.expires_in

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at


@dataclass
class AppLimits:
    requests_per_minute: int
    response_bytes_per_minute: int

    @classmethod
    def from_dict(cls, data: dict) -> "AppLimits":
        return cls(
            requests_per_minute=data["requests_per_minute"],
            response_bytes_per_minute=data["response_bytes_per_minute"],
        )


@dataclass
class AppInfo:
    id: str
    name: str
    tier: str
    verification_status: str
    limits: AppLimits

    @classmethod
    def from_dict(cls, data: dict) -> "AppInfo":
        return cls(
            id=data["id"],
            name=data["name"],
            tier=data["tier"],
            verification_status=data["verification_status"],
            limits=AppLimits.from_dict(data["limits"]),
        )


@dataclass
class StatusResponse:
    ok: bool
    api: str
    app: AppInfo

    @classmethod
    def from_dict(cls, data: dict) -> "StatusResponse":
        return cls(
            ok=data["ok"],
            api=data["api"],
            app=AppInfo.from_dict(data["app"]),
        )


class SoundviaOAuth:
    """Handles the OAuth2 authorization-code flow for soundvia.eu."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorization_url(
        self, scopes: Iterable[str], state: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Build the URL to send the user's browser to for login/consent.

        CONFIRMED against the docs: GET /oauth/authorize with client_id,
        redirect_uri, response_type=code, scope (space-separated), state.

        Returns (url, state). Pass your own `state` or let one be generated
        for you -- either way, store it (e.g. in the user's session) so you
        can verify it matches on the callback, to protect against CSRF.
        """
        state = state or secrets.token_urlsafe(24)
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
        url = f"{BASE_URL}/oauth/authorize?{urlencode(params)}"
        return url, state

    def fetch_token(self, code: str) -> SoundviaToken:

        resp = requests.post(
            f"{BASE_URL}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if not resp.ok:
            raise SoundviaAuthError(f"Token exchange failed: {resp.status_code} {resp.text}")
        return SoundviaToken(**resp.json())

    def refresh(self, token: SoundviaToken) -> SoundviaToken:
        """
        Refresh an expired access token.

        NOT CONFIRMED -- same caveat as fetch_token().
        """
        if not token.refresh_token:
            raise SoundviaAuthError("No refresh_token available on this token.")
        resp = requests.post(
            f"{BASE_URL}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if not resp.ok:
            raise SoundviaAuthError(f"Token refresh failed: {resp.status_code} {resp.text}")
        return SoundviaToken(**resp.json())


class SoundviaClient:
    """
    Thin wrapper for calling authenticated soundvia.eu API endpoints.

    No resource endpoints are implemented yet -- none were available in the
    docs snippet provided. Add methods here following the `_get` pattern
    once you have real endpoint paths (e.g. get_library(), search_tracks()).
    """

    def __init__(self, token: SoundviaToken):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"{token.token_type} {token.access_token}",
            "Accept": "application/json",
        })

    @classmethod
    def from_token(cls, access_token: str, token_type: str = "Bearer") -> "SoundviaClient":
        """
        Convenience constructor for when you already have a bearer token
        (e.g. a static app token) and don't need the full OAuth exchange.
        """
        return cls(SoundviaToken(access_token=access_token, token_type=token_type))

    def _get(self, path: str, **kwargs) -> dict:
        resp = self.session.get(f"{BASE_URL}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, **kwargs) -> dict:
        resp = self.session.post(f"{BASE_URL}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_status(self) -> StatusResponse:
        """
        GET /api/v1/status

        Confirmed against the docs, including example response shape:
            {
              "ok": true,
              "api": "v1",
              "app": {
                "id": "...", "name": "...", "tier": "...",
                "verification_status": "...",
                "limits": {
                  "requests_per_minute": 180,
                  "response_bytes_per_minute": 12582912
                }
              }
            }
        """
        data = self._get("/api/v1/status")
        return StatusResponse.from_dict(data)

    def get_now_listening(self) -> requests.Response:
        resp = requests.get(
            f"{BASE_URL}/oauth/api/now-listening",
            headers={
                "Authorization": f"Bearer {self.token.access_token}",
                "Accept": "application/json"
            },
        )
        return resp

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Captures the ?code=&state= (or ?error=) redirect from soundvia."""

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        self.server.oauth_code = params.get("code", [None])[0]
        self.server.oauth_state = params.get("state", [None])[0]
        self.server.oauth_error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Authorization complete.</h2>"
            b"<p>You can close this tab and return to the app.</p></body></html>"
        )

    def log_message(self, format, *args):
        pass  # silence default request logging to stdout


def authorize_interactive(
    oauth: SoundviaOAuth, scopes: Iterable[str], port: int = 8888, timeout: int = 120
) -> SoundviaToken:
    """
    Runs the full authorization-code flow for a local script:
      1. Starts a temporary local server on `port` to catch the redirect.
      2. Opens the authorization URL in the user's default browser.
      3. Waits for the callback, verifies `state` (CSRF check), and
         exchanges the returned `code` for a token via fetch_token().

    IMPORTANT: `oauth.redirect_uri` must exactly match a redirect URI
    registered for your app on soundvia (e.g. "http://localhost:8888/callback"),
    including the port number.

    NOTE: fetch_token() is still an unconfirmed placeholder (see its
    docstring) -- this will run the browser + local-server dance correctly,
    but the final token exchange will fail until /oauth/token is confirmed
    against the real docs.
    """
    url, expected_state = oauth.authorization_url(scopes)

    server = HTTPServer(("localhost", port), _OAuthCallbackHandler)
    server.oauth_code = None
    server.oauth_state = None
    server.oauth_error = None

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Opening browser for authorization...")
    webbrowser.open(url)

    thread.join(timeout=timeout)
    if thread.is_alive():
        server.server_close()
        raise SoundviaAuthError("Timed out waiting for authorization callback.")
    server.server_close()

    if server.oauth_error:
        raise SoundviaAuthError(f"Authorization denied or failed: {server.oauth_error}")
    if server.oauth_state != expected_state:
        raise SoundviaAuthError("State mismatch on callback -- possible CSRF, aborting.")
    if not server.oauth_code:
        raise SoundviaAuthError("No authorization code received.")

    return oauth.fetch_token(server.oauth_code)


if __name__ == "__main__":
    # Example 1: build the authorization redirect URL (confirmed flow)
    oauth = SoundviaOAuth(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="YOUR_REDIRECT_URI",
    )
    url, state = oauth.authorization_url(scopes=["user.read", "library.read","now-listening.read"])
    print("Send the user's browser to:", url)
    print("Store this state to verify on callback:", state)

    # Example 2: call the status endpoint directly with a static app token
    client = SoundviaClient.from_token("YOUR_APP_TOKEN")
    status = client.get_status()
    print(f"App '{status.app.name}' (tier={status.app.tier}, "
          f"verification={status.app.verification_status})")
    print(f"Rate limit: {status.app.limits.requests_per_minute} req/min")