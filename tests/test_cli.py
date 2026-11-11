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
                verifier = form['code_verifier'][0]
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                if not self.authorization or challenge != self.authorization['code_challenge'][0] or form['redirect_uri'] != self.authorization['redirect_uri']:
                    self.respond({'error': 'invalid_grant'}, 400)
                    return
            if form.get('grant_type') == ['refresh_token'] and self.reject_refresh:
                self.respond({'error': 'invalid_grant'}, 400)
                return
            self.respond({'access_token': 'access', 'refresh_token': 'rotated' if form.get('grant_type') == ['refresh_token'] else 'first', 'expires_in': 1})
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
        Server.authorization = None
        Server.reject_refresh = False
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
        time.sleep(1.1)
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
        time.sleep(1.1)
        Server.reject_refresh = True
        result, body = self.run_cli('account', 'show')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(body['error']['code'], 'invalid_grant')
        self.assertTrue(self.creds.exists())
        result, body = self.run_cli('auth', 'logout', '--local')
        self.assertFalse(body['revoked'])
        self.assertFalse(self.creds.exists())
    def test_local_logout_is_explicit(self):
        self.run_cli('auth', 'login', '--browser-driver', str(self.driver))
        result, body = self.run_cli('auth', 'logout', '--local')
        self.assertFalse(body['revoked'])
        self.assertFalse(self.creds.exists())

if __name__ == '__main__':
    unittest.main()
