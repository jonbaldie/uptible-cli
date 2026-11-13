"""Opt-in checks against an explicitly provisioned, disposable test account."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
import uuid


@unittest.skipUnless(os.environ.get('UPTIBLE_INTEGRATION') == 'dedicated-test-account',
                     'requires an explicitly provisioned integration account')
class ActualAccount(unittest.TestCase):
    def test_browser_login_and_owned_draft(self):
        from uptible_cli import issuer_url

        issuer = issuer_url(os.environ['UPTIBLE_TEST_ISSUER'])
        if urllib.parse.urlsplit(issuer).hostname in ('uptible.com', 'www.uptible.com'):
            self.fail('Use an isolated test service, not the production issuer')
        client = os.environ['UPTIBLE_TEST_CLIENT_ID']
        expected = int(os.environ['UPTIBLE_TEST_ACCOUNT_ID'])
        self.assertGreater(expected, 0)
        with tempfile.TemporaryDirectory(prefix='uptible-integration-') as directory:
            credentials = Path(directory) / 'credentials.json'
            base = [sys.executable, '-m', 'uptible_cli', '--json', '--issuer', issuer,
                    '--client-id', client, '--credential-file', str(credentials)]
            created = None
            connected = False

            def command(*args):
                result = subprocess.run([*base, *args], capture_output=True, text=True, timeout=630)
                try:
                    body = json.loads(result.stdout or result.stderr)
                except ValueError:
                    self.fail('CLI returned invalid structured output')
                if result.returncode:
                    code = body.get('error', {}).get('code', 'unknown')
                    self.fail('CLI operation failed: ' + code)
                return body

            try:
                login = command('auth', 'login', '--delete-notifications', '--callback-timeout', '600')
                connected = True
                self.assertEqual(login['account']['id'], expected, 'Unexpected test account')
                self.assertEqual(command('account', 'show')['id'], expected)
                key = 'integration-' + uuid.uuid4().hex
                message = 'Synthetic draft ' + uuid.uuid4().hex
                draft = command('notifications', 'create', '--idempotency-key', key, '--message', message)
                created = draft['id']
                self.assertIs(type(created), int)
                self.assertGreater(created, 0)
                self.assertEqual(command('notifications', 'show', str(created))['message'], message)
                repeated = command('notifications', 'create', '--idempotency-key', key, '--message', message)
                self.assertEqual(repeated['id'], created)
                command('notifications', 'list', '--limit', '1')
                command('notifications', 'archive', str(created))
                command('notifications', 'restore', str(created))
                if os.environ.get('UPTIBLE_TEST_LIFETIME_ACCESS') == 'yes':
                    command('leads', 'list', '--notification-id', str(created), '--limit', '1')
                    command('stats', 'show')
                    command('installation', 'show')
                deleted = command('notifications', 'delete', str(created), '--yes')
                self.assertEqual(deleted, {'deleted': True, 'id': created})
                created = None
            finally:
                try:
                    if created is not None:
                        cleanup = subprocess.run([*base, 'notifications', 'delete', str(created), '--yes'],
                                                 capture_output=True, timeout=30)
                        self.assertEqual(cleanup.returncode, 0, 'Owned draft cleanup requires attention')
                finally:
                    if connected:
                        logout = subprocess.run([*base, 'auth', 'logout'], capture_output=True, timeout=30)
                        self.assertEqual(logout.returncode, 0, 'Test grant cleanup requires attention')
