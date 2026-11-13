"""Uptible public connection client."""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from filelock import FileLock, Timeout
from keyring.errors import KeyringError

VERSION = "0.1.0"
DEFAULT_ISSUER = "https://uptible.com"
DEFAULT_CLIENT_ID = "5af9087d-4c3a-4bb9-a144-3cbf5560771a"
SERVER_ERRORS = {"invalid_request", "invalid_client", "invalid_grant", "unauthorized_client", "unsupported_grant_type", "invalid_scope", "access_denied", "temporarily_unavailable", "server_error"}

PROBLEM_ERRORS = {"bad_request", "unauthenticated", "forbidden", "not_found", "method_not_allowed", "conflict", "validation_error", "rate_limited", "upstream_unavailable", "internal_error", "request_error"}
VALIDATION_FIELDS = {"message", "url_capture", "url_display", "display_maps_only", "custom_delay_x_seconds", "display_last_x_conversions", "revision", "email", "name", "session_id", "event_id", "limit", "after", "notification_id", "from", "until", "cursor", "claim_cursor"}

class Failure(Exception):
    def __init__(self, code, message, exit_code=1, *, http_status=0, correlation_id=None, fields=(), server_code=None):
        self.code, self.message, self.exit_code = code, message, exit_code
        self.http_status, self.correlation_id = http_status, correlation_id
        self.fields, self.server_code = fields, server_code
        super().__init__(message)

    def reframe(self, code, message, exit_code=3):
        return Failure(code, message, exit_code, http_status=self.http_status,
                       correlation_id=self.correlation_id, fields=self.fields, server_code=self.server_code)

    def output(self):
        error = {"code": self.code, "message": self.message}
        if self.http_status:
            error["http_status"] = self.http_status
        if self.correlation_id:
            error["correlation_id"] = self.correlation_id
        if self.fields:
            error["fields"] = list(self.fields)
        if self.server_code and self.server_code != self.code:
            error["server_code"] = self.server_code
        return {"error": error}

def http_failure(status, payload):
    code, correlation, fields = "http_error", None, ()
    if isinstance(payload, dict):
        problem, oauth = payload.get("code"), payload.get("error")
        if isinstance(problem, str) and problem in PROBLEM_ERRORS:
            code = problem
        elif isinstance(oauth, str) and oauth in SERVER_ERRORS:
            code = oauth
        value = payload.get("correlation_id")
        if isinstance(value, str):
            try:
                parsed = str(uuid.UUID(value))
                if parsed == value.lower():
                    correlation = parsed
            except ValueError:
                pass
        if status == 422 and isinstance(payload.get("errors"), dict):
            fields = tuple(sorted(VALIDATION_FIELDS.intersection(payload["errors"])))
    message = f"Server rejected request (HTTP {status})."
    if fields:
        message += " Check these fields: " + ", ".join(fields) + "."
    if status == 403:
        message += " Check lifetime access and permissions for this connection."
    elif status == 409:
        message += " Check the request identity or current revision before retrying."
    return Failure(code, message, 3, http_status=status, correlation_id=correlation,
                   fields=fields, server_code=code if code != "http_error" else None)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(NoRedirect())

def request(url, form=None, bearer=None, method=None, _retry=True, payload=None, extra_headers=None, expected_status=None):
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
        try:
            with OPENER.open(req, timeout=15) as response:
                if expected_status is not None and response.status != expected_status:
                    raise Failure("unexpected_response", "Server returned an unexpected response.", 3)
                return json.load(response) if response.status != 204 else None
        except urllib.error.HTTPError as exc:
            body = exc.read()
            payload = json.loads(body) if body else None
            if _retry and form is None and method is None and exc.code in (429, 503):
                retry_after = exc.headers.get("Retry-After", "0")
                if retry_after.isdigit() and int(retry_after) <= 2:
                    time.sleep(int(retry_after))
                    return request(url, bearer=bearer, _retry=False)
            raise http_failure(exc.code, payload) from None
    except Failure:
        raise
    except (Exception, KeyboardInterrupt):
        raise Failure("network_error", "Server request failed or returned invalid JSON.", 3) from None

def issuer_url(value):
    try:
        u = urllib.parse.urlsplit(value)
        port = u.port
        valid = (u.hostname and not u.username and not u.password and not u.query and not u.fragment
                 and u.path in ("", "/") and not any(ord(c) <= 32 or c == "\\" for c in value)
                 and (port is None or 1 <= port <= 65535)
                 and (u.scheme == "https" or (u.scheme == "http" and u.hostname == "127.0.0.1")))
    except ValueError:
        valid = False
    if not valid:
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

def authorize(issuer, client, browser, timeout, delete_leads=False, events=False, billing=False, delete_notifications=False, scopes=None, email_change=False):
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
        query = urllib.parse.urlencode({"response_type":"code", "client_id":client, "redirect_uri":callback, "scope":scopes or ("account:read notifications:read notifications:write installation:read activity:read leads:read statistics:read" + (" leads:delete" if delete_leads else "") + (" events:write" if events else "") + (" billing:read" if billing else "") + (" notifications:delete" if delete_notifications else "") + (" account:email:write" if email_change else "")), "state":state, "code_challenge":challenge, "code_challenge_method":"S256"})
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
            raise exc.reframe("login_uncertain", "A grant may have been created. Check your account connections and revoke any unintended connection before retrying.") from None

def granted_scopes(access):
    try:
        encoded = access.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        scopes = claims["scopes"]
        if not isinstance(scopes, list) or not scopes or any(not isinstance(scope, str) or not scope for scope in scopes):
            raise ValueError()
        return set(scopes)
    except Exception:
        raise Failure("scope_unknown", "Cannot determine existing permissions. The connection remains unchanged.", 3) from None

def account_id(account):
    if not isinstance(account, dict) or type(account.get("id")) is not int:
        raise Failure("account_unknown", "Cannot verify the connected account.", 3)
    return account["id"]

def token_subject(access):
    try:
        encoded = access.split(".")[1]
        subject = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["sub"]
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal() or int(subject) < 1:
            raise ValueError()
        return int(subject)
    except Exception:
        raise Failure("account_unknown", "Cannot verify the connected account. The connection remains unchanged.", 3) from None

def recovery_instructions(args):
    options = ["--json"] if getattr(args, "json", False) else []
    if args.issuer:
        options.append("--issuer=" + args.issuer)
    if args.client_id != DEFAULT_CLIENT_ID or args.issuer:
        options.append("--client-id=" + args.client_id)
    if args.profile != "default":
        options.append("--profile=" + args.profile)
    if args.credential_file is not None:
        options.append("--credential-file=" + args.credential_file)
    command = ["uptible", *options, "auth"]
    logout = shlex.join([*command, "logout", "--local"])
    login = shlex.join([*command, "login"])
    return "Revoke the connection in your account, then run these commands to reconnect:\n" + logout + "\n" + login

def refresh_connection(issuer, client, store, original, recovery, scopes=None):
    old_id = original.get("account_id")
    if type(old_id) is not int:
        try:
            old_id = token_subject(original["access_token"])
        except Failure as exc:
            raise exc.reframe(exc.code, exc.message + " " + recovery, exc.exit_code) from None
    original["refresh_pending"] = True
    store.write(original)
    refreshed = store.validate(request(issuer + "/oauth/token", {"grant_type":"refresh_token", "client_id":client, "refresh_token":original["refresh_token"]}))
    try:
        if scopes is not None:
            refreshed_scopes = granted_scopes(refreshed["access_token"])
        account = request(issuer + "/api/v1/account", bearer=refreshed["access_token"])
        refreshed_id = account_id(account)
    except Failure as exc:
        raise exc.reframe("refresh_uncertain", "Cannot verify the refreshed connection. " + recovery) from None
    if scopes is not None and refreshed_scopes != scopes:
        raise Failure("refresh_permissions_changed", "The refreshed connection has different permissions. " + recovery, 3)
    if refreshed_id != old_id:
        raise Failure("refresh_account_changed", "The refreshed connection belongs to a different account. It was not saved. " + recovery, 3)
    refreshed["account_id"] = old_id
    store.write(refreshed)
    return refreshed, account

def upgrade(args, issuer, store, original, recovery):
    additions = {scope for selected, scope in ((args.delete_leads, "leads:delete"), (args.events, "events:write"), (args.billing, "billing:read"), (args.delete_notifications, "notifications:delete"), (args.email_change, "account:email:write")) if selected}
    if original.get("refresh_pending"):
        raise Failure("refresh_uncertain", "The existing refresh outcome is unknown. " + recovery, 3)
    if not additions:
        raise Failure("permissions_required", "Select at least one permission to add.", 2)
    try:
        old_scopes = granted_scopes(original["access_token"])
    except Failure as exc:
        raise exc.reframe(exc.code, exc.message + " " + recovery, exc.exit_code) from None
    if time.time() >= original["expires_at"]:
        original, old_account = refresh_connection(issuer, args.client_id, store, original, recovery, old_scopes)
    else:
        old_account = request(issuer + "/api/v1/account", bearer=original["access_token"])
    old_id = account_id(old_account)
    scopes = old_scopes | additions
    new = authorize(issuer, args.client_id, args.browser_driver, args.callback_timeout, scopes=" ".join(sorted(scopes)))
    access = new.get("access_token") if isinstance(new, dict) else None
    try:
        validated = store.validate(new)
        new_account = request(issuer + "/api/v1/account", bearer=validated["access_token"])
        if account_id(new_account) != old_id:
            raise Failure("account_mismatch", "The approved account differs from the connected account. The existing connection was retained.", 3)
        approved_scopes = granted_scopes(validated["access_token"])
        if not scopes <= approved_scopes:
            raise Failure("permissions_missing", "The approved connection did not retain all requested permissions.", 3)
        if approved_scopes != scopes:
            raise Failure("permissions_unexpected", "The approved connection included unrequested permissions. The existing connection was retained.", 3)
        validated["account_id"] = old_id
        store.write(validated)
    except (Failure, OSError, ValueError, TypeError, KeyringError) as exc:
        try:
            saved = store.load()
        except (Failure, OSError, ValueError, TypeError, KeyringError):
            raise Failure("storage_uncertain", "Cannot confirm which credential was saved. Check account connections before retrying.", 3) from None
        if saved != original:
            raise Failure("storage_uncertain", "Cannot confirm which credential was saved. Check account connections before retrying.", 3) from None
        if not isinstance(access, str) or not access:
            raise Failure("login_uncertain", "A grant may have been created. Check account connections before retrying.", 3) from None
        try:
            request(issuer + "/api/v1/logout", form={}, bearer=access)
        except Failure as cleanup:
            raise cleanup.reframe("cleanup_unconfirmed", "The existing connection was retained, but revocation of the new grant could not be confirmed. Check account connections.") from None
        raise exc
    try:
        request(issuer + "/api/v1/logout", form={}, bearer=original["access_token"])
    except Failure as cleanup:
        raise cleanup.reframe("cleanup_unconfirmed", "The new connection was saved, but revocation of the old grant could not be confirmed. Check account connections.") from None
    return {"connected": True, "account": new_account}

def run(args):
    issuer = issuer_url(args.issuer or DEFAULT_ISSUER)
    if issuer != DEFAULT_ISSUER and not args.client_id:
        raise Failure("client_id_required", "An alternate service requires its registered public client ID via --client-id.", 2)
    args.client_id = args.client_id or DEFAULT_CLIENT_ID
    recovery = recovery_instructions(args)
    if args.command == "auth" and args.action == "login" and not 1 <= args.callback_timeout <= 600:
        raise Failure("invalid_timeout", "Callback timeout must be between 1 and 600 seconds.", 2)
    if args.command in ("leads", "notifications") and args.action == "delete" and not args.yes:
        if not sys.stdin.isatty():
            raise Failure("confirmation_required", "Deletion requires confirmation. Use --yes for noninteractive deletion.", 2)
        prompt = (f"Permanently delete notification {args.id} and its collected leads? [y/N] "
                  if args.command == "notifications" else f"Permanently delete lead {args.id}? [y/N] ")
        if args.command == "notifications" and args.json:
            try:
                with open(os.ttyname(sys.stdin.fileno()), "w") as terminal:
                    print(prompt, end="", file=terminal, flush=True)
            except (AttributeError, OSError, ValueError):
                raise Failure("confirmation_required", "Cannot display confirmation. Use --yes for noninteractive deletion.", 2) from None
        else:
            print(prompt, end="", file=sys.stderr, flush=True)
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
            if token and not args.add:
                message = "Connection already exists. "
                if token.get("refresh_pending"):
                    message += "The existing refresh outcome is unknown. "
                else:
                    try:
                        granted_scopes(token["access_token"])
                        if type(token.get("account_id")) is not int and time.time() >= token["expires_at"]:
                            token_subject(token["access_token"])
                    except Failure:
                        message += "The existing connection cannot be verified. "
                    else:
                        message += "Use auth login --add to add permissions. To replace the connection, follow these steps. "
                raise Failure("already_connected", message + recovery)
            if args.add:
                if not token:
                    raise Failure("not_connected", "No saved connection. Run auth login first.")
                return upgrade(args, issuer, store, token, recovery)
            token = authorize(issuer, args.client_id, args.browser_driver, args.callback_timeout, args.delete_leads, args.events, args.billing, args.delete_notifications, email_change=args.email_change)
            try:
                validated = store.validate(token)
                account = request(issuer + "/api/v1/account", bearer=validated["access_token"])
                validated["account_id"] = account_id(account)
                store.write(validated)
            except (Failure, OSError, ValueError, TypeError, KeyringError) as exc:
                access = token.get("access_token") if isinstance(token, dict) else None
                if isinstance(access, str) and access:
                    try:
                        request(issuer + "/api/v1/logout", form={}, bearer=access)
                    except Failure as cleanup:
                        raise cleanup.reframe("cleanup_unconfirmed", "Login failed and grant revocation could not be confirmed. Revoke the connection in your account before retrying.") from None
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
            raise Failure("refresh_uncertain", "A refresh may have been consumed. " + recovery, 3)
        if time.time() >= token["expires_at"]:
            token, _ = refresh_connection(issuer, args.client_id, store, token, recovery)
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
                    token, _ = refresh_connection(issuer, args.client_id, store, token, recovery)
                    if kwargs.get("method"):
                        if args.command == "account" and args.action == "update":
                            raise exc.reframe("operation_not_retried", "The connection was refreshed. The email request was not retried. Check the recipient mailbox and account settings before requesting another code.") from None
                        if args.command == "notifications" and args.action == "delete":
                            raise exc.reframe("operation_not_retried", "The connection was refreshed. The deletion was not retried. Check the notification before deciding whether to retry.") from None
                        raise exc.reframe("operation_not_retried", "The connection was refreshed. The write was not retried. For event submissions, retry the exact command with the same IDs and payload. For create, reuse the same key and input.") from None
                    return request(url, bearer=token["access_token"], **kwargs)
                if (exc.code in ("network_error", "unexpected_response") or getattr(exc, "http_status", 0) >= 500) and args.command in ("leads", "notifications") and args.action == "delete":
                    resource = "lead" if args.command == "leads" else "notification"
                    raise exc.reframe("delete_uncertain", f"The deletion outcome is unknown. Check the {resource} before deciding whether to retry.") from None
                if (exc.code == "network_error" or getattr(exc, "http_status", 0) >= 500) and args.command == "notifications" and args.action == "create":
                    raise exc.reframe("create_uncertain", "The create outcome is unknown. Retry the same input with the same idempotency key.") from None
                if (exc.code == "network_error" or getattr(exc, "http_status", 0) >= 500) and args.command == "events":
                    raise exc.reframe("event_uncertain", "The event outcome is unknown. Retry the exact command with the same IDs and payload.") from None
                raise
        if (args.command, args.action) in BROWSER_ACTIONS:
            account = authenticated(issuer + "/api/v1/account")
            connected_id = account_id(account)
            if args.command == "notifications":
                authenticated(issuer + "/api/v1/notifications/" + str(args.id))
            return browser_handoff(args, issuer, connected_id)
        if args.command == "account" and args.action == "update":
            try:
                result = authenticated(issuer + "/api/v1/account/email-change", method="POST",
                                       payload={"email": args.email}, expected_status=202)
                if result != {"status": "confirmation_required"}:
                    raise Failure("unexpected_response", "Server returned an unexpected response.", 3)
            except Failure as exc:
                if exc.code in ("network_error", "unexpected_response") or exc.http_status >= 500:
                    raise exc.reframe("email_change_uncertain", "The request outcome is unknown. Check the recipient mailbox and account settings before requesting another code. The account email has not been confirmed by this command.") from None
                raise
            return {"status": "confirmation_required", "email_changed": False,
                    "confirmation_url": issuer + "/billing",
                    "next_step": "Run account confirm-email to open account settings. Check the browser account, then enter the recipient code and current password in the Confirm email change form. Run account show afterwards to read the authoritative identity."}
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
        if args.action == "delete":
            authenticated(path, method="DELETE", expected_status=204)
            return {"deleted": True, "id": args.id}
        if args.action == "edit":
            payload = notification_payload(args)
            payload["revision"] = args.revision
            return authenticated(path, method="PUT", payload=payload)
        return authenticated(path + "/" + args.action, method="PUT", payload={})

BROWSER_ACTIONS = {
    ("account", "settings"): ("/billing", "Review account settings and connected clients."),
    ("account", "security"): ("/billing", "Use the password, connection revocation, Google linking or account closure form. Closure requires current password confirmation and cannot be undone by the CLI."),
    ("account", "onboarding"): ("/onboarding", "Review onboarding and lifetime access options."),
    ("account", "confirm-email"): ("/billing", "Enter the recipient code and current password in the Confirm email change form. Invalid, expired, replaced or used codes do not change identity. Run account show afterwards."),
    ("notifications", "preview"): ("/notifications", "Find the requested notification, using page navigation if needed, then select Preview. This command does not open its modal or confirm rendering."),
    ("installation", "open"): ("/install", "Review installation instructions and tracking status."),
    ("billing", "checkout"): ("/billing", "Review the single $99 lifetime offer and confirm checkout in the browser. Opening this page does not purchase access. Return to billing status to check server access."),
    ("billing", "open"): ("/billing", "Review billing history, payment reconciliation or purchase claims. Complete any required confirmations in the browser."),
}


def browser_handoff(args, issuer, connected_id):
    path, instruction = BROWSER_ACTIONS[(args.command, args.action)]
    url = issuer + path
    try:
        if args.browser_driver:
            subprocess.Popen([args.browser_driver, url], close_fds=True)
        elif not webbrowser.open(url):
            raise OSError()
    except OSError:
        raise Failure("browser_failed", "Could not open a browser. Set a default browser and retry. No browser action was confirmed.") from None
    result = {"browser_launch_requested": True, "url": url, "completed": False,
              "account_binding_verified": False, "connected_account_id": connected_id,
              "next_step": "The browser has its own session. Compare its signed-in identity with account show before submitting a form. " + instruction}
    if args.command == "notifications":
        result["notification_id"] = args.id
    return result


def browser_option(parser):
    parser.add_argument("--browser-driver", help="executable that receives the fixed browser URL")


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

def build_parser():
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
    login.add_argument("--add", action="store_true", help="add selected permissions to the existing connection")
    login.add_argument("--delete-leads", action="store_true", help="request permission to permanently delete leads during browser consent")
    login.add_argument("--delete-notifications", action="store_true", help="request permission to permanently delete notifications during browser consent")
    login.add_argument("--events", action="store_true", help="request permission to submit events")
    login.add_argument("--email-change", action="store_true", help="request email change permission with current-password proof in browser consent")
    login.add_argument("--billing", action="store_true", help="request permission to read billing")
    login.add_argument("--browser-driver", help="executable that receives the authorization URL")
    login.add_argument("--callback-timeout", type=int, default=120)
    auth.add_parser("status")
    logout = auth.add_parser("logout")
    logout.add_argument("--local", action="store_true", help="forget locally without revoking the server grant")
    account = sub.add_parser("account").add_subparsers(dest="action", required=True)
    account.add_parser("show")
    update = account.add_parser("update", description="Request an email change. HTTP 202 means recipient confirmation is required, not that the email changed. Add permission with auth login --add --email-change. Password and recipient code stay in the browser.")
    update.add_argument("--email", required=True, help="new recipient email address")
    for action in ("settings", "security", "onboarding", "confirm-email"):
        browser_option(account.add_parser(action, description="Open the corresponding browser form. Verify the browser account before acting. The CLI cannot confirm browser identity or completion."))
    stats = sub.add_parser("stats", help="show dashboard statistics").add_subparsers(dest="action", required=True)
    stats.add_parser("show", description="Show lifetime customer dashboard statistics. Capture counts use active, non-archived owned notifications. Hour and day counts cover the preceding hour and 24 hours in inclusive rolling UTC windows ending at as_of. Tracks include all account history. Results may be cached for one second.")
    installation = sub.add_parser("installation").add_subparsers(dest="action", required=True)
    installation.add_parser("show")
    browser_option(installation.add_parser("open", help="open browser installation instructions"))
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
    for action in ("checkout", "open"):
        browser_option(billing.add_parser(action, description="Open billing in the browser. Check the browser account, then complete any checkout or payment confirmation there. Opening a page does not confirm payment."))
    notifications = sub.add_parser("notifications", help="manage notifications").add_subparsers(dest="action", required=True)
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
    preview = notifications.add_parser("preview", description="Check the owned notification, then open the browser notification list. Find the notification and select Preview. Browser account and rendering are not verified.")
    preview.add_argument("id", type=positive)
    browser_option(preview)
    delete = notifications.add_parser("delete", help="permanently delete a notification and its collected leads", description="Permanently delete one notification and its collected leads. This cannot be undone. Request permission with auth login --delete-notifications or auth login --add --delete-notifications. If the outcome is unknown, check the notification before retrying.")
    delete.add_argument("id", type=positive)
    delete.add_argument("--yes", action="store_true", help="confirm permanent deletion without prompting")
    completion = sub.add_parser("completion", help="generate local Bash or Zsh completion")
    completion.add_argument("shell", choices=("bash", "zsh"), help="shell to generate; see README for installation")
    return p


def main():
    from .completion import bash_words, candidates, shell_script

    p = build_parser()
    if sys.argv[1:2] in (["--_complete"], ["--_complete-bash"]):
        try:
            index = int(sys.argv[2])
            if sys.argv[1] == "--_complete-bash":
                if len(sys.argv) != 4:
                    return 2
                words = bash_words(sys.argv[3], index)
                index = len(words) - 1
            else:
                words = sys.argv[3:]
            if not 0 < index < len(words) or len(words) > 256 or sum(map(len, words)) > 32768:
                return 2
        except (IndexError, ValueError):
            return 2
        print("\n".join(candidates(p, words[1:index], words[index])), end="")
        return 0
    args = p.parse_args()
    if args.command == "completion":
        print(shell_script(args.shell), end="")
        return 0
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
            print(json.dumps(exc.output(), sort_keys=True), file=sys.stderr)
        else:
            print(f"Error: {exc.message}", file=sys.stderr)
            if exc.correlation_id:
                print(f"Request ID: {exc.correlation_id}", file=sys.stderr)
        return exc.exit_code
    return 0
