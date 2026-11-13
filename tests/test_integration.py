"""Opt-in checks against an explicitly provisioned, disposable test account."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.parse
import uuid


class IntegrationTargetGuard(unittest.TestCase):
    def run_target(self, issuer):
        with mock.patch.dict(os.environ, {
            'UPTIBLE_TEST_ISSUER': issuer,
            'UPTIBLE_TEST_CLIENT_ID': 'synthetic-client',
            'UPTIBLE_TEST_ACCOUNT_ID': '1',
        }, clear=True):
            ActualAccount('test_browser_login_and_owned_draft').test_browser_login_and_owned_draft()

    def test_production_aliases_never_start_login(self):
        for issuer in (
            'https://uptible.com', 'https://www.uptible.com', 'https://UPTIBLE.COM',
            'https://uptible.com.', 'https://www.uptible.com.',
            'https://ｕｐｔｉｂｌｅ.com', 'https://uptible。com',
        ):
            with self.subTest(issuer=issuer), mock.patch.object(
                subprocess, 'run', side_effect=AssertionError('Login must not start'),
            ) as run:
                with self.assertRaises(AssertionError):
                    self.run_target(issuer)
                run.assert_not_called()

    def test_malformed_hostname_never_starts_login(self):
        with mock.patch.object(subprocess, 'run', side_effect=AssertionError('Login must not start')) as run:
            with self.assertRaises(AssertionError):
                self.run_target('https://invalid..test')
            run.assert_not_called()

    def test_dedicated_target_reaches_login(self):
        for issuer in ('http://127.0.0.1:8765', 'https://dedicated.example.test'):
            with self.subTest(issuer=issuer), mock.patch.object(
                subprocess, 'run', side_effect=RuntimeError('controlled login boundary'),
            ) as run:
                with self.assertRaisesRegex(RuntimeError, 'controlled login boundary'):
                    self.run_target(issuer)
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0][-5:], [
                    'auth', 'login', '--delete-notifications', '--callback-timeout', '600',
                ])


@unittest.skipUnless(os.environ.get('UPTIBLE_INTEGRATION') == 'dedicated-test-account',
                     'requires an explicitly provisioned integration account')
class ActualAccount(unittest.TestCase):
    def test_browser_login_and_owned_draft(self):
        from uptible_cli import issuer_url

        issuer = issuer_url(os.environ['UPTIBLE_TEST_ISSUER'])
        try:
            hostname = urllib.parse.urlsplit(issuer).hostname.encode('idna').decode('ascii').rstrip('.').lower()
        except UnicodeError:
            self.fail('Use a valid isolated test hostname')
        if not hostname or hostname in ('uptible.com', 'www.uptible.com'):
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
