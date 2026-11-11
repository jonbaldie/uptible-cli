import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Server(BaseHTTPRequestHandler):
    calls = []
    authorization = None
    reject_refresh = False
    account_error = None
    refreshes = 0
    reject_logout = False
    drop_refresh_response = False
    login_response = None
    current_refresh = "first"
    operations = []
    reject_next = False
    drop_create = False
    api_error = None
    def log_message(self, *args):
        pass
    def respond(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(raw)
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
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
            self.respond({'access_token': 'access', 'refresh_token': self.current_refresh, 'expires_in': 60})
        elif self.path == '/api/v1/logout' and self.reject_logout:
            self.respond({'error': 'synthetic-secret-marker'}, 503)
        elif self.path == '/api/v1/logout':
            self.send_response(204)
            self.end_headers()
        else:
            self.respond({'error': 'unknown'}, 404)
    def do_PUT(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.operations.append(('PUT', self.path, json.loads(raw)))
        if self.path == '/api/v1/notifications/7' and json.loads(raw).get('revision') != 2:
            self.respond({'error': 'conflict'}, 409)
        else:
            self.respond({'id': 7, 'revision': 3})
    def do_DELETE(self):
        self.operations.append(('DELETE', self.path))
        if self.drop_create:
            self.connection.shutdown(2)
            self.connection.close()
        elif self.api_error:
            self.respond(self.api_error[1], self.api_error[0])
        else:
            self.send_response(204)
            self.end_headers()
    def do_GET(self):
        if self.reject_next and self.path.startswith('/api/'):
            type(self).reject_next = False
            self.respond({'error': 'unauthorized'}, 401)
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
        elif self.path == '/api/v1/account' and self.headers.get('Authorization') == 'Bearer access':
            self.respond({'id': 42, 'name': 'Example', 'email': 'person@example.test'})
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

    def test_notification_commands_and_recovery(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        self.assertEqual(set(Server.authorization['scope'][0].split()), {'account:read', 'notifications:read', 'notifications:write', 'installation:read', 'activity:read', 'leads:read'})
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
            def save(self, token):
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
