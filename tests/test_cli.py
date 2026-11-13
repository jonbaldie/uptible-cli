import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def nested_claim_token(access):
    header, encoded, signature = access.split('.')
    claims = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
    claims = claims[:-1] + b',"unused":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}'
    return header + '.' + base64.urlsafe_b64encode(claims).decode().rstrip('=') + '.' + signature


def nested_claim_readable():
    try:
        json.loads('{"unused":' + '[' * 1500 + '0' + ']' * 1500 + '}')
    except RecursionError:
        return False
    return True


class Server(BaseHTTPRequestHandler):
    calls = []
    authorization = None
    reject_refresh = False
    account_error = None
    refreshes = 0
    reject_logout = False
    drop_refresh_response = False
    login_response = None
    jwt_mode = False
    issued_scopes = None
    refresh_scopes = None
    refresh_account = None
    account_number = 42
    grant_number = 0
    current_refresh = "first"
    operations = []
    reject_next = False
    drop_create = False
    api_error = None
    notification_records = None
    delete_success_status = 204
    response_fault = None
    fault_requests = []
    token_fault = None
    issued_access = None
    logout_bearers = []
    interrupt_started = None
    interrupt_release = None
    account_payload = None
    event_receipt = {'receipt': 'synthetic-receipt', 'status': 'processed'}
    statistics = {'hour_captures_count': 1, 'captures_count': 2, 'all_captures_count': 3, 'tracks_count': 4, 'as_of': '2026-01-02T00:00:00Z', 'hour_start': '2026-01-01T23:00:00Z', 'day_start': '2026-01-01T00:00:00Z'}
    def log_message(self, *args):
        pass
    def respond(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(raw)
    def damaged_response(self, raw=b''):
        if not self.response_fault or self.response_fault[:2] != (self.command, self.path):
            return False
        echoed = self.headers.get('Authorization', '').encode() + b' ' + raw
        self.fault_requests.append((self.command, self.path, echoed))
        if self.response_fault[2] == 'bad-status':
            self.connection.sendall(b'INVALID synthetic-untrusted-marker ' + echoed + b'\r\n\r\n')
        elif self.response_fault[2] in ('nested-200', 'nested-503'):
            body = b'[' * 2000 + b']' * 2000
            status = 200 if self.response_fault[2] == 'nested-200' else 503
            self.send_response(status, 'synthetic-untrusted-marker ' + echoed.decode())
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        elif self.response_fault[2] == 'stalled-503':
            self.send_response(503, 'synthetic-untrusted-marker ' + echoed.decode())
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', '100')
            self.send_header('Retry-After', '3')
            self.end_headers()
            self.wfile.write(b'{"error":')
            self.wfile.flush()
            self.interrupt_started.set()
            self.interrupt_release.wait(10)
        elif self.response_fault[2] == 'retry-503':
            self.send_response(503, 'synthetic-untrusted-marker ' + echoed.decode())
            self.send_header('Content-Length', '0')
            self.send_header('Retry-After', '2')
            self.end_headers()
            self.wfile.flush()
            self.interrupt_started.set()
        elif self.response_fault[2] in ('invalid-422', 'malformed-422', 'empty-422'):
            if self.response_fault[2] == 'invalid-422':
                body = b'\xff synthetic-untrusted-marker ' + echoed
            elif self.response_fault[2] == 'malformed-422':
                body = b'{"error":"synthetic-untrusted-marker ' + echoed + b'"'
            else:
                body = b''
            self.send_response(422)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        else:
            partial = b'{"error":"synthetic-untrusted-marker ' + echoed + b'"'
            kind = self.response_fault[2]
            status = int(kind.removeprefix('truncated-')) if kind.startswith('truncated-') else 503
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(partial) + 100))
            self.end_headers()
            self.wfile.write(partial)
            self.wfile.flush()
        self.close_connection = True
        return True
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.damaged_response(raw):
            return
        raw = raw.decode()
        if self.path.startswith('/api/v1/notifications/') and self.path.endswith(('/capture', '/track')):
            self.operations.append(('POST', self.path, json.loads(raw)))
            if self.api_error:
                self.respond(self.api_error[1], self.api_error[0])
            elif self.drop_create:
                self.connection.shutdown(2)
                self.connection.close()
            elif self.event_receipt == 'malformed':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"receipt":')
            else:
                self.respond(self.event_receipt)
            return
        if self.path == '/api/v1/notifications':
            if self.api_error:
                status, body = self.api_error
                self.respond(body, status)
                return
            if self.reject_next:
                type(self).reject_next = False
                self.respond({'error': 'unauthorized'}, 401)
                return
            self.operations.append(('POST', self.path, self.headers.get('Idempotency-Key'), json.loads(raw)))
            if self.drop_create:
                self.connection.shutdown(2)
                self.connection.close()
                return
            self.respond({'id': 7, 'revision': 1}, 201)
            return
        form = urllib.parse.parse_qs(raw)
        self.calls.append((self.path, form))
        if self.path == '/oauth/token':
            if form.get('grant_type') == ['authorization_code']:
                if self.login_response == 'drop':
                    self.connection.shutdown(2)
                    self.connection.close()
                    return
                if self.login_response == 'malformed':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{\"access_token\":\"synthetic-secret-marker\"')
                    return
                if self.login_response == 'unusable':
                    self.respond({'refresh_token': 'synthetic-secret-marker'})
                    return
                if self.login_response == 'reject':
                    self.respond({'error': 'invalid_grant'}, 400)
                    return
                verifier = form['code_verifier'][0]
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                if not self.authorization or challenge != self.authorization['code_challenge'][0] or form['redirect_uri'] != self.authorization['redirect_uri']:
                    self.respond({'error': 'invalid_grant'}, 400)
                    return
            if form.get('grant_type') == ['refresh_token'] and self.reject_refresh:
                self.respond({'error': 'invalid_grant'}, 400)
                return
            if form.get('grant_type') == ['refresh_token']:
                type(self).refreshes += 1
                if form.get('refresh_token') != [self.current_refresh]:
                    self.respond({'error': 'invalid_grant'}, 400)
                    return
                time.sleep(0.3)
                type(self).current_refresh = 'rotated'
                if self.drop_refresh_response:
                    self.connection.shutdown(2)
                    self.connection.close()
                    return
            access = 'access'
            if not self.jwt_mode and form.get('grant_type') == ['refresh_token'] and self.refresh_account is not None:
                access = 'opaque-account-' + str(self.refresh_account)
            if self.jwt_mode:
                if form.get('grant_type') == ['authorization_code']:
                    type(self).grant_number += 1
                refreshing = form.get('grant_type') == ['refresh_token']
                scopes = self.refresh_scopes if refreshing and self.refresh_scopes is not None else self.issued_scopes
                scopes = scopes if scopes is not None else self.authorization['scope'][0].split()
                account = self.refresh_account if refreshing and self.refresh_account is not None else self.account_number
                claims = {'scopes': scopes, 'account': account, 'sub': str(account), 'grant': self.grant_number}
                access = 'header.' + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=') + '.signature'
            if self.token_fault and form.get('grant_type') == [self.token_fault[0]]:
                if self.token_fault[1] == 'deep':
                    access = nested_claim_token(access)
                elif self.token_fault[1] == 'invalid':
                    access = 'header.' + base64.urlsafe_b64encode(b'{"scopes":').decode().rstrip('=') + '.signature'
            type(self).issued_access = access
            self.respond({'access_token': access, 'refresh_token': self.current_refresh, 'expires_in': 60})
        elif self.path == '/api/v1/logout':
            self.logout_bearers.append(self.headers.get('Authorization'))
            if self.reject_logout:
                self.respond({'error': 'synthetic-secret-marker'}, 503)
            else:
                self.send_response(204)
                self.end_headers()
        else:
            self.respond({'error': 'unknown'}, 404)
    def do_PUT(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.damaged_response(raw):
            return
        self.operations.append(('PUT', self.path, json.loads(raw)))
        if self.path == '/api/v1/notifications/7' and json.loads(raw).get('revision') != 2:
            self.respond({'error': 'conflict'}, 409)
        else:
            self.respond({'id': 7, 'revision': 3})
    def claims(self):
        access = self.headers['Authorization'].removeprefix('Bearer ')
        part = access.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    def do_DELETE(self):
        self.operations.append(('DELETE', self.path))
        if self.notification_records is not None and self.path.startswith('/api/v1/notifications/'):
            if self.reject_next:
                type(self).reject_next = False
                self.respond({}, 401)
                return
            if self.api_error:
                self.respond(self.api_error[1], self.api_error[0])
                return
            claims = self.claims()
            if 'notifications:delete' not in claims['scopes']:
                self.respond({}, 403)
                return
            identifier = int(self.path.rsplit('/', 1)[-1])
            record = self.notification_records.get(identifier)
            if record is None or record['owner'] != claims['account']:
                self.respond({}, 404)
                return
            if self.delete_success_status != 204:
                self.respond({'status': 'accepted'}, self.delete_success_status)
                return
            del self.notification_records[identifier]
            if self.damaged_response():
                return
            if self.drop_create:
                self.connection.shutdown(2)
                self.connection.close()
            else:
                self.send_response(204)
                self.end_headers()
            return
        if self.damaged_response():
            return
        if self.drop_create:
            self.connection.shutdown(2)
            self.connection.close()
        elif self.api_error:
            self.respond(self.api_error[1], self.api_error[0])
        else:
            self.send_response(204)
            self.end_headers()
    def do_GET(self):
        if self.damaged_response():
            return
        if self.reject_next and self.path.startswith('/api/'):
            type(self).reject_next = False
            self.respond({'error': 'unauthorized'}, 401)
            return
        if self.path.startswith('/api/v1/billing'):
            self.operations.append(('GET', self.path))
            if self.api_error:
                self.respond(self.api_error[1], self.api_error[0])
            else:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if query.get('cursor') == ['claim-next'] or query.get('claim_cursor') == ['order-next']:
                    self.respond({'errors': {'cursor': ['invalid']}}, 422)
                else:
                    self.respond({'live_access': True, 'purchase_eligible': False, 'orders': [], 'claim_references': [], 'next_cursor': None if 'cursor' in query else 'order-next', 'next_claim_cursor': None if 'claim_cursor' in query else 'claim-next'})
            return
        if self.path == '/api/v1/statistics':
            self.operations.append(('GET', self.path))
            if self.api_error:
                self.respond(self.api_error[1], self.api_error[0])
            else:
                self.respond(self.statistics)
            return
        if self.notification_records is not None and self.path.startswith('/api/v1/notifications/') and self.path.rsplit('/', 1)[-1].isdigit():
            self.operations.append(('GET', self.path))
            record = self.notification_records.get(int(self.path.rsplit('/', 1)[-1]))
            if record is None or record['owner'] != self.claims()['account']:
                self.respond({}, 404)
            else:
                self.respond(record)
            return
        if self.path.startswith(('/api/v1/notifications', '/api/v1/leads')) or self.path == '/api/v1/installation':
            self.operations.append(('GET', self.path))
            self.respond({'path': self.path})
            return
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == '/oauth/authorize':
            type(self).authorization = urllib.parse.parse_qs(parsed.query)
            self.respond({'ok': True})
        elif self.path == '/api/v1/account' and self.account_error is not None:
            self.respond({'error': self.account_error}, 503)
        elif self.path == '/api/v1/account' and self.account_payload is not None:
            self.respond(self.account_payload)
        elif self.path == '/api/v1/account' and self.headers.get('Authorization', '').startswith('Bearer '):
            access = self.headers['Authorization'][7:]
            if self.jwt_mode:
                part = access.split('.')[1]
                identity = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))['account']
            elif access == 'access':
                identity = 42
            elif access.startswith('opaque-account-') and access.removeprefix('opaque-account-').isdigit():
                identity = int(access.removeprefix('opaque-account-'))
            else:
                self.respond({'error': 'unauthorized'}, 401)
                return
            self.respond({'id': identity, 'name': 'Example', 'email': 'person@example.test'})
        else:
            self.respond({'error': 'unauthorized'}, 401)


class CLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
    def setUp(self):
        Server.login_response = None
        Server.jwt_mode = False
        Server.issued_scopes = None
        Server.refresh_scopes = None
        Server.refresh_account = None
        Server.account_number = 42
        Server.grant_number = 0
        Server.authorization = None
        Server.reject_refresh = False
        Server.account_error = None
        Server.current_refresh = "first"
        Server.refreshes = 0
        Server.reject_logout = False
        Server.drop_refresh_response = False
        Server.calls = []
        Server.operations = []
        Server.reject_next = False
        Server.drop_create = False
        Server.api_error = None
        Server.notification_records = None
        Server.delete_success_status = 204
        Server.response_fault = None
        Server.fault_requests = []
        Server.token_fault = None
        Server.issued_access = None
        Server.logout_bearers = []
        Server.account_payload = None
        Server.event_receipt = {'receipt': 'synthetic-receipt', 'status': 'processed'}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.creds = self.path / 'credentials'
        self.driver = self.path / 'browser'
        self.driver.write_text('''#!/usr/bin/env python3
import os, sys, urllib.parse, urllib.request
q = urllib.parse.parse_qs(urllib.parse.urlsplit(sys.argv[1]).query)
urllib.request.urlopen(sys.argv[1], timeout=5).read()
state = 'wrong' if os.getenv('WRONG_STATE') else q['state'][0]
if os.getenv('NO_CALLBACK'):
    sys.exit(0)
params = {'state': state, 'error': 'access_denied'} if os.getenv('DENY') else {'state': state, 'code': 'synthetic'}
url = q['redirect_uri'][0] + '?' + urllib.parse.urlencode(params)
urllib.request.urlopen(url, timeout=5).read()
''')
        self.driver.chmod(0o700)
        self.base = [sys.executable, '-m', 'uptible_cli', '--json', '--issuer', 'http://127.0.0.1:' + str(self.server.server_port), '--client-id', 'test', '--credential-file', str(self.creds)]
    def run_cli(self, *args, env=None):
        result = subprocess.run(self.base + list(args), capture_output=True, text=True, env=env, timeout=10)
        return result, json.loads(result.stdout or result.stderr)
    def interrupt_cli(self, base, *args):
        Server.interrupt_started = threading.Event()
        Server.interrupt_release = threading.Event()
        process = subprocess.Popen(base + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(Server.interrupt_started.wait(5), 'The server did not start its response')
            time.sleep(0.3)
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=8)
            return process.returncode, stdout, stderr
        finally:
            Server.interrupt_release.set()
            if process.poll() is None:
                process.kill()
                process.wait()
    def run_tty_cli(self, base, answer, *args):
        import pty
        import select
        master, slave = pty.openpty()
        process = subprocess.Popen(base + list(args), stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        os.close(slave)
        try:
            terminal = b''
            deadline = time.monotonic() + 10
            while b'[y/N]' not in terminal and process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    data = os.read(master, 8192)
                    if not data:
                        break
                    terminal += data
            if process.poll() is None:
                os.write(master, answer)
            stdout, stderr = process.communicate(timeout=10)
            return process.returncode, stdout, stderr, terminal.decode()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
    def test_notification_delete_permission_is_explicit_on_initial_login(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        default = set(Server.authorization['scope'][0].split())
        self.assertNotIn('notifications:delete', default)
        self.assertEqual(self.run_cli('auth', 'logout', '--local')[0].returncode, 0)
        result = subprocess.run(self.base + ['auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(Server.authorization['scope'][0].split()), default | {'notifications:delete'})

    def test_notification_delete_upgrade_retains_exact_scopes_and_account(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = self.creds.read_text()
        old_scopes = set(Server.authorization['scope'][0].split())
        requested = old_scopes | {'notifications:delete'}
        command = ['auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver)]
        denied = subprocess.run(self.base + command, capture_output=True, text=True, timeout=10, env=dict(os.environ, DENY='1'))
        self.assertEqual(denied.returncode, 1, denied.stderr)
        self.assertEqual(json.loads(denied.stderr)['error']['code'], 'authorization_denied')
        self.assertEqual(self.creds.read_text(), original)
        self.assertEqual(set(Server.authorization['scope'][0].split()), requested)
        Server.account_number = 43
        result, body = self.run_cli(*command)
        self.assertEqual(body['error']['code'], 'account_mismatch')
        self.assertEqual(self.creds.read_text(), original)
        Server.account_number = 42
        for issued, error in ((old_scopes, 'permissions_missing'), (requested | {'leads:delete'}, 'permissions_unexpected')):
            Server.issued_scopes = sorted(issued)
            result, body = self.run_cli(*command)
            self.assertEqual(result.returncode, 3, body)
            self.assertEqual(body['error']['code'], error)
            self.assertEqual(self.creds.read_text(), original)
            self.assertEqual(self.run_cli('auth', 'status')[1]['account']['id'], 42)
        Server.issued_scopes = None
        result, body = self.run_cli(*command)
        self.assertEqual(result.returncode, 0, body)
        self.assertEqual(set(Server.authorization['scope'][0].split()), requested)
        self.assertNotEqual(self.creds.read_text(), original)
        self.assertEqual(self.run_cli('auth', 'status')[1]['account']['id'], 42)

    def test_notification_delete_denied_upgrade_after_refresh_retains_grant(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--browser-driver', str(self.driver))[0].returncode, 0)
        old_scopes = set(Server.authorization['scope'][0].split())
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        result, body = self.run_cli('auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver), env=dict(os.environ, DENY='1'))
        self.assertEqual((result.returncode, body['error']['code']), (1, 'authorization_denied'))
        self.assertEqual(Server.refreshes, 1)
        self.assertEqual(self.run_cli('auth', 'status')[1]['account']['id'], 42)
        rotated = json.loads(self.creds.read_text())
        self.assertEqual(rotated['refresh_token'], 'rotated')
        part = rotated['access_token'].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        self.assertEqual(set(claims['scopes']), old_scopes)

    def test_notification_delete_upgrade_rejects_changed_refresh_scopes(self):
        Server.jwt_mode = True
        for change in ('narrow', 'expand'):
            Server.refresh_scopes = None
            Server.current_refresh = 'first'
            self.assertEqual(self.run_cli('auth', 'login', '--events', '--browser-driver', str(self.driver))[0].returncode, 0)
            old_scopes = set(Server.authorization['scope'][0].split())
            saved = json.loads(self.creds.read_text())
            saved['expires_at'] = 0
            self.creds.write_text(json.dumps(saved))
            Server.refresh_scopes = sorted(old_scopes - {'events:write'} if change == 'narrow' else old_scopes | {'billing:read'})
            result, body = self.run_cli('auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver))
            self.assertEqual(result.returncode, 3, body)
            self.assertEqual(body['error']['code'], 'refresh_permissions_changed')
            self.assertIn('reconnect', body['error']['message'])
            self.assertEqual(set(Server.authorization['scope'][0].split()), old_scopes)
            pending = json.loads(self.creds.read_text())
            self.assertEqual(pending['access_token'], saved['access_token'])
            self.assertTrue(pending['refresh_pending'])
            self.assertEqual(self.run_cli('auth', 'logout', '--local')[0].returncode, 0)

    def test_notification_delete_upgrade_rejects_account_change_during_refresh(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        old_scopes = set(Server.authorization['scope'][0].split())
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.refresh_account = 43
        result, body = self.run_cli('auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 3, body)
        self.assertEqual(body['error']['code'], 'refresh_account_changed')
        self.assertIn('reconnect', body['error']['message'])
        self.assertEqual(set(Server.authorization['scope'][0].split()), old_scopes)
        pending = json.loads(self.creds.read_text())
        self.assertEqual(pending['access_token'], saved['access_token'])
        self.assertTrue(pending['refresh_pending'])

    def test_notification_delete_upgrade_requires_known_expired_account(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved.pop('account_id', None)
        part = saved['access_token'].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        del claims['sub']
        encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        saved['access_token'] = 'header.' + encoded + '.signature'
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        before = self.creds.read_text()
        result, body = self.run_cli('auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver))
        self.assertEqual((result.returncode, body['error']['code']), (3, 'account_unknown'))
        self.assertEqual(Server.refreshes, 0)
        self.assertEqual(self.creds.read_text(), before)

    def test_permission_upgrade_retains_scope_and_rejects_other_account(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = self.creds.read_text()
        denied = self.run_cli('auth', 'login', '--add', '--billing', '--browser-driver', str(self.driver), env=dict(os.environ, DENY='1'))
        self.assertEqual(denied[1]['error']['code'], 'authorization_denied')
        self.assertEqual(self.creds.read_text(), original)
        Server.account_number = 43
        wrong = self.run_cli('auth', 'login', '--add', '--billing', '--browser-driver', str(self.driver))
        self.assertEqual(wrong[1]['error']['code'], 'account_mismatch')
        self.assertEqual(self.creds.read_text(), original)
        Server.account_number = 42
        result, body = self.run_cli('auth', 'login', '--add', '--billing', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 0, body)
        self.assertTrue({'events:write', 'billing:read'} <= set(Server.authorization['scope'][0].split()))
        self.assertNotEqual(self.creds.read_text(), original)
        self.assertEqual(self.run_cli('auth', 'status')[1]['account']['id'], 42)
        self.assertEqual(sum(path == '/api/v1/logout' for path, _ in Server.calls), 2)

    def test_upgrade_reports_uncertain_new_grant(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = self.creds.read_text()
        Server.login_response = 'drop'
        result, body = self.run_cli('auth', 'login', '--add', '--events', '--browser-driver', str(self.driver))
        self.assertEqual(body['error']['code'], 'login_uncertain')
        self.assertEqual(self.creds.read_text(), original)

    def test_upgrade_timeout_and_unconfirmed_cleanup(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = self.creds.read_text()
        result, body = self.run_cli('auth', 'login', '--add', '--events', '--browser-driver', str(self.driver), '--callback-timeout', '1', env=dict(os.environ, NO_CALLBACK='1'))
        self.assertEqual(body['error']['code'], 'callback_timeout')
        self.assertEqual(self.creds.read_text(), original)
        Server.account_number = 43
        Server.reject_logout = True
        result, body = self.run_cli('auth', 'login', '--add', '--events', '--browser-driver', str(self.driver))
        self.assertEqual(body['error']['code'], 'cleanup_unconfirmed')
        self.assertEqual(self.creds.read_text(), original)

    def test_upgrade_save_failure_keeps_original(self):
        import argparse
        from unittest.mock import patch
        import uptible_cli
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = self.creds.read_text()
        args = argparse.Namespace(issuer='http://127.0.0.1:' + str(self.server.server_port), client_id='test', profile='default', credential_file=str(self.creds), command='auth', action='login', callback_timeout=5, add=True, delete_leads=False, delete_notifications=False, events=True, billing=False, browser_driver=str(self.driver))
        with patch.object(uptible_cli.Store, 'write', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                uptible_cli.run(args)
        self.assertEqual(self.creds.read_text(), original)
        self.assertTrue(any(path == '/api/v1/logout' for path, _ in Server.calls))
        self.assertEqual(self.run_cli('auth', 'status')[1]['account']['id'], 42)

    def test_upgrade_refreshes_expired_connection_and_blocks_uncertain_refresh(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        result, body = self.run_cli('auth', 'login', '--add', '--billing', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 0, body)
        self.assertEqual(Server.refreshes, 1)
        self.assertTrue({'events:write', 'billing:read'} <= set(Server.authorization['scope'][0].split()))
        saved = json.loads(self.creds.read_text())
        saved['refresh_pending'] = True
        self.creds.write_text(json.dumps(saved))
        before = self.creds.read_text()
        result, body = self.run_cli('auth', 'login', '--add', '--delete-leads', '--browser-driver', str(self.driver))
        self.assertEqual(body['error']['code'], 'refresh_uncertain')
        self.assertEqual(self.creds.read_text(), before)

    def test_upgrade_uncertain_storage_does_not_revoke_saved_grant(self):
        import argparse
        from unittest.mock import patch
        import uptible_cli
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = self.creds.read_text()
        args = argparse.Namespace(issuer='http://127.0.0.1:' + str(self.server.server_port), client_id='test', profile='default', credential_file=str(self.creds), command='auth', action='login', callback_timeout=5, add=True, delete_leads=False, delete_notifications=False, events=True, billing=False, browser_driver=str(self.driver))
        write = uptible_cli.Store.write
        def save_then_fail(store, value):
            write(store, value)
            raise OSError('unknown storage outcome')
        with patch.object(uptible_cli.Store, 'write', save_then_fail):
            with self.assertRaises(uptible_cli.Failure) as failure:
                uptible_cli.run(args)
        self.assertEqual(failure.exception.code, 'storage_uncertain')
        self.assertNotEqual(self.creds.read_text(), original)
        self.assertFalse(any(path == '/api/v1/logout' for path, _ in Server.calls))
        self.assertEqual(self.run_cli('auth', 'status')[1]['account']['id'], 42)

    def test_events_and_billing(self):
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--billing', '--browser-driver', str(self.driver))[0].returncode, 0)
        self.assertTrue({'events:write', 'billing:read'} <= set(Server.authorization['scope'][0].split()))
        capture = ('events', 'capture', '7', '--session-id', 'session', '--event-id', 'event', '--email', 'person@example.test', '--name', 'Person')
        result, body = self.run_cli(*capture)
        self.assertEqual((result.returncode, body), (0, Server.event_receipt))
        self.assertEqual(Server.operations[-1], ('POST', '/api/v1/notifications/7/capture', {'session_id': 'session', 'event_id': 'event', 'email': 'person@example.test', 'name': 'Person'}))
        self.assertEqual(self.run_cli('events', 'track', '7', '--session-id', 's', '--event-id', 'e')[1], Server.event_receipt)
        Server.drop_create = True
        self.assertEqual(self.run_cli(*capture)[1]['error']['code'], 'event_uncertain')
        prior = Server.operations[-1]
        Server.drop_create = False
        self.assertEqual(self.run_cli(*capture)[0].returncode, 0)
        self.assertEqual(Server.operations[-1], prior)
        Server.event_receipt = {'receipt': 'bad', 'status': 'accepted'}
        self.assertEqual(self.run_cli(*capture)[1]['error']['code'], 'event_uncertain')
        Server.event_receipt = 'malformed'
        result, body = self.run_cli(*capture)
        self.assertEqual(body['error']['code'], 'event_uncertain')
        self.assertIn('same IDs and payload', body['error']['message'])
        result, body = self.run_cli('billing', 'status', '--cursor', 'a+/=', '--claim-cursor', 'b+/=')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(body['live_access'])
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(Server.operations[-1][1]).query)
        self.assertEqual(query, {'cursor': ['a+/='], 'claim_cursor': ['b+/=']})
        first = self.run_cli('billing', 'status')[1]
        self.assertEqual((first['next_cursor'], first['next_claim_cursor']), ('order-next', 'claim-next'))
        last = self.run_cli('billing', 'status', '--cursor', first['next_cursor'], '--claim-cursor', first['next_claim_cursor'])[1]
        self.assertEqual((last['next_cursor'], last['next_claim_cursor']), (None, None))
        self.assertIn('422', self.run_cli('billing', 'status', '--cursor', first['next_claim_cursor'])[1]['error']['message'])
        self.assertIn('422', self.run_cli('billing', 'status', '--claim-cursor', first['next_cursor'])[1]['error']['message'])
        for status in (403, 404, 422, 429):
            Server.api_error = (status, {'error': 'hidden'})
            self.assertIn(str(status), self.run_cli(*capture)[1]['error']['message'])
            self.assertIn(str(status), self.run_cli('billing', 'status')[1]['error']['message'])
        self.assertNotEqual(subprocess.run(self.base + ['events', 'track', '7', '--session-id', '', '--event-id', 'x'], capture_output=True).returncode, 0)

    def test_lead_permissions_pages_and_delete_uncertainty(self):
        self.run_cli('auth', 'login', '--delete-leads', '--browser-driver', str(self.driver))
        self.assertIn('leads:delete', Server.authorization['scope'][0].split())
        result, body = self.run_cli('leads', 'list', '--limit', '2', '--notification-id', '7', '--from', '2026-01-01', '--until', '2026-02-01', '--cursor', 'a+/=')
        self.assertEqual(result.returncode, 0)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(body['path']).query)
        self.assertEqual(query, {'limit': ['2'], 'notification_id': ['7'], 'from': ['2026-01-01'], 'until': ['2026-02-01'], 'cursor': ['a+/=']})
        self.assertEqual(self.run_cli('leads', 'show', '7')[1]['path'], '/api/v1/leads/7')
        result, body = self.run_cli('leads', 'delete', '7')
        self.assertEqual(body['error']['code'], 'confirmation_required')
        self.assertEqual(self.run_cli('leads', 'delete', '7', '--yes')[0].returncode, 0)
        Server.drop_create = True
        result, body = self.run_cli('leads', 'delete', '7', '--yes')
        self.assertEqual(body['error']['code'], 'delete_uncertain')
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/leads/7')), 2)
        Server.drop_create = False
        for status in (403, 404, 422, 429):
            Server.api_error = (status, {'errors': {'secret': ['secret marker']}})
            result, body = self.run_cli('leads', 'delete', '7', '--yes')
            self.assertIn(str(status), body['error']['message'])
            self.assertNotIn('secret marker', result.stderr)

    def test_statistics_output_authentication_and_errors(self):
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        result, body = self.run_cli('stats', 'show')
        self.assertEqual((result.returncode, body), (0, Server.statistics))
        self.assertEqual(Server.operations, [('GET', '/api/v1/statistics')])
        human = subprocess.run([x for x in self.base if x != '--json'] + ['stats', 'show'], capture_output=True, text=True, timeout=10)
        self.assertEqual(human.returncode, 0)
        self.assertEqual(json.loads(human.stdout), Server.statistics)
        self.assertIn('\n  "all_captures_count"', human.stdout)
        value = json.loads(self.creds.read_text())
        value['expires_at'] = 0
        self.creds.write_text(json.dumps(value))
        self.assertEqual(self.run_cli('stats', 'show')[1], Server.statistics)
        self.assertEqual(Server.refreshes, 1)
        Server.reject_next = True
        self.assertEqual(self.run_cli('stats', 'show')[1], Server.statistics)
        self.assertEqual(Server.refreshes, 2)
        for status in (403, 429, 503):
            Server.api_error = (status, {'error': 'synthetic-secret-marker'})
            before = len(Server.operations)
            result, body = self.run_cli('stats', 'show')
            self.assertEqual(result.returncode, 3)
            self.assertIn(str(status), body['error']['message'])
            self.assertNotIn('synthetic-secret-marker', result.stderr)
            self.assertNotIn('rotated', result.stderr)
            self.assertEqual(len(Server.operations) - before, 2 if status in (429, 503) else 1)
            if status == 403:
                self.assertIn('permissions', body['error']['message'])
        Server.api_error = None
        Server.reject_next = True
        Server.reject_refresh = True
        result, body = self.run_cli('stats', 'show')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'invalid_grant'))
        self.assertNotIn('rotated', result.stderr)

    def test_notification_delete_unapproved_never_opens_connection(self):
        unavailable = self.path / 'untouched' / 'credentials'
        base = self.base.copy()
        base[base.index(str(self.creds))] = str(unavailable)
        command = ['notifications', 'delete', '7']
        result = subprocess.run(base + command, input='', capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'confirmation_required')
        for answer in (b'n\n', b'\x04'):
            code, stdout, stderr, terminal = self.run_tty_cli(base, answer, *command)
            self.assertEqual(code, 1, stderr)
            self.assertEqual(stdout, '')
            self.assertEqual(json.loads(stderr)['error']['code'], 'delete_cancelled')
            self.assertIn('Permanently delete notification 7', terminal)
            self.assertIn('lead', terminal)
        self.assertFalse(unavailable.parent.exists())
        self.assertEqual(Server.calls, [])
        self.assertEqual(Server.operations, [])

    def test_notification_delete_yes_returns_confirmed_result(self):
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        result = subprocess.run(self.base + ['notifications', 'delete', '7', '--yes'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'deleted': True, 'id': 7})
        self.assertEqual(Server.operations, [('DELETE', '/api/v1/notifications/7')])

    def test_notification_delete_rejects_invalid_ids_before_connection(self):
        unavailable = self.path / 'untouched' / 'credentials'
        base = self.base.copy()
        base[base.index(str(self.creds))] = str(unavailable)
        for identifier in ('0', '-1', 'not-an-id', '7/other'):
            result = subprocess.run(base + ['notifications', 'delete', identifier, '--yes'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, '')
        self.assertFalse(unavailable.parent.exists())
        self.assertEqual(Server.calls, [])
        self.assertEqual(Server.operations, [])

    def test_notification_delete_checks_scope_owner_and_archived_record(self):
        Server.jwt_mode = True
        Server.notification_records = {7: {'owner': 42, 'state': 'archived'}, 8: {'owner': 43, 'state': 'active'}}
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        result, body = self.run_cli('notifications', 'delete', '7', '--yes')
        self.assertEqual(result.returncode, 3)
        self.assertIn('403', body['error']['message'])
        self.assertEqual(self.run_cli('notifications', 'show', '7')[1]['state'], 'archived')
        self.assertEqual(self.run_cli('auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        result, body = self.run_cli('notifications', 'delete', '8', '--yes')
        self.assertEqual(result.returncode, 3)
        self.assertIn('404', body['error']['message'])
        code, stdout, stderr, terminal = self.run_tty_cli(self.base, b'yes\n', 'notifications', 'delete', '7')
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(json.loads(stdout), {'deleted': True, 'id': 7})
        self.assertIn('collected leads', terminal)
        self.assertIn('404', self.run_cli('notifications', 'show', '7')[1]['error']['message'])
        self.assertIn('404', self.run_cli('notifications', 'delete', '7', '--yes')[1]['error']['message'])
        self.assertEqual(Server.notification_records, {8: {'owner': 43, 'state': 'active'}})

    def test_notification_delete_reports_uncertain_response_without_replay(self):
        Server.jwt_mode = True
        Server.notification_records = {7: {'owner': 42}, 8: {'owner': 42}, 9: {'owner': 42}}
        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        Server.drop_create = True
        result, body = self.run_cli('notifications', 'delete', '7', '--yes')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'delete_uncertain'))
        self.assertIn('Check the notification', body['error']['message'])
        self.assertEqual(result.stdout, '')
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/7')), 1)
        self.assertIn('404', self.run_cli('notifications', 'show', '7')[1]['error']['message'])
        Server.drop_create = False
        Server.api_error = (503, {'error': 'synthetic-secret-marker'})
        result, body = self.run_cli('notifications', 'delete', '8', '--yes')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'delete_uncertain'))
        self.assertNotIn('synthetic-secret-marker', result.stderr)
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/8')), 1)
        Server.api_error = (429, {})
        result, body = self.run_cli('notifications', 'delete', '8', '--yes')
        self.assertEqual(result.returncode, 3)
        self.assertIn('429', body['error']['message'])
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/8')), 2)
        Server.api_error = None
        Server.delete_success_status = 200
        result, body = self.run_cli('notifications', 'delete', '9', '--yes')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'delete_uncertain'))
        self.assertEqual(result.stdout, '')
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/9')), 1)
        self.assertEqual(set(Server.notification_records), {8, 9})

    def test_notification_delete_protocol_damage_is_uncertain_without_replay(self):
        Server.jwt_mode = True
        Server.notification_records = {7: {'owner': 42}, 8: {'owner': 42}, 9: {'owner': 42}}
        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        access = json.loads(self.creds.read_text())['access_token']
        for identifier, kind in ((7, 'bad-status'), (8, 'truncated-503'), (9, 'nested-503')):
            with self.subTest(kind=kind):
                path = '/api/v1/notifications/' + str(identifier)
                Server.response_fault = ('DELETE', path, kind)
                result = subprocess.run(self.base + ['notifications', 'delete', str(identifier), '--yes'], capture_output=True, text=True, timeout=10)
                Server.response_fault = None
                shown, body = self.run_cli('notifications', 'show', str(identifier))
                self.assertEqual(Server.operations.count(('DELETE', path)), 1)
                self.assertEqual(shown.returncode, 3)
                self.assertIn('404', body['error']['message'])
                self.assertTrue(access.encode() in Server.fault_requests[-1][2])
                self.assertFalse(access in result.stderr, 'The bearer credential reached the error output')
                self.assertFalse('synthetic-untrusted-marker' in result.stderr, 'Server text reached the error output')
                self.assertEqual(result.returncode, 3, 'A damaged delete response must be an operational error')
                self.assertEqual(result.stdout, '')
                self.assertEqual(json.loads(result.stderr)['error']['code'], 'delete_uncertain')

    def test_notification_delete_damaged_client_errors_are_uncertain_without_refresh(self):
        faults = [(status, 'truncated-' + str(status)) for status in (400, 403, 404, 408, 409, 422, 429)]
        faults += [(422, 'invalid-422'), (422, 'malformed-422'), (401, 'truncated-401')]
        Server.jwt_mode = True
        Server.notification_records = {identifier: {'owner': 42} for identifier in range(100, 100 + len(faults))}
        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = self.creds.read_bytes()
        access = json.loads(saved)['access_token']
        for identifier, (status, kind) in enumerate(faults, start=100):
            with self.subTest(status=status, kind=kind):
                path = '/api/v1/notifications/' + str(identifier)
                Server.response_fault = ('DELETE', path, kind)
                result = subprocess.run(self.base + ['notifications', 'delete', str(identifier), '--yes'], capture_output=True, text=True, timeout=10)
                Server.response_fault = None
                shown, body = self.run_cli('notifications', 'show', str(identifier))
                self.assertEqual(Server.operations.count(('DELETE', path)), 1)
                self.assertEqual(shown.returncode, 3)
                self.assertIn('404', body['error']['message'])
                self.assertNotIn(access, result.stdout + result.stderr)
                self.assertNotIn('synthetic-untrusted-marker', result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(result.stdout, '')
                self.assertEqual(json.loads(result.stderr)['error']['code'], 'delete_uncertain')
                self.assertEqual(Server.refreshes, 0)
                self.assertEqual(self.creds.read_bytes(), saved)

    def test_complete_empty_client_error_remains_an_http_error(self):
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        Server.response_fault = ('POST', '/api/v1/notifications', 'empty-422')
        result, body = self.run_cli('notifications', 'create', '--idempotency-key', 'empty-error', '--message', 'safe')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'http_error'))
        self.assertIn('422', body['error']['message'])

    def test_request_faults_never_expose_bearers_or_server_text(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--delete-leads', '--browser-driver', str(self.driver))[0].returncode, 0)
        access = json.loads(self.creds.read_text())['access_token']
        cases = (
            ('GET', '/api/v1/account', ('account', 'show'), 'network_error', 'http_error'),
            ('POST', '/api/v1/notifications', ('notifications', 'create', '--idempotency-key', 'key', '--message', 'synthetic-request-body-marker'), 'create_uncertain', 'create_uncertain'),
            ('POST', '/api/v1/notifications/7/track', ('events', 'track', '7', '--session-id', 'synthetic-session-marker', '--event-id', 'event'), 'event_uncertain', 'event_uncertain'),
            ('PUT', '/api/v1/notifications/7', ('notifications', 'edit', '7', '--revision', '2', '--message', 'synthetic-request-body-marker'), 'network_error', 'http_error'),
            ('DELETE', '/api/v1/leads/7', ('leads', 'delete', '7', '--yes'), 'delete_uncertain', 'delete_uncertain'),
            ('POST', '/api/v1/logout', ('auth', 'logout'), 'network_error', 'http_error'),
        )
        try:
            json.loads('[' * 2000 + ']' * 2000)
            nested_readable = True
        except RecursionError:
            nested_readable = False
        for method, path, command, bad_status, readable_error in cases:
            for kind, expected in (('bad-status', bad_status), ('truncated-503', bad_status), ('nested-503', readable_error if nested_readable else bad_status)):
                for json_mode in (True, False):
                    with self.subTest(method=method, path=path, kind=kind, json_mode=json_mode):
                        Server.fault_requests = []
                        Server.response_fault = (method, path, kind)
                        base = self.base if json_mode else [value for value in self.base if value != '--json']
                        result = subprocess.run(base + list(command), capture_output=True, text=True, timeout=10)
                        self.assertTrue(Server.fault_requests)
                        self.assertTrue(access.encode() in Server.fault_requests[-1][2])
                        self.assertFalse(access in result.stdout or access in result.stderr, 'The bearer credential reached output')
                        self.assertFalse('synthetic-untrusted-marker' in result.stdout or 'synthetic-untrusted-marker' in result.stderr, 'Server text reached output')
                        for marker in ('synthetic-request-body-marker', 'synthetic-session-marker'):
                            self.assertFalse(marker in result.stdout or marker in result.stderr, 'The request body reached output')
                        self.assertEqual(result.returncode, 3, 'A damaged response must be an operational error')
                        self.assertEqual(result.stdout, '')
                        if json_mode:
                            self.assertEqual(json.loads(result.stderr)['error']['code'], expected)
                        else:
                            self.assertTrue(result.stderr.startswith('Error: '))
        Server.response_fault = None

    def test_interrupted_delete_is_uncertain_without_replay_or_credential_output(self):
        Server.jwt_mode = True
        Server.notification_records = {7: {'owner': 42}}
        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        access = json.loads(self.creds.read_text())['access_token']
        Server.response_fault = ('DELETE', '/api/v1/notifications/7', 'stalled-503')
        code, stdout, stderr = self.interrupt_cli(self.base, 'notifications', 'delete', '7', '--yes')
        Server.response_fault = None
        shown, body = self.run_cli('notifications', 'show', '7')
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/7')), 1)
        self.assertEqual(shown.returncode, 3)
        self.assertIn('404', body['error']['message'])
        self.assertTrue(access.encode() in Server.fault_requests[-1][2])
        self.assertFalse(access in stderr, 'The bearer credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in stderr, 'Server text reached error output')
        self.assertEqual((code, stdout), (3, ''))
        self.assertEqual(json.loads(stderr)['error']['code'], 'delete_uncertain')

    def test_interrupted_requests_never_expose_bearers_or_request_bodies(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--events', '--delete-leads', '--browser-driver', str(self.driver))[0].returncode, 0)
        access = json.loads(self.creds.read_text())['access_token']
        cases = (
            ('GET', '/api/v1/account', ('account', 'show'), 'network_error'),
            ('POST', '/api/v1/notifications', ('notifications', 'create', '--idempotency-key', 'key', '--message', 'synthetic-request-body-marker'), 'create_uncertain'),
            ('POST', '/api/v1/notifications/7/track', ('events', 'track', '7', '--session-id', 'synthetic-session-marker', '--event-id', 'event'), 'event_uncertain'),
            ('PUT', '/api/v1/notifications/7', ('notifications', 'edit', '7', '--revision', '2', '--message', 'synthetic-request-body-marker'), 'network_error'),
            ('DELETE', '/api/v1/leads/7', ('leads', 'delete', '7', '--yes'), 'delete_uncertain'),
            ('POST', '/api/v1/logout', ('auth', 'logout'), 'network_error'),
        )
        for method, path, command, expected in cases:
            for json_mode in (True, False):
                with self.subTest(method=method, path=path, json_mode=json_mode):
                    Server.fault_requests = []
                    Server.response_fault = (method, path, 'stalled-503')
                    base = self.base if json_mode else [value for value in self.base if value != '--json']
                    code, stdout, stderr = self.interrupt_cli(base, *command)
                    self.assertTrue(access.encode() in Server.fault_requests[-1][2])
                    self.assertFalse(access in stdout or access in stderr, 'The bearer credential reached output')
                    for marker in ('synthetic-untrusted-marker', 'synthetic-request-body-marker', 'synthetic-session-marker'):
                        self.assertFalse(marker in stdout or marker in stderr, 'Untrusted text reached output')
                    self.assertEqual((code, stdout), (3, ''))
                    if json_mode:
                        self.assertEqual(json.loads(stderr)['error']['code'], expected)
                    else:
                        self.assertTrue(stderr.startswith('Error: '))
        Server.response_fault = None

    def test_interrupted_read_retry_never_exposes_the_bearer(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        access = json.loads(self.creds.read_text())['access_token']
        Server.response_fault = ('GET', '/api/v1/account', 'retry-503')
        code, stdout, stderr = self.interrupt_cli(self.base, 'account', 'show')
        self.assertEqual(len(Server.fault_requests), 1)
        self.assertTrue(access.encode() in Server.fault_requests[0][2])
        self.assertFalse(access in stderr, 'The bearer credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in stderr, 'Server text reached error output')
        self.assertEqual((code, stdout), (3, ''))
        self.assertEqual(json.loads(stderr)['error']['code'], 'network_error')

    def test_interrupted_login_never_exposes_the_authorization_verifier(self):
        Server.response_fault = ('POST', '/oauth/token', 'stalled-503')
        code, stdout, stderr = self.interrupt_cli(self.base, 'auth', 'login', '--browser-driver', str(self.driver))
        form = urllib.parse.parse_qs(Server.fault_requests[-1][2].decode().strip())
        verifier = form['code_verifier'][0]
        self.assertTrue(verifier)
        self.assertFalse(verifier in stdout or verifier in stderr, 'The authorization verifier reached output')
        self.assertFalse('synthetic-untrusted-marker' in stderr, 'Server text reached error output')
        self.assertEqual((code, stdout), (3, ''))
        self.assertEqual(json.loads(stderr)['error']['code'], 'login_uncertain')
        self.assertFalse(self.creds.exists())

    def test_interrupted_refresh_preserves_the_old_credential(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved['refresh_token'] = 'synthetic-refresh-secret-marker'
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.current_refresh = saved['refresh_token']
        Server.response_fault = ('POST', '/oauth/token', 'stalled-503')
        code, stdout, stderr = self.interrupt_cli(self.base, 'account', 'show')
        self.assertTrue(saved['refresh_token'].encode() in Server.fault_requests[-1][2])
        self.assertFalse(saved['refresh_token'] in stderr, 'The refresh credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in stderr, 'Server text reached error output')
        self.assertEqual((code, stdout), (3, ''))
        self.assertEqual(json.loads(stderr)['error']['code'], 'network_error')
        self.assertEqual(json.loads(self.creds.read_text()), dict(saved, refresh_pending=True))

    def test_interrupted_login_cleanup_never_exposes_the_bearer(self):
        Server.jwt_mode = True
        Server.account_error = 'synthetic-account-error'
        Server.response_fault = ('POST', '/api/v1/logout', 'stalled-503')
        code, stdout, stderr = self.interrupt_cli(self.base, 'auth', 'login', '--browser-driver', str(self.driver))
        access = Server.fault_requests[-1][2].decode().removeprefix('Bearer ').strip()
        self.assertTrue(access)
        self.assertFalse(access in stderr, 'The cleanup bearer credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in stderr, 'Server text reached error output')
        self.assertEqual((code, stdout), (3, ''))
        self.assertEqual(json.loads(stderr)['error']['code'], 'cleanup_unconfirmed')
        self.assertFalse(self.creds.exists())

    def test_deep_success_response_is_valid_or_a_safe_network_error(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        access = json.loads(self.creds.read_text())['access_token']
        Server.response_fault = ('GET', '/api/v1/account', 'nested-200')
        result = subprocess.run(self.base + ['account', 'show'], capture_output=True, text=True, timeout=10)
        self.assertTrue(access.encode() in Server.fault_requests[-1][2])
        self.assertFalse(access in result.stderr, 'The bearer credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in result.stderr, 'Server text reached error output')
        if result.returncode == 0:
            self.assertEqual(result.stderr, '')
            self.assertTrue(result.stdout.startswith('[['))
        else:
            self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads(result.stderr)['error']['code'], 'network_error')

    def test_login_fault_never_exposes_the_authorization_form(self):
        Server.jwt_mode = True
        Server.response_fault = ('POST', '/oauth/token', 'bad-status')
        result = subprocess.run(self.base + ['auth', 'login', '--browser-driver', str(self.driver)], capture_output=True, text=True, timeout=10)
        form = urllib.parse.parse_qs(Server.fault_requests[-1][2].decode().strip())
        verifier = form['code_verifier'][0]
        self.assertTrue(verifier)
        self.assertFalse(verifier in result.stdout or verifier in result.stderr, 'The authorization verifier reached output')
        self.assertFalse('code_verifier' in result.stderr, 'The authorization form reached error output')
        self.assertFalse('synthetic-untrusted-marker' in result.stderr, 'Server text reached error output')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'login_uncertain')
        self.assertFalse(self.creds.exists())

    def test_refresh_fault_never_exposes_the_refresh_credential(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved['refresh_token'] = 'synthetic-refresh-secret-marker'
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.current_refresh = saved['refresh_token']
        Server.response_fault = ('POST', '/oauth/token', 'bad-status')
        result = subprocess.run(self.base + ['account', 'show'], capture_output=True, text=True, timeout=10)
        self.assertTrue(saved['refresh_token'].encode() in Server.fault_requests[-1][2])
        self.assertFalse(saved['refresh_token'] in result.stderr, 'The refresh credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in result.stderr, 'Server text reached error output')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'network_error')
        pending = json.loads(self.creds.read_text())
        self.assertEqual(pending['access_token'], saved['access_token'])
        self.assertEqual(pending['refresh_token'], saved['refresh_token'])
        self.assertTrue(pending['refresh_pending'])

    def test_login_cleanup_fault_never_exposes_the_bearer(self):
        Server.jwt_mode = True
        Server.account_error = 'synthetic-account-error'
        Server.response_fault = ('POST', '/api/v1/logout', 'bad-status')
        result = subprocess.run(self.base + ['auth', 'login', '--browser-driver', str(self.driver)], capture_output=True, text=True, timeout=10)
        echoed = Server.fault_requests[-1][2].decode()
        access = echoed.removeprefix('Bearer ').strip()
        self.assertTrue(access)
        self.assertFalse(access in result.stderr, 'The cleanup bearer credential reached error output')
        self.assertFalse('synthetic-untrusted-marker' in result.stderr, 'Server text reached error output')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'cleanup_unconfirmed')
        self.assertFalse(self.creds.exists())

    def test_nested_legacy_subject_decodes_or_fails_without_changing_the_credential(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved.pop('account_id')
        saved['expires_at'] = 0
        saved['access_token'] = nested_claim_token(saved['access_token'])
        self.creds.write_text(json.dumps(saved))
        before = self.creds.read_bytes()
        result = subprocess.run(self.base + ['account', 'show'], capture_output=True, text=True, timeout=10)
        self.assertNotIn('Traceback', result.stderr)
        for secret in (saved['access_token'], saved['refresh_token']):
            self.assertFalse(secret in result.stdout + result.stderr, 'A credential reached the output')
        if nested_claim_readable():
            self.assertEqual((result.returncode, json.loads(result.stdout)['id']), (0, 42))
            self.assertEqual(json.loads(self.creds.read_text())['account_id'], 42)
            self.assertEqual(Server.refreshes, 1)
        else:
            self.assertEqual((result.returncode, json.loads(result.stderr)['error']['code']), (3, 'account_unknown'))
            self.assertEqual(self.creds.read_bytes(), before)
            self.assertEqual(Server.refreshes, 0)

    def test_nested_refreshed_scopes_decode_or_leave_the_old_credential_pending(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.token_fault = ('refresh_token', 'deep')
        Server.account_payload = {'id': 42}
        command = ['auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver)]
        result = subprocess.run(self.base + command, capture_output=True, text=True, timeout=10)
        self.assertNotIn('Traceback', result.stderr)
        for secret in (saved['access_token'], saved['refresh_token'], Server.issued_access):
            self.assertFalse(secret in result.stdout + result.stderr, 'A credential reached the output')
        self.assertEqual(Server.refreshes, 1)
        if nested_claim_readable():
            self.assertEqual((result.returncode, json.loads(result.stdout)['account']['id']), (0, 42))
            self.assertEqual(json.loads(self.creds.read_text())['account_id'], 42)
            self.assertEqual(Server.grant_number, 2)
        else:
            self.assertEqual((result.returncode, json.loads(result.stderr)['error']['code']), (3, 'refresh_uncertain'))
            self.assertEqual(json.loads(self.creds.read_text()), dict(saved, refresh_pending=True))
            self.assertEqual(Server.grant_number, 1)
            self.assertEqual(Server.logout_bearers, [])

    def test_undecodable_upgrade_grant_is_revoked_or_cleanup_is_reported(self):
        for fault in ('deep', 'invalid'):
            for reject_logout in (False, True):
                with self.subTest(fault=fault, reject_logout=reject_logout):
                    self.creds.unlink(missing_ok=True)
                    Server.jwt_mode = True
                    Server.token_fault = None
                    Server.account_payload = None
                    Server.reject_logout = False
                    Server.current_refresh = 'first'
                    Server.grant_number = 0
                    Server.calls = []
                    Server.logout_bearers = []
                    self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
                    before = self.creds.read_bytes()
                    saved = json.loads(before)
                    Server.token_fault = ('authorization_code', fault)
                    Server.account_payload = {'id': 42}
                    Server.reject_logout = reject_logout
                    command = ['auth', 'login', '--add', '--delete-notifications', '--browser-driver', str(self.driver)]
                    result = subprocess.run(self.base + command, capture_output=True, text=True, timeout=10)
                    self.assertNotIn('Traceback', result.stderr)
                    for secret in (saved['access_token'], saved['refresh_token'], Server.issued_access):
                        self.assertFalse(secret in result.stdout + result.stderr, 'A credential reached the output')
                    self.assertEqual(Server.grant_number, 2)
                    self.assertEqual(len(Server.logout_bearers), 1)
                    if fault == 'deep' and nested_claim_readable():
                        self.assertTrue(Server.logout_bearers[0] == 'Bearer ' + saved['access_token'])
                        self.assertNotEqual(self.creds.read_bytes(), before)
                        if reject_logout:
                            self.assertEqual((result.returncode, json.loads(result.stderr)['error']['code']), (3, 'cleanup_unconfirmed'))
                        else:
                            self.assertEqual((result.returncode, json.loads(result.stdout)['account']['id']), (0, 42))
                    else:
                        self.assertTrue(Server.logout_bearers[0] == 'Bearer ' + Server.issued_access)
                        self.assertEqual(self.creds.read_bytes(), before)
                        expected = 'cleanup_unconfirmed' if reject_logout else 'scope_unknown'
                        error = json.loads(result.stderr)['error']
                        self.assertEqual((result.returncode, error['code']), (3, expected))
                        if reject_logout:
                            self.assertIn('revocation', error['message'])
                            self.assertIn('could not be confirmed', error['message'])

    def test_invalid_stored_claims_report_errors_without_refresh_or_traceback(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        original = json.loads(self.creds.read_text())
        original['refresh_token'] = 'synthetic-refresh-credential-marker'
        for operation in ('subject', 'scopes'):
            for access in (None, 7, 'synthetic-access-credential-marker', 'header.☃.signature'):
                with self.subTest(operation=operation, access_type=type(access).__name__):
                    saved = dict(original, access_token=access)
                    if operation == 'subject':
                        saved.pop('account_id')
                        saved['expires_at'] = 0
                        command = ['account', 'show']
                        expected = 'account_unknown'
                    else:
                        saved['expires_at'] = 9999999999
                        command = ['auth', 'login', '--add', '--events', '--browser-driver', str(self.driver)]
                        expected = 'scope_unknown'
                    self.creds.write_text(json.dumps(saved))
                    before = self.creds.read_bytes()
                    result = subprocess.run(self.base + command, capture_output=True, text=True, timeout=10)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertEqual((result.returncode, json.loads(result.stderr)['error']['code']), (3, expected))
                    self.assertEqual(self.creds.read_bytes(), before)
                    self.assertEqual(Server.refreshes, 0)
                    self.assertEqual(Server.grant_number, 1)
                    self.assertEqual(Server.logout_bearers, [])
                    self.assertNotIn('synthetic-refresh-credential-marker', result.stdout + result.stderr)
                    if isinstance(access, str):
                        self.assertFalse(access in result.stdout + result.stderr, 'A credential reached the output')

    def test_ordinary_refresh_rejects_another_account_before_delete_or_read(self):
        for storage in ('new', 'legacy-jwt'):
            for trigger in ('expired', '401'):
                for first_command in ('delete', 'read'):
                    with self.subTest(storage=storage, trigger=trigger, first_command=first_command):
                        self.creds.unlink(missing_ok=True)
                        Server.jwt_mode = True
                        Server.refresh_account = None
                        Server.current_refresh = 'first'
                        Server.refreshes = 0
                        Server.reject_next = False
                        Server.operations = []
                        Server.notification_records = {7: {'owner': 43}}
                        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
                        saved = json.loads(self.creds.read_text())
                        if storage == 'legacy-jwt':
                            saved.pop('account_id', None)
                        if trigger == 'expired':
                            saved['expires_at'] = 0
                        self.creds.write_text(json.dumps(saved))
                        Server.refresh_account = 43
                        Server.reject_next = trigger == '401'
                        command = ('notifications', 'delete', '7', '--yes') if first_command == 'delete' else ('account', 'show')
                        result, body = self.run_cli(*command)
                        self.assertEqual((result.returncode, body.get('error', {}).get('code')), (3, 'refresh_account_changed'))
                        self.assertIn('reconnect', body['error']['message'])
                        pending = json.loads(self.creds.read_text())
                        self.assertEqual(pending, dict(saved, refresh_pending=True))
                        self.assertEqual(Server.refreshes, 1)
                        expected_deletes = 1 if trigger == '401' and first_command == 'delete' else 0
                        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/7')), expected_deletes)
                        retry, retry_body = self.run_cli('notifications', 'delete', '7', '--yes')
                        self.assertEqual((retry.returncode, retry_body['error']['code']), (3, 'refresh_uncertain'))
                        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/7')), expected_deletes)
                        self.assertEqual(Server.notification_records, {7: {'owner': 43}})

    def test_opaque_connection_rejects_refresh_for_another_account(self):
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.refresh_account = 43
        result, body = self.run_cli('account', 'show')
        self.assertEqual((result.returncode, body.get('error', {}).get('code')), (3, 'refresh_account_changed'))
        self.assertEqual(json.loads(self.creds.read_text()), dict(saved, refresh_pending=True))
        self.assertEqual(Server.refreshes, 1)

    def test_refresh_requires_a_verifiable_account_before_saving(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.account_error = 'synthetic-untrusted-marker'
        result, body = self.run_cli('account', 'show')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'refresh_uncertain'))
        self.assertFalse('synthetic-untrusted-marker' in result.stderr)
        self.assertEqual(json.loads(self.creds.read_text()), dict(saved, refresh_pending=True))
        self.assertEqual(Server.refreshes, 1)
        self.assertEqual(self.run_cli('account', 'show')[1]['error']['code'], 'refresh_uncertain')
        self.assertEqual(Server.refreshes, 1)

    def test_legacy_jwt_refresh_records_the_verified_account(self):
        Server.jwt_mode = True
        self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
        saved = json.loads(self.creds.read_text())
        saved.pop('account_id', None)
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        result, body = self.run_cli('account', 'show')
        self.assertEqual((result.returncode, body['id']), (0, 42))
        self.assertEqual(json.loads(self.creds.read_text())['account_id'], 42)

    def test_legacy_opaque_credentials_require_a_known_account_before_refresh(self):
        for trigger in ('expired', '401'):
            with self.subTest(trigger=trigger):
                self.creds.unlink(missing_ok=True)
                Server.jwt_mode = False
                Server.current_refresh = 'first'
                Server.refreshes = 0
                Server.reject_next = False
                self.assertEqual(self.run_cli('auth', 'login', '--browser-driver', str(self.driver))[0].returncode, 0)
                saved = json.loads(self.creds.read_text())
                saved.pop('account_id', None)
                if trigger == 'expired':
                    saved['expires_at'] = 0
                self.creds.write_text(json.dumps(saved))
                before = self.creds.read_bytes()
                Server.reject_next = trigger == '401'
                result, body = self.run_cli('account', 'show')
                self.assertEqual((result.returncode, body.get('error', {}).get('code')), (3, 'account_unknown'))
                self.assertEqual(self.creds.read_bytes(), before)
                self.assertEqual(Server.refreshes, 0)

    def test_login_requires_a_verifiable_account_before_saving(self):
        Server.account_payload = {'name': 'Synthetic'}
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual((result.returncode, body.get('error', {}).get('code')), (3, 'account_unknown'))
        self.assertFalse(self.creds.exists())
        self.assertTrue(any(path == '/api/v1/logout' for path, _ in Server.calls))

    def test_notification_delete_does_not_replay_after_refresh_or_revocation(self):
        Server.jwt_mode = True
        Server.notification_records = {7: {'owner': 42}, 8: {'owner': 42}}
        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        Server.reject_next = True
        result, body = self.run_cli('notifications', 'delete', '7', '--yes')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'operation_not_retried'))
        self.assertIn('notification', body['error']['message'])
        self.assertIn('not retried', body['error']['message'])
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/7')), 1)
        self.assertEqual(self.run_cli('notifications', 'show', '7')[1]['owner'], 42)
        Server.reject_next = True
        Server.reject_refresh = True
        result, body = self.run_cli('notifications', 'delete', '8', '--yes')
        self.assertEqual((result.returncode, body['error']['code']), (3, 'invalid_grant'))
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/8')), 1)
        result, body = self.run_cli('notifications', 'delete', '8', '--yes')
        self.assertEqual(body['error']['code'], 'refresh_uncertain')
        self.assertEqual(Server.operations.count(('DELETE', '/api/v1/notifications/8')), 1)
        self.assertEqual(set(Server.notification_records), {7, 8})

    def test_notification_delete_human_output_reports_confirmed_result(self):
        self.assertEqual(self.run_cli('auth', 'login', '--delete-notifications', '--browser-driver', str(self.driver))[0].returncode, 0)
        base = [value for value in self.base if value != '--json']
        result = subprocess.run(base + ['notifications', 'delete', '7', '--yes'], capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(json.loads(result.stdout), {'deleted': True, 'id': 7})
        self.assertIn('\n  "deleted": true', result.stdout)
        self.assertEqual(Server.operations, [('DELETE', '/api/v1/notifications/7')])

    def test_notification_commands_and_recovery(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(set(Server.authorization['scope'][0].split()), {'account:read', 'notifications:read', 'notifications:write', 'installation:read', 'activity:read', 'leads:read', 'statistics:read'})
        for _ in range(2):
            result, body = self.run_cli('notifications', 'create', '--idempotency-key', 'order-123', '--message', 'Hello', '--no-display-maps-only')
            self.assertEqual((result.returncode, body['id']), (0, 7))
        self.assertEqual(Server.operations[0], Server.operations[1])
        self.assertEqual(Server.operations[0][2:], ('order-123', {'message': 'Hello', 'display_maps_only': False}))
        result, body = self.run_cli('notifications', 'edit', '7', '--revision', '1', '--message', 'Changed')
        self.assertEqual(result.returncode, 3)
        self.assertIn('revision', body['error']['message'])
        result, body = self.run_cli('notifications', 'edit', '7', '--revision', '2', '--message', 'Changed')
        self.assertEqual(body['revision'], 3)
        self.assertEqual(Server.operations[-1][2], {'message': 'Changed', 'revision': 2})
        for action in ('activate', 'deactivate', 'archive', 'restore'):
            self.assertEqual(self.run_cli('notifications', action, '7')[0].returncode, 0)
        for args in (('notifications', 'show', '7'), ('notifications', 'activity', '7'), ('installation', 'show'), ('notifications', 'list', '--limit', '3', '--after', '7')):
            self.assertEqual(self.run_cli(*args)[0].returncode, 0)
        self.assertEqual(Server.operations[-1], ('GET', '/api/v1/notifications?limit=3&after=7'))
        result = subprocess.run(self.base + ['notifications', 'create', '--idempotency-key', 'bad key', '--message', 'x'], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_unauthorized_refresh_and_uncertain_create(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        Server.reject_next = True
        self.assertEqual(self.run_cli('notifications', 'show', '7')[0].returncode, 0)
        self.assertEqual(Server.refreshes, 1)
        Server.reject_next = True
        result, body = self.run_cli('notifications', 'create', '--idempotency-key', 'key', '--message', 'Hello')
        self.assertEqual(body['error']['code'], 'operation_not_retried')
        self.assertEqual(Server.operations, [('GET', '/api/v1/notifications/7')])
        Server.drop_create = True
        result, body = self.run_cli('notifications', 'create', '--idempotency-key', 'key', '--message', 'Hello')
        self.assertEqual(body['error']['code'], 'create_uncertain')
        self.assertIn('same idempotency key', body['error']['message'])
        self.assertEqual(len(Server.operations), 2)

    def test_notification_error_boundaries(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        command = ('notifications', 'create', '--idempotency-key', 'key', '--message', 'Hello')
        Server.api_error = (422, {'errors': {'message': ['secret marker'], 'unknown-secret-marker': ['secret marker']}})
        result, body = self.run_cli(*command)
        self.assertEqual(result.returncode, 3)
        self.assertIn('message', body['error']['message'])
        self.assertNotIn('secret marker', result.stderr)
        self.assertNotIn('unknown-secret-marker', result.stderr)
        Server.api_error = (503, {'error': 'server_error'})
        result, body = self.run_cli(*command)
        self.assertEqual(body['error']['code'], 'create_uncertain')
        self.assertIn('same idempotency key', body['error']['message'])
        for status in (403, 404, 429):
            Server.api_error = (status, {})
            result, body = self.run_cli(*command)
            self.assertEqual(result.returncode, 3)
            self.assertIn(str(status), body['error']['message'])

    def test_login_restart_refresh_account_and_logout(self):
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(body['account']['id'], 42)
        self.assertEqual(self.creds.stat().st_mode & 0o777, 0o600)
        value = json.loads(self.creds.read_text())
        value['expires_at'] = 0
        self.creds.write_text(json.dumps(value))
        result, body = self.run_cli('account', 'show')
        self.assertEqual(body['id'], 42)
        self.assertEqual(json.loads(self.creds.read_text())['refresh_token'], 'rotated')
        result, body = self.run_cli('auth', 'logout')
        self.assertTrue(body['revoked'])
        self.assertFalse(self.creds.exists())
    def test_wrong_state_does_not_save(self):
        env = dict(os.environ, WRONG_STATE='1')
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver), env=env)
        self.assertEqual(body['error']['code'], 'state_mismatch')
        self.assertFalse(self.creds.exists())
    def test_denial_and_timeout_do_not_save(self):
        for extra, expected in [({'DENY': '1'}, 'authorization_denied'), ({'NO_CALLBACK': '1'}, 'callback_timeout')]:
            result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver), '--callback-timeout', '1', env=dict(os.environ, **extra))
            self.assertEqual(body['error']['code'], expected)
            self.assertFalse(self.creds.exists())
    def test_private_file_and_connection_identity(self):
        self.creds.write_text('{}')
        self.creds.chmod(0o644)
        result, body = self.run_cli('auth', 'status')
        self.assertEqual(body['error']['code'], 'unsafe_storage')
        self.creds.chmod(0o600)
        self.creds.write_text('{"identity":"different"}')
        result, body = self.run_cli('auth', 'status')
        self.assertEqual(body['error']['code'], 'wrong_connection')
    def test_revoked_refresh_is_reported_and_can_be_forgotten(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        value = json.loads(self.creds.read_text())
        value['expires_at'] = 0
        self.creds.write_text(json.dumps(value))
        Server.reject_refresh = True
        result, body = self.run_cli('account', 'show')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(body['error']['code'], 'invalid_grant')
        self.assertTrue(self.creds.exists())
        saved = json.loads(self.creds.read_text())
        self.assertEqual(saved['refresh_token'], 'first')
        count = len(Server.calls)
        result, body = self.run_cli('account', 'show')
        self.assertEqual(body['error']['code'], 'refresh_uncertain')
        self.assertEqual(len(Server.calls), count)
        result, body = self.run_cli('auth', 'logout', '--local')
        self.assertFalse(body['revoked'])
        self.assertFalse(self.creds.exists())
    def test_lost_refresh_response_is_not_replayed(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        saved = json.loads(self.creds.read_text())
        saved['expires_at'] = 0
        self.creds.write_text(json.dumps(saved))
        Server.drop_refresh_response = True
        result, body = self.run_cli('account', 'show')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(Server.refreshes, 1)
        self.assertEqual(json.loads(self.creds.read_text())['refresh_token'], 'first')
        result, body = self.run_cli('account', 'show')
        self.assertEqual(body['error']['code'], 'refresh_uncertain')
        self.assertEqual(Server.refreshes, 1)
        self.assertEqual(self.run_cli('auth', 'logout', '--local')[0].returncode, 0)

    def test_uncertain_login_and_recovery(self):
        for response in ('drop', 'malformed', 'unusable'):
            for json_mode in (True, False):
                Server.login_response = response
                base = self.base if json_mode else [x for x in self.base if x != '--json']
                result = subprocess.run(base + ['auth', 'login', '--browser-driver', str(self.driver)], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 3)
                self.assertIn('may have been created', result.stderr)
                self.assertIn('before retrying', result.stderr)
                self.assertIn('account', result.stderr)
                self.assertNotIn('synthetic-secret-marker', result.stderr)
                self.assertFalse(self.creds.exists())
                if json_mode:
                    self.assertEqual(json.loads(result.stderr)['error']['code'], 'login_uncertain')
        Server.login_response = 'reject'
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(body['error']['code'], 'invalid_grant')
        Server.login_response = None
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_login_failure_revokes_and_retry_succeeds(self):
        Server.account_error = 'synthetic-secret-marker'
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(body['error']['code'], 'http_error')
        self.assertNotIn('synthetic-secret-marker', result.stderr)
        self.assertFalse(self.creds.exists())
        self.assertTrue(any(path == '/api/v1/logout' for path, _ in Server.calls))
        Server.account_error = None
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.creds.read_bytes()
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(body['error']['code'], 'already_connected')
        self.assertEqual(self.creds.read_bytes(), before)

    def test_login_reports_unconfirmed_revocation(self):
        Server.account_error = 'unavailable'
        Server.reject_logout = True
        result, body = self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(body['error']['code'], 'cleanup_unconfirmed')
        self.assertIn('Revoke the connection', body['error']['message'])
        self.assertFalse(self.creds.exists())
        self.assertNotIn('synthetic-secret-marker', result.stderr)

    def test_aliases_serialize_refresh(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        value = json.loads(self.creds.read_text())
        value['expires_at'] = 0
        self.creds.write_text(json.dumps(value))
        alias = self.path / 'alias'
        alias.symlink_to(self.path, target_is_directory=True)
        other = self.base.copy()
        other[other.index(str(self.creds))] = str(alias / 'credentials')
        processes = [subprocess.Popen(base + ['account', 'show'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for base in (self.base, other)]
        for process in processes:
            out, err = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, err)
            self.assertEqual(json.loads(out)['id'], 42)
        self.assertEqual(Server.refreshes, 1)
        self.assertEqual(json.loads(self.creds.read_text())['refresh_token'], 'rotated')
        self.assertEqual(self.run_cli('account', 'show')[0].returncode, 0)

    def test_untrusted_errors_never_reach_diagnostics(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        for error in ('synthetic-secret-marker', 'invalid_grant\nsecret', '', 'x' * 500):
            Server.account_error = error
            for json_mode in (True, False):
                base = self.base if json_mode else [x for x in self.base if x != '--json']
                result = subprocess.run(base + ['account', 'show'], capture_output=True, text=True, timeout=10)
                self.assertNotIn(error or 'synthetic-secret-marker', result.stderr)
                if json_mode:
                    self.assertEqual(json.loads(result.stderr)['error']['code'], 'http_error')

    def test_local_logout_is_explicit(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        result, body = self.run_cli('auth', 'logout', '--local')
        self.assertFalse(body['revoked'])
        self.assertFalse(self.creds.exists())

class DefaultRouting(unittest.TestCase):
    def test_clean_login_routes_to_the_official_service_and_public_client(self):
        from contextlib import nullcontext, redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import uptible_cli

        class MemoryStore:
            lock = nullcontext()
            def __init__(self, issuer, client, profile, filename):
                self.connection = (issuer, client, profile, filename)
            def load(self):
                return None
            def validate(self, token):
                return token
            def write(self, token):
                pass

        with patch.object(sys, 'argv', ['uptible', 'auth', 'login']), \
             patch.dict(os.environ, {'UPTIBLE_ISSUER': 'https://other.example', 'UPTIBLE_CLIENT_ID': 'other'}), \
             patch.object(uptible_cli, 'Store', MemoryStore), \
             patch.object(uptible_cli, 'authorize', return_value={'access_token': 'synthetic'}) as authorize, \
             patch.object(uptible_cli, 'request', return_value={'id': 42}) as request, \
             redirect_stdout(StringIO()):
            self.assertEqual(uptible_cli.main(), 0)
        self.assertEqual(authorize.call_args.args[:2], ('https://uptible.com', '5af9087d-4c3a-4bb9-a144-3cbf5560771a'))
        self.assertEqual(request.call_args.args[0], 'https://uptible.com/api/v1/account')

    def test_delete_eof_cancels_without_accessing_connection(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from unittest.mock import patch
        import uptible_cli

        with patch.object(sys, 'argv', ['uptible', '--json', 'leads', 'delete', '7']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('builtins.input', side_effect=EOFError), \
             patch.object(uptible_cli, 'Store') as store, redirect_stderr(StringIO()) as error:
            self.assertEqual(uptible_cli.main(), 1)
        store.assert_not_called()
        self.assertIn('Deletion cancelled', error.getvalue())

    def test_alternate_service_requires_explicit_client(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from unittest.mock import patch
        import uptible_cli

        with patch.object(sys, 'argv', ['uptible', '--issuer', 'https://other.example', 'auth', 'status']), redirect_stderr(StringIO()) as error:
            self.assertEqual(uptible_cli.main(), 2)
        self.assertIn('--client-id', error.getvalue())


if __name__ == '__main__':
    unittest.main()
