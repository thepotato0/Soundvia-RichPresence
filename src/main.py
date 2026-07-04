from soundvia import SoundviaClient, SoundviaOAuth, SoundviaToken, SoundviaAuthError, authorize_interactive
from dotenv import load_dotenv
from urllib.parse import urlparse
import discordrpc
import logging
import time
import sys
import os
import json
import requests

logger = logging.getLogger(__name__.replace("_", ""))

# Not to be confused with APP_TOKEN
APPID = "1522642631472185465"
USER_TOKEN_CACHE = "user_token.json"


class App:
    def __init__(self, logging_level: int = logging.DEBUG, app_id: str = APPID, poll_interval: int = 15):
        self.app_id = app_id
        self.poll_interval = poll_interval  # Discord rate-limits activity updates to ~1 per 15s
        self.rpc = None
        self.logging_level = logging_level
        self.APP_TOKEN = None
        self.oauth = None
        self.user_token = None
        self.setup_logging()
        logger.info("App started")

        if self.load_app_token():
            logger.critical("Could not read APP_TOKEN from .env file! Exiting in 3 seconds")
            self.shutdown()
        else:
            logger.debug("Read APP_TOKEN from .env")

        self.SVclient = SoundviaClient.from_token(self.APP_TOKEN)
        try:
            status = self.SVclient.get_status()
            if not status.ok:
                logger.critical("Invalid app token! Exiting in 3 seconds")
                self.shutdown()
            else:
                logger.debug("Valid app token")
        except requests.exceptions.RequestException:
            logger.critical("Could not validate app token! Exiting in 3 seconds")
            self.shutdown()

        self.setup_user_auth()

        try:
            self.start_discord_presence()
            self.run_forever()
        except discordrpc.exceptions.DiscordNotOpened:
            logger.critical("Could not find Discord. Is Discord running? Exiting in 3 seconds.")
            self.shutdown()
        except Exception:
            logger.exception("Unexpected error while starting Discord presence.")
            self.shutdown()
        except KeyboardInterrupt:
            logger.info("Shutting down.")
            self.shutdown(0, 0)

    def setup_logging(self):
        logger.setLevel(self.logging_level)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            ))
            logger.addHandler(handler)
        else:
            handler = logger.handlers[0]
        discord_log = logging.getLogger("Discord RPC")
        discord_log.setLevel(self.logging_level)
        discord_log.propagate = False
        if not discord_log.handlers:
            discord_log.addHandler(handler)

    def load_app_token(self) -> bool:
        load_dotenv()
        self.APP_TOKEN = os.getenv("APP_TOKEN")
        return self.APP_TOKEN is None

    def setup_user_auth(self):
        """
        Obtains a user-level OAuth token, required for "now listening" data
        (APP_TOKEN only proves the app itself, not a specific user).

        Order of preference:
          1. Reuse a cached token from disk if present and not expired.
          2. If expired but a refresh_token exists, refresh it.
          3. Otherwise, run the full interactive browser login.
        """
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")
        redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:8888/callback")

        if not client_id or not client_secret:
            logger.critical("CLIENT_ID / CLIENT_SECRET missing from .env! Exiting in 3 seconds")
            self.shutdown()
            return

        self.oauth = SoundviaOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)

        cached = self._load_cached_user_token()
        if cached and not cached.is_expired:
            logger.debug("Reusing cached user token.")
            self.user_token = cached
            return

        if cached and cached.refresh_token:
            try:
                logger.debug("Cached user token expired, attempting refresh...")
                self.user_token = self.oauth.refresh(cached)
                self._save_cached_user_token(self.user_token)
                return
            except SoundviaAuthError:
                logger.warning("Refresh failed, falling back to interactive login.")

        logger.info("No valid user token found -- opening browser for authorization.")
        # Port must match whatever's registered as the redirect URI on soundvia's dashboard
        port = urlparse(redirect_uri).port or 8888
        try:
            self.user_token = authorize_interactive(
                self.oauth, scopes=["user.read", "library.read"], port=port
            )
            self._save_cached_user_token(self.user_token)
        except SoundviaAuthError:
            logger.exception("User authorization failed.")
            self.shutdown()

    def _load_cached_user_token(self):
        if not os.path.exists(USER_TOKEN_CACHE):
            return None
        try:
            with open(USER_TOKEN_CACHE, "r") as f:
                data = json.load(f)
            return SoundviaToken(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Cached user token file is corrupt, ignoring it.")
            return None

    def _save_cached_user_token(self, token: SoundviaToken):
        with open(USER_TOKEN_CACHE, "w") as f:
            json.dump(token.__dict__, f)
        logger.debug("Saved user token to cache.")

    def start_discord_presence(self):
        self.rpc = discordrpc.RPC(app_id=self.app_id)  # debug=True)
        self.rpc.set_activity(
            details="Idling",
            act_type=discordrpc.Activity.Listening,
        )
        logger.info("Activity set to Idling until now-playing data is retrieved.")

    def run_forever(self):
        """
        replaces rpc.run() — keeps the process (and pipe) alive,
        while also giving you a hook to refresh the listening activity.
        """
        while True:
            self.update_now_playing()
            time.sleep(self.poll_interval)

    def update_now_playing(self):
        # TODO fetch real now-playing info and call self.rpc.set_activity(...)
        logger.debug("Polling for now-playing data...")

    def shutdown(self, wait_seconds: int = 3, status_code: int = 1):
        time.sleep(wait_seconds)
        if self.rpc:
            self.rpc.disconnect()
        sys.exit(status_code)


if __name__ == "__main__":
    app = App()