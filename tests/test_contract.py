"""Verify installed consumer requests against the pinned public OpenAPI contract."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from uptible_cli import Store

CONTRACTS = Path(__file__).resolve().parents[1] / 'docs/contracts'
MANIFEST = json.loads((CONTRACTS / 'manifest.json').read_text())
PINNED = json.loads((CONTRACTS / MANIFEST['snapshot']).read_text())
SCHEMA = json.loads(Path(os.environ['UPTIBLE_CONTRACT_SCHEMA']).read_text()) if os.environ.get('UPTIBLE_CONTRACT_SCHEMA') else PINNED
CASES = json.loads((CONTRACTS / 'cli-operations.json').read_text())


def validate(value, rule, document):
    if '$ref' in rule:
        target = document
        for part in rule['$ref'].removeprefix('#/').split('/'):
            target = target[part]
        return validate(value, target, document)
    if value is None and rule.get('nullable'):
        return
    for child in rule.get('allOf', []):
        validate(value, child, document)
    kind = rule.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    if kind:
        assert kind in types and type(value) is types[kind], f'Expected {kind}'
    if 'enum' in rule:
        assert value in rule['enum'], 'Unknown enum value'
    if kind == 'object':
        assert set(rule.get('required', [])) <= value.keys(), 'Missing required field'
        properties = rule.get('properties', {})
        if rule.get('additionalProperties') is False:
            assert value.keys() <= properties.keys(), 'Unexpected request field'
        for key, child in properties.items():
            if key in value:
                validate(value[key], child, document)
    if kind == 'array':
        for item in value:
            validate(item, rule['items'], document)
    if kind == 'string':
        assert len(value) >= rule.get('minLength', 0), 'String too short'
        assert len(value) <= rule.get('maxLength', len(value)), 'String too long'
        assert 'pattern' not in rule or re.search(rule['pattern'], value), 'Pattern mismatch'
    if kind == 'integer':
        assert value >= rule.get('minimum', value), 'Value below minimum'
        assert value <= rule.get('maximum', value), 'Value above maximum'


def operation(document, case):
    result = document['paths'][case['path']][case['method'].lower()]
    assert result['operationId'] == case['operation_id'], 'Operation identity changed'
    assert any(set(item['oauth']) <= set(case['scopes']) for item in result['security'] if 'oauth' in item), 'OAuth scopes no longer sufficient'
    return result


class ConsumerContract(unittest.TestCase):
    def test_pin_and_complete_operation_mapping(self):
        snapshot = CONTRACTS / MANIFEST['snapshot']
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), MANIFEST['sha256'])
        self.assertEqual(MANIFEST['sha256'], '69478e641f5fe22df2012abf3cec8db0089b8f083b228f26f99b093c1002868c')
        self.assertEqual((MANIFEST['api_major'], MANIFEST['minimum_server_contract'], MANIFEST['openapi']), (1, '1.1.0', '3.0.3'))
        self.assertEqual(PINNED['info']['version'], MANIFEST['minimum_server_contract'])
        expected = {value['operationId'] for item in PINNED['paths'].values() for key, value in item.items() if key in ('get', 'post', 'put', 'delete', 'patch')}
        self.assertEqual({case['operation_id'] for case in CASES}, expected)
        self.assertEqual(len(CASES), len(expected))
        for case in CASES:
            operation(SCHEMA, case)

    def test_installed_commands_send_contract_requests_and_accept_additions(self):
        failures = []
        observations = []
        current = {}

        class ContractServer(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_command(self):
                case = current['case']
                op = operation(SCHEMA, case)
                try:
                    actual = urllib.parse.urlsplit(self.path)
                    expected_path = case['path'].replace('{id}', '7').replace('{target}', 'activate')
                    assert (self.command, actual.path) == (case['method'], expected_path), 'Wrong operation'
                    assert self.headers.get('Authorization') == 'Bearer synthetic-consumer-token', 'Missing bearer'
                    query = urllib.parse.parse_qs(actual.query)
                    assert query == {key: [str(value)] for key, value in case['query'].items()}, 'Wrong query'
                    for parameter in op.get('parameters', []):
                        location, name, rule = parameter['in'], parameter['name'], parameter['schema']
                        values = query.get(name) if location == 'query' else [self.headers[name]] if name in self.headers else None
                        if location == 'path':
                            value = 7 if name == 'id' else 'activate'
                            validate(value, rule, SCHEMA)
                            continue
                        assert values or not parameter.get('required'), 'Missing required parameter'
                        if values:
                            value = int(values[0]) if rule.get('type') == 'integer' else values[0]
                            validate(value, rule, SCHEMA)
                    raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                    body = json.loads(raw) if raw and self.headers.get('Content-Type') == 'application/json' else None
                    assert body == case['body'], 'Wrong body'
                    if 'requestBody' in op:
                        assert self.headers.get('Content-Type') == 'application/json', 'Wrong content type'
                        validate(body, op['requestBody']['content']['application/json']['schema'], SCHEMA)
                    for name, value in case['headers'].items():
                        assert self.headers.get(name) == value, 'Wrong request header'
                    observations.append(case['operation_id'])
                except (AssertionError, KeyError, ValueError) as exc:
                    failures.append(str(exc))
                    self.send_response(422)
                    self.end_headers()
                    self.wfile.write(b'{"code":"validation_error"}')
                    return
                status, response = next((int(key), value) for key, value in op['responses'].items() if key.startswith('2'))
                media = response.get('content', {}).get('application/json')
                payload = copy.deepcopy(media['example']) if media else None
                if media:
                    validate(payload, media['schema'], SCHEMA)
                    pinned_op = operation(PINNED, case)
                    pinned_media = pinned_op['responses'][str(status)]['content']['application/json']
                    validate(payload, pinned_media['schema'], PINNED)
                    payload['consumer_extension'] = {'accepted': True}
                    validate(payload, media['schema'], SCHEMA)
                self.send_response(status)
                self.send_header('Uptible-API-Version', SCHEMA['info']['version'])
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                if payload is not None:
                    self.wfile.write(json.dumps(payload).encode())

            do_GET = do_POST = do_PUT = do_DELETE = handle_command

        server = ThreadingHTTPServer(('127.0.0.1', 0), ContractServer)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                issuer = 'http://127.0.0.1:' + str(server.server_port)
                credentials = Path(directory) / 'credentials'
                store = Store(issuer, 'synthetic-client', 'default', str(credentials))
                base = [sys.executable, '-m', 'uptible_cli', '--json', '--issuer', issuer, '--client-id', 'synthetic-client', '--credential-file', str(credentials)]
                for case in CASES:
                    with self.subTest(operation=case['operation_id']):
                        current['case'] = case
                        store.write(store.validate({'access_token': 'synthetic-consumer-token', 'refresh_token': 'synthetic-refresh', 'expires_in': 3600}))
                        result = subprocess.run([*base, *case['command']], capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stderr, '')
                        output = json.loads(result.stdout)
                        if case['method'] == 'GET' or case['command'][0] == 'events':
                            self.assertEqual(output['consumer_extension'], {'accepted': True})
                self.assertEqual(failures, [])
                self.assertEqual(observations, [case['operation_id'] for case in CASES])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_contract_controls_reject_incompatible_requests_and_security(self):
        case = next(case for case in CASES if case['command'][:2] == ['notifications', 'create'])
        rule = operation(PINNED, case)['requestBody']['content']['application/json']['schema']
        validate(case['body'], rule, PINNED)
        for change in ({'display_maps_only': True}, {'custom_delay_x_seconds': 4}, {'state': 'unknown'}):
            with self.subTest(change=change), self.assertRaises(AssertionError):
                validate({**case['body'], **change}, rule, PINNED)
        changed = copy.deepcopy(PINNED)
        del changed['paths'][case['path']]['post']
        with self.assertRaises(KeyError):
            operation(changed, case)
        changed = copy.deepcopy(PINNED)
        changed['paths'][case['path']]['post']['security'] = [{'oauth': ['new:required']}]
        with self.assertRaises(AssertionError):
            operation(changed, case)

    def test_real_oauth_request_covers_mapped_scopes(self):
        from test_cli import CLI, Server

        fixture = CLI('test_login_restart_refresh_account_and_logout')
        CLI.setUpClass()
        try:
            fixture.setUp()
            try:
                result, _ = fixture.run_cli('auth', 'login', '--events', '--billing', '--delete-leads', '--delete-notifications', '--email-change', '--browser-driver', str(fixture.driver))
                self.assertEqual(result.returncode, 0)
                actual = set(Server.authorization['scope'][0].split())
                required = {scope for case in CASES for scope in case['scopes']}
                self.assertEqual(actual, required)
            finally:
                fixture.doCleanups()
        finally:
            CLI.tearDownClass()

    def test_server_version_gate_runs_before_mutations(self):
        import io
        from unittest import mock
        from test_integration import require_server_contract
        from uptible_cli import OPENER

        for version in ('1.1.0', '1.2.0', '1.1.1', '', '1.0.9', '2.0.0', '1.1', '1.1.0-private'):
            response = io.BytesIO(b'')
            response.headers = {'Uptible-API-Version': version}
            with self.subTest(version=version), mock.patch.object(OPENER, 'open', return_value=response) as opened:
                if version in ('1.1.0', '1.2.0', '1.1.1'):
                    require_server_contract('https://dedicated.example.test')
                else:
                    with self.assertRaises(AssertionError):
                        require_server_contract('https://dedicated.example.test')
                self.assertEqual(opened.call_args.args[0].get_method(), 'GET')
                self.assertNotIn('Authorization', opened.call_args.args[0].headers)

    def test_notification_cursors_are_mutually_exclusive_before_storage(self):
        result = subprocess.run([sys.executable, '-m', 'uptible_cli', 'notifications', 'list', '--after', '2', '--before', '9'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('not allowed with argument', result.stderr)
