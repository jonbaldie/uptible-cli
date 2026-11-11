"""Uptible public connection client."""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from filelock import FileLock, Timeout
from keyring.errors import KeyringError

VERSION = "0.1.0"

class Failure(Exception):
    def __init__(self, code, message, exit_code=1):
        self.code, self.message, self.exit_code = code, message, exit_code
        super().__init__(message)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(NoRedirect())

def request(url, form=None, bearer=None, method=None, _retry=True):
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with OPENER.open(req, timeout=15) as response:
            return json.load(response) if response.status != 204 else None
    except urllib.error.HTTPError as exc:
        if _retry and form is None and method is None and exc.code in (429, 503):
            retry_after = exc.headers.get("Retry-After", "0")
            if retry_after.isdigit() and int(retry_after) <= 2:
                time.sleep(int(retry_after))
                return request(url, bearer=bearer, _retry=False)
        code = "http_error"
        try:
            payload = json.load(exc)
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                code = payload["error"]
        except (ValueError, OSError):
            pass
        raise Failure(code, f"Server rejected request (HTTP {exc.code}).", 3) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise Failure("network_error", "Server request failed or returned invalid JSON.", 3) from None

def issuer_url(value):
    u = urllib.parse.urlsplit(value)
    if not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/") or not (u.scheme == "https" or (u.scheme == "http" and u.hostname == "127.0.0.1")):
        raise Failure("invalid_issuer", "Issuer must be an HTTPS origin or an IPv4 loopback HTTP origin.", 2)
    return value.rstrip("/")

class Store:
    def __init__(self, issuer, client, profile, filename):
        self.identity = hashlib.sha256(json.dumps([issuer, client, profile], separators=(",", ":")).encode()).hexdigest()
        self.path = Path(filename).expanduser() if filename else None
        self.keyring = None
        directory = self.path.parent if self.path else Path.home() / ".cache" / "uptible-cli"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt" and (directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077):
            raise Failure("unsafe_storage", "Credential directory must be private to your user.")
        lock_id = hashlib.sha256(str(self.path.absolute()).encode()).hexdigest() if self.path else self.identity
        self.lock = FileLock(str(directory / (".uptible-" + lock_id + ".lock")), timeout=30, mode=0o600)
        if not self.path:
            try:
                import keyring
                backend = keyring.get_keyring()
                if type(backend).__module__ not in ("keyring.backends.macOS", "keyring.backends.SecretService", "keyring.backends.Windows"):
                    raise RuntimeError()
                self.keyring = keyring
            except (ImportError, RuntimeError):
                raise Failure("no_credential_store", "No supported OS credential store. Select a private file with --credential-file.") from None

    def load(self):
        try:
            if self.path:
                fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd) as f:
                    stat = os.fstat(f.fileno())
                    if os.name != "nt" and (stat.st_uid != os.getuid() or stat.st_mode & 0o077):
                        raise Failure("unsafe_storage", "Credential file must be private to your user.")
                    value = json.load(f)
            else:
                raw = self.keyring.get_password("uptible-cli", self.identity)
                value = json.loads(raw) if raw else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise Failure("storage_error", "Cannot read credentials.") from None
        if value and value.get("identity") != self.identity:
            raise Failure("wrong_connection", "Credential file belongs to another connection.")
        return value

    def save(self, token):
        if not isinstance(token, dict) or not isinstance(token.get("access_token"), str) or not isinstance(token.get("refresh_token"), str) or not isinstance(token.get("expires_in"), (int, float)) or token["expires_in"] <= 0:
            raise Failure("invalid_token_response", "Server did not return usable access and refresh credentials.", 3)
        value = {"identity": self.identity, "access_token": token["access_token"], "refresh_token": token["refresh_token"], "expires_at": time.time() + token["expires_in"]}
        encoded = json.dumps(value)
        if self.keyring:
            self.keyring.set_password("uptible-cli", self.identity, encoded)
        else:
            fd, tmp = tempfile.mkstemp(prefix=".uptible-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(encoded)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        return value

    def delete(self):
        if self.path:
            self.path.unlink(missing_ok=True)
        elif self.load():
            self.keyring.delete_password("uptible-cli", self.identity)

def authorize(issuer, client, browser, timeout):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    result = {}
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(1)
        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if parsed.path != "/callback":
                self.send_error(404)
                return
            if len(query.get("state", [])) != 1 or not hmac.compare_digest(query["state"][0].encode("utf-8"), state.encode("ascii")):
                result["error"] = "state_mismatch"
            elif len(query.get("error", [])) == 1:
                result["error"] = "authorization_denied"
            elif len(query.get("code", [])) == 1 and query["code"][0]:
                result["code"] = query["code"][0]
            else:
                result["error"] = "invalid_callback"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authorization received. You may close this window.")
        def log_message(self, *args):
            pass
    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 0.25
        callback = f"http://127.0.0.1:{server.server_port}/callback"
        query = urllib.parse.urlencode({"response_type":"code", "client_id":client, "redirect_uri":callback, "scope":"account:read", "state":state, "code_challenge":challenge, "code_challenge_method":"S256"})
        url = issuer + "/oauth/authorize?" + query
        def launch():
            try:
                if browser:
                    subprocess.Popen([browser, url], close_fds=True)
                elif not webbrowser.open(url):
                    result["error"] = "browser_failed"
            except OSError:
                result["error"] = "browser_failed"
        threading.Thread(target=launch, daemon=True).start()
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            server.handle_request()
        if "code" not in result:
            raise Failure(result.get("error", "callback_timeout"), "Authorization did not complete. Start login again.")
        return request(issuer + "/oauth/token", {"grant_type":"authorization_code", "client_id":client, "redirect_uri":callback, "code_verifier":verifier, "code":result["code"]})

def run(args):
    issuer = issuer_url(args.issuer)
    if args.command == "auth" and args.action == "login" and not 1 <= args.callback_timeout <= 600:
        raise Failure("invalid_timeout", "Callback timeout must be between 1 and 600 seconds.", 2)
    store = Store(issuer, args.client_id, args.profile, args.credential_file)
    with store.lock:
        token = store.load()
        if args.command == "auth" and args.action == "login":
            if token:
                raise Failure("already_connected", "Connection already exists. Log out before login.")
            token = authorize(issuer, args.client_id, args.browser_driver, args.callback_timeout)
            token = store.save(token)
            account = request(issuer + "/api/v1/account", bearer=token["access_token"])
            return {"connected": True, "account": account}
        if args.command == "auth" and args.action == "logout" and args.local:
            store.delete()
            return {"connected": False, "revoked": False}
        if not token:
            if args.command == "auth" and args.action == "status":
                return {"connected": False}
            raise Failure("not_connected", "No saved connection. Run auth login.")
        if time.time() >= token["expires_at"]:
            token = store.save(request(issuer + "/oauth/token", {"grant_type":"refresh_token", "client_id":args.client_id, "refresh_token":token["refresh_token"]}))
        if args.command == "auth" and args.action == "logout":
            request(issuer + "/api/v1/logout", form={}, bearer=token["access_token"])
            store.delete()
            return {"connected": False, "revoked": True}
        account = request(issuer + "/api/v1/account", bearer=token["access_token"])
        return {"connected": True, "account": account} if args.command == "auth" else account

def main():
    p = argparse.ArgumentParser(prog="uptible", description="Connect to an Uptible account.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--issuer", required=True, help="HTTPS server origin")
    p.add_argument("--client-id", required=True, help="registered public client identifier")
    p.add_argument("--profile", default="default", help="local connection name")
    p.add_argument("--credential-file", help="explicit private credential file")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth").add_subparsers(dest="action", required=True)
    login = auth.add_parser("login")
    login.add_argument("--browser-driver", help="executable that receives the authorization URL")
    login.add_argument("--callback-timeout", type=int, default=120)
    auth.add_parser("status")
    logout = auth.add_parser("logout")
    logout.add_argument("--local", action="store_true", help="forget locally without revoking the server grant")
    account = sub.add_parser("account").add_subparsers(dest="action", required=True)
    account.add_parser("show")
    args = p.parse_args()
    try:
        result = run(args)
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
    except Timeout:
        exc = Failure("storage_busy", "Connection is busy. Try again.")
        if args.json:
            print(json.dumps({"error": {"code": exc.code, "message": exc.message}}, sort_keys=True), file=sys.stderr)
        else:
            print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError, KeyError, TypeError, KeyringError):
        exc = Failure("client_error", "The operation could not be completed. Check the connection and credential store.")
        if args.json:
            print(json.dumps({"error": {"code": exc.code, "message": exc.message}}, sort_keys=True), file=sys.stderr)
        else:
            print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except Failure as exc:
        if args.json:
            print(json.dumps({"error": {"code": exc.code, "message": exc.message}}, sort_keys=True), file=sys.stderr)
        else:
            print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    return 0
