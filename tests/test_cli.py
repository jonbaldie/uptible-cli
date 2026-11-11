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
    def log_message(self, *args):
        pass
    def respond(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(raw)
    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
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
    def do_GET(self):
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

if __name__ == '__main__':
    unittest.main()
