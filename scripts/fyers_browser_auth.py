#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from fyers_apiv3 import fyersModel


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


CLIENT_ID = required_env("FYERS_CLIENT_ID")
SECRET_KEY = required_env("FYERS_SECRET_KEY")
REDIRECT_URI = os.environ.get("FYERS_REDIRECT_URI", "http://127.0.0.1:8080/").strip() or "http://127.0.0.1:8080/"
INSECURE_SSL = os.environ.get("FYERS_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes"}
CA_BUNDLE = os.environ.get("FYERS_CA_BUNDLE", "").strip()
BROWSER = os.environ.get("FYERS_BROWSER", "firefox").strip().lower()
STATE = os.environ.get("FYERS_AUTH_STATE", "projectx-auth").strip() or "projectx-auth"


class CallbackState:
    code: str | None = None
    error: str | None = None
    params: dict[str, list[str]] | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        CallbackState.params = {k: v for k, v in query.items()}
        CallbackState.code = (
            query.get("auth_code", [None])[0]
            or query.get("code", [None])[0]
        )
        CallbackState.error = query.get("error", [None])[0]

        print("Callback path:", self.path, flush=True)
        print("Callback query params:", CallbackState.params, flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Login complete. You can close this tab.")

    def log_message(self, format: str, *args) -> None:
        return


def start_server() -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 8080), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def update_env_file(token: str, env_path: str = ".env") -> None:
    path = Path(env_path)
    lines = path.read_text().splitlines() if path.exists() else []

    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith("FYERS_ACCESS_TOKEN="):
            new_lines.append(f"FYERS_ACCESS_TOKEN={token}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"FYERS_ACCESS_TOKEN={token}")

    path.write_text("\n".join(new_lines) + "\n")


def patch_ssl() -> None:
    if CA_BUNDLE:
        os.environ["REQUESTS_CA_BUNDLE"] = CA_BUNDLE
        os.environ["SSL_CERT_FILE"] = CA_BUNDLE
        print(f"Using custom CA bundle: {CA_BUNDLE}")
        return

    if INSECURE_SSL:
        print("WARNING: SSL verification disabled for FYERS token exchange")
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

        old_post = requests.post
        old_request = requests.sessions.Session.request

        def patched_post(*args, **kwargs):
            kwargs["verify"] = False
            return old_post(*args, **kwargs)

        def patched_request(self, method, url, **kwargs):
            kwargs["verify"] = False
            return old_request(self, method, url, **kwargs)

        requests.post = patched_post  # type: ignore[assignment]
        requests.sessions.Session.request = patched_request  # type: ignore[assignment]


def open_browser(url: str) -> None:
    print(f"Opening FYERS login in browser: {BROWSER}")
    print(url)

    if BROWSER == "firefox":
        try:
            browser = webbrowser.get("firefox")
            browser.open(url, new=1, autoraise=True)
            return
        except webbrowser.Error:
            pass

    webbrowser.open(url, new=1, autoraise=True)


def main() -> None:
    patch_ssl()

    server = start_server()
    try:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID,
            secret_key=SECRET_KEY,
            redirect_uri=REDIRECT_URI,
            response_type="code",
            grant_type="authorization_code",
            state=STATE,
        )

        auth_url = session.generate_authcode()
        open_browser(auth_url)

        deadline = time.time() + 180
        while time.time() < deadline:
            if CallbackState.code or CallbackState.error or CallbackState.params:
                break
            time.sleep(0.5)

        if CallbackState.error:
            raise RuntimeError(f"FYERS returned error: {CallbackState.error}")

        if not CallbackState.code:
            raise RuntimeError(
                "Did not capture auth code. Callback params were:\n"
                + json.dumps(CallbackState.params, indent=2)
            )

        print(f"Captured auth code: {CallbackState.code}")
        print("Received auth code, exchanging for access token...")

        session.set_token(CallbackState.code)
        token_response = session.generate_token()

        if not isinstance(token_response, dict):
            raise RuntimeError(f"Unexpected token response: {token_response!r}")

        access_token = token_response.get("access_token")
        if not access_token:
            raise RuntimeError("Token exchange failed:\n" + json.dumps(token_response, indent=2))

        update_env_file(access_token)
        print(json.dumps({
            "ok": True,
            "message": "FYERS access token saved to .env",
            "token_preview": access_token[:24] + "..."
        }, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
