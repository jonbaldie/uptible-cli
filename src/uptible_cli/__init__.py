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
DEFAULT_ISSUER = "https://uptible.com"
DEFAULT_CLIENT_ID = "5af9087d-4c3a-4bb9-a144-3cbf5560771a"
SERVER_ERRORS = {"invalid_request", "invalid_client", "invalid_grant", "unauthorized_client", "unsupported_grant_type", "invalid_scope", "access_denied", "temporarily_unavailable", "server_error"}

class Failure(Exception):
    def __init__(self, code, message, exit_code=1):
        self.code, self.message, self.exit_code = code, message, exit_code
        super().__init__(message)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(NoRedirect())

def request(url, form=None, bearer=None, method=None, _retry=True, payload=None, extra_headers=None):
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    else:
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
        fields = []
        try:
            payload = json.load(exc)
            if isinstance(payload, dict) and isinstance(payload.get("error"), str) and payload["error"] in SERVER_ERRORS:
                code = payload["error"]
            if exc.code == 422 and isinstance(payload, dict) and isinstance(payload.get("errors"), dict):
                allowed = {"message", "url_capture", "url_display", "display_maps_only", "custom_delay_x_seconds", "display_last_x_conversions", "revision"}
                fields = sorted(allowed.intersection(payload["errors"]))
        except (ValueError, OSError):
            pass
        message = f"Server rejected request (HTTP {exc.code})."
        if fields:
            message += " Check these fields: " + ", ".join(fields) + "."
        if exc.code == 403:
            message += " Check lifetime access and permissions for this connection."
        elif exc.code == 409:
            message += " Check the request identity or current revision before retrying."
        failure = Failure(code, message, 3)
        failure.http_status = exc.code
        raise failure from None
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
        path = Path(filename).expanduser() if filename else None
        self.path = path.parent.resolve() / path.name if path else None
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

    def validate(self, token):
        if not isinstance(token, dict) or not isinstance(token.get("access_token"), str) or not isinstance(token.get("refresh_token"), str) or not isinstance(token.get("expires_in"), (int, float)) or token["expires_in"] <= 0:
            raise Failure("invalid_token_response", "Server did not return usable access and refresh credentials.", 3)
        return {"identity": self.identity, "access_token": token["access_token"], "refresh_token": token["refresh_token"], "expires_at": time.time() + token["expires_in"]}

    def save(self, token):
        value = self.validate(token)
        self.write(value)
        return value

    def write(self, value):
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

    def delete(self):
        if self.path:
            self.path.unlink(missing_ok=True)
        elif self.load():
            self.keyring.delete_password("uptible-cli", self.identity)

def authorize(issuer, client, browser, timeout, delete_leads=False, events=False, billing=False):
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
            self.wfile.write(b"Authorization received. You may close this window." if "code" in result else b"Authorization was not completed. You may close this window.")
        def log_message(self, *args):
            pass
    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 0.25
        callback = f"http://127.0.0.1:{server.server_port}/callback"
        query = urllib.parse.urlencode({"response_type":"code", "client_id":client, "redirect_uri":callback, "scope":"account:read notifications:read notifications:write installation:read activity:read leads:read statistics:read" + (" leads:delete" if delete_leads else "") + (" events:write" if events else "") + (" billing:read" if billing else ""), "state":state, "code_challenge":challenge, "code_challenge_method":"S256"})
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
            error = result.get("error", "callback_timeout")
            message = "Could not open a browser. Set a default browser and start login again." if error == "browser_failed" else "Authorization did not complete. Start login again."
            raise Failure(error, message)
        try:
            return request(issuer + "/oauth/token", {"grant_type":"authorization_code", "client_id":client, "redirect_uri":callback, "code_verifier":verifier, "code":result["code"]})
        except Failure as exc:
            if getattr(exc, "http_status", None) == 400 and exc.code in {"invalid_request", "invalid_client", "invalid_grant", "unauthorized_client", "unsupported_grant_type", "invalid_scope"}:
                raise
            raise Failure("login_uncertain", "A grant may have been created. Check your account connections and revoke any unintended connection before retrying.", 3) from None

def run(args):
    issuer = issuer_url(args.issuer or DEFAULT_ISSUER)
    if issuer != DEFAULT_ISSUER and not args.client_id:
        raise Failure("client_id_required", "An alternate service requires its registered public client ID via --client-id.", 2)
    args.client_id = args.client_id or DEFAULT_CLIENT_ID
    if args.command == "auth" and args.action == "login" and not 1 <= args.callback_timeout <= 600:
        raise Failure("invalid_timeout", "Callback timeout must be between 1 and 600 seconds.", 2)
    if args.command == "leads" and args.action == "delete" and not args.yes:
        if not sys.stdin.isatty():
            raise Failure("confirmation_required", "Deletion requires confirmation. Use --yes for noninteractive deletion.", 2)
        print(f"Permanently delete lead {args.id}? [y/N] ", end="", file=sys.stderr, flush=True)
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            raise Failure("delete_cancelled", "Deletion cancelled.")
    store = Store(issuer, args.client_id, args.profile, args.credential_file)
    with store.lock:
        token = store.load()
        if args.command == "auth" and args.action == "login":
            if token:
                raise Failure("already_connected", "Connection already exists. Log out before login.")
            token = authorize(issuer, args.client_id, args.browser_driver, args.callback_timeout, args.delete_leads, args.events, args.billing)
            try:
                validated = store.validate(token)
                account = request(issuer + "/api/v1/account", bearer=validated["access_token"])
                store.save(token)
            except (Failure, OSError, ValueError, TypeError, KeyringError) as exc:
                access = token.get("access_token") if isinstance(token, dict) else None
                if isinstance(access, str) and access:
                    try:
                        request(issuer + "/api/v1/logout", form={}, bearer=access)
                    except Failure:
                        raise Failure("cleanup_unconfirmed", "Login failed and grant revocation could not be confirmed. Revoke the connection in your account before retrying.", 3) from None
                else:
                    raise Failure("login_uncertain", "A grant may have been created. Check your account connections and revoke any unintended connection before retrying.", 3) from None
                raise exc
            return {"connected": True, "account": account}
        if args.command == "auth" and args.action == "logout" and args.local:
            store.delete()
            return {"connected": False, "revoked": False}
        if not token:
            if args.command == "auth" and args.action == "status":
                return {"connected": False}
            raise Failure("not_connected", "No saved connection. Run auth login.")
        if token.get("refresh_pending"):
            raise Failure("refresh_uncertain", "A refresh may have been consumed. Revoke the connection in your account, then use auth logout --local and reconnect.", 3)
        if time.time() >= token["expires_at"]:
            token["refresh_pending"] = True
            store.write(token)
            token = store.save(request(issuer + "/oauth/token", {"grant_type":"refresh_token", "client_id":args.client_id, "refresh_token":token["refresh_token"]}))
        if args.command == "auth" and args.action == "logout":
            request(issuer + "/api/v1/logout", form={}, bearer=token["access_token"])
            store.delete()
            return {"connected": False, "revoked": True}
        def authenticated(url, **kwargs):
            nonlocal token
            try:
                return request(url, bearer=token["access_token"], **kwargs)
            except Failure as exc:
                if getattr(exc, "http_status", None) == 401:
                    token["refresh_pending"] = True
                    store.write(token)
                    token = store.save(request(issuer + "/oauth/token", {"grant_type": "refresh_token", "client_id": args.client_id, "refresh_token": token["refresh_token"]}))
                    if kwargs.get("method"):
                        raise Failure("operation_not_retried", "The connection was refreshed. The write was not retried. For event submissions, retry the exact command with the same IDs and payload. For create, reuse the same key and input.", 3) from None
                    return request(url, bearer=token["access_token"], **kwargs)
                if (exc.code == "network_error" or getattr(exc, "http_status", 0) >= 500) and args.command == "leads" and args.action == "delete":
                    raise Failure("delete_uncertain", "The deletion outcome is unknown. Check the lead before deciding whether to retry.", 3) from None
                if (exc.code == "network_error" or getattr(exc, "http_status", 0) >= 500) and args.command == "notifications" and args.action == "create":
                    raise Failure("create_uncertain", "The create outcome is unknown. Retry the same input with the same idempotency key.", 3) from None
                if (exc.code == "network_error" or getattr(exc, "http_status", 0) >= 500) and args.command == "events":
                    raise Failure("event_uncertain", "The event outcome is unknown. Retry the exact command with the same IDs and payload.", 3) from None
                raise
        if args.command == "events":
            payload = {"session_id": args.session_id, "event_id": args.event_id}
            if args.action == "capture":
                payload["email"] = args.email
                if args.name is not None:
                    payload["name"] = args.name
            result = authenticated(issuer + "/api/v1/notifications/" + str(args.id) + "/" + args.action, method="POST", payload=payload)
            if not isinstance(result, dict) or set(result) != {"receipt", "status"} or not isinstance(result["receipt"], str) or not result["receipt"] or result["status"] != "processed":
                raise Failure("event_uncertain", "The server returned an invalid receipt. Retry the exact command with the same IDs and payload.", 3)
            return result
        if args.command == "billing":
            params = {key: value for key, value in (("cursor", args.cursor), ("claim_cursor", args.claim_cursor)) if value is not None}
            query = "?" + urllib.parse.urlencode(params) if params else ""
            return authenticated(issuer + "/api/v1/billing" + query)
        if args.command in ("auth", "account"):
            account = authenticated(issuer + "/api/v1/account")
            return {"connected": True, "account": account} if args.command == "auth" else account
        if args.command == "stats":
            return authenticated(issuer + "/api/v1/statistics")
        if args.command == "installation":
            return authenticated(issuer + "/api/v1/installation")
        if args.command == "leads":
            path = issuer + "/api/v1/leads"
            if args.action == "list":
                params = {"limit": args.limit}
                params.update({key: value for key, value in (("notification_id", args.notification_id), ("from", args.date_from), ("until", args.until), ("cursor", args.cursor)) if value is not None})
                return authenticated(path + "?" + urllib.parse.urlencode(params))
            path += "/" + str(args.id)
            return authenticated(path, method="DELETE") if args.action == "delete" else authenticated(path)
        path = issuer + "/api/v1/notifications"
        if args.action == "list":
            params = {"limit": args.limit}
            if args.after is not None:
                params["after"] = args.after
            return authenticated(path + "?" + urllib.parse.urlencode(params))
        if args.action == "create":
            return authenticated(path, method="POST", payload=notification_payload(args), extra_headers={"Idempotency-Key": args.idempotency_key})
        path += "/" + str(args.id)
        if args.action == "show":
            return authenticated(path)
        if args.action == "activity":
            return authenticated(path + "/activity")
        if args.action == "edit":
            payload = notification_payload(args)
            payload["revision"] = args.revision
            return authenticated(path, method="PUT", payload=payload)
        return authenticated(path + "/" + args.action, method="PUT", payload={})

def notification_payload(args):
    return {name: getattr(args, name) for name in ("message", "url_capture", "url_display", "display_maps_only", "custom_delay_x_seconds", "display_last_x_conversions") if getattr(args, name) is not None}

def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number

def create_key(value):
    import re
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value):
        raise argparse.ArgumentTypeError("use 1 to 128 ASCII letters, digits, periods, underscores or hyphens")
    return value

def event_id(value):
    if not value or len(value) > 128:
        raise argparse.ArgumentTypeError("must contain 1 to 128 characters")
    return value

def notification_fields(parser):
    parser.add_argument("--message", required=True)
    parser.add_argument("--url-capture")
    parser.add_argument("--url-display")
    parser.add_argument("--display-maps-only", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--custom-delay-x-seconds", type=int)
    parser.add_argument("--display-last-x-conversions", type=int)

def main():
    p = argparse.ArgumentParser(prog="uptible", description="Connect to an Uptible account.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--issuer", help="alternate HTTPS server origin (default: https://uptible.com; requires --client-id)")
    p.add_argument("--client-id", help="alternate registered public client identifier")
    p.add_argument("--profile", default="default", help="local connection name")
    p.add_argument("--credential-file", help="explicit private credential file")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth").add_subparsers(dest="action", required=True)
    login = auth.add_parser("login")
    login.add_argument("--delete-leads", action="store_true", help="request permission to permanently delete leads during browser consent")
    login.add_argument("--events", action="store_true", help="request permission to submit events")
    login.add_argument("--billing", action="store_true", help="request permission to read billing")
    login.add_argument("--browser-driver", help="executable that receives the authorization URL")
    login.add_argument("--callback-timeout", type=int, default=120)
    auth.add_parser("status")
    logout = auth.add_parser("logout")
    logout.add_argument("--local", action="store_true", help="forget locally without revoking the server grant")
    account = sub.add_parser("account").add_subparsers(dest="action", required=True)
    account.add_parser("show")
    stats = sub.add_parser("stats", help="show dashboard statistics").add_subparsers(dest="action", required=True)
    stats.add_parser("show", description="Show lifetime customer dashboard statistics. Capture counts use active, non-archived owned notifications. Hour and day counts cover the preceding hour and 24 hours in inclusive rolling UTC windows ending at as_of. Tracks include all account history. Results may be cached for one second.")
    installation = sub.add_parser("installation").add_subparsers(dest="action", required=True)
    installation.add_parser("show")
    leads = sub.add_parser("leads", help="browse or permanently delete collected leads").add_subparsers(dest="action", required=True)
    lead_list = leads.add_parser("list", description="List one page, including leads from inactive and archived notifications. Dates are UTC; --from is inclusive and --until is exclusive. Pass next_cursor as --cursor with the same filters.")
    lead_list.add_argument("--limit", type=positive, default=20, choices=range(1, 101), metavar="1-100")
    lead_list.add_argument("--notification-id", type=positive)
    lead_list.add_argument("--from", dest="date_from", help="inclusive UTC date (YYYY-MM-DD)")
    lead_list.add_argument("--until", help="exclusive UTC date (YYYY-MM-DD)")
    lead_list.add_argument("--cursor", help="opaque next_cursor from the previous page")
    lead_show = leads.add_parser("show")
    lead_show.add_argument("id", type=positive)
    lead_delete = leads.add_parser("delete", description="Permanently delete one lead. If the outcome is unknown, check the lead before retrying. To request deletion permission at initial login, use auth login --delete-leads.")
    lead_delete.add_argument("id", type=positive)
    lead_delete.add_argument("--yes", action="store_true", help="confirm permanent deletion without prompting")
    events = sub.add_parser("events", help="submit events for a live notification").add_subparsers(dest="action", required=True)
    for action in ("capture", "track"):
        event = events.add_parser(action, description="Retry an uncertain submission with the exact same IDs and payload. A processed receipt confirms processing.")
        event.add_argument("id", type=positive, help="notification ID")
        event.add_argument("--session-id", required=True, type=event_id)
        event.add_argument("--event-id", required=True, type=event_id)
        if action == "capture":
            event.add_argument("--email", required=True)
            event.add_argument("--name")
    billing = sub.add_parser("billing", help="read lifetime billing status").add_subparsers(dest="action", required=True)
    status = billing.add_parser("status", description="Read billing status. Purchase eligibility does not guarantee checkout availability.")
    status.add_argument("--cursor", help="next_cursor for older orders")
    status.add_argument("--claim-cursor", help="next_claim_cursor for older purchase references")
    notifications = sub.add_parser("notifications").add_subparsers(dest="action", required=True)
    listing = notifications.add_parser("list")
    listing.add_argument("--limit", type=positive, default=20, choices=range(1, 101), metavar="1-100")
    listing.add_argument("--after", type=positive)
    create = notifications.add_parser("create")
    create.add_argument("--idempotency-key", required=True, type=create_key, help="stable unique key to reuse if the outcome is uncertain")
    notification_fields(create)
    edit = notifications.add_parser("edit")
    edit.add_argument("id", type=positive)
    edit.add_argument("--revision", type=positive, required=True)
    notification_fields(edit)
    for action in ("show", "activity", "activate", "deactivate", "archive", "restore"):
        command = notifications.add_parser(action)
        command.add_argument("id", type=positive)
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
