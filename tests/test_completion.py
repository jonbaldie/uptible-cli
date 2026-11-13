import argparse
import contextlib
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import uptible_cli
from uptible_cli.completion import bash_words, candidates


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.parser = uptible_cli.build_parser()

    def complete(self, *words):
        return candidates(self.parser, words[:-1], words[-1])

    def test_current_commands_and_options(self):
        self.assertEqual(self.complete(''), ['account', 'auth', 'billing', 'completion', 'events', 'installation', 'leads', 'notifications', 'stats'])
        self.assertEqual(self.complete('notifications', ''), ['activate', 'activity', 'archive', 'create', 'deactivate', 'delete', 'edit', 'list', 'restore', 'show'])
        self.assertEqual(self.complete('auth', ''), ['login', 'logout', 'status'])
        self.assertIn('--delete-notifications', self.complete('auth', 'login', '--delete'))
        self.assertEqual(self.complete('events', 'capture', '--e'), ['--email', '--event-id'])
        self.assertEqual(self.complete('billing', 'status', '--c'), ['--claim-cursor', '--cursor'])
        self.assertEqual(self.complete('notifications', 'edit', '12', '--no-'), ['--no-display-maps-only'])
        self.assertEqual(self.complete('--j', 'leads', 'delete', '12', '--y'), ['--yes'])
        self.assertEqual(self.complete('--profile=synthetic', 'stats', ''), ['show'])
        self.assertEqual(self.complete('--issuer', 'https://example.invalid', '--client-id', 'synthetic', 'account', ''), ['show'])
        self.assertEqual(self.complete('auth', 'login', '--issuer'), [])
        self.assertEqual(self.complete('completion', ''), ['bash', 'zsh'])
        self.assertEqual(self.complete('-'), ['--client-id', '--credential-file', '--help', '--issuer', '--json', '--profile', '--version', '-h'])

    def test_every_parser_path_and_option(self):
        def visit(parser, path):
            expected = sorted(parser._option_string_actions)
            self.assertEqual(self.complete(*path, '-'), expected)
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    self.assertEqual(self.complete(*path, ''), sorted(action.choices))
                    for name, child in action.choices.items():
                        visit(child, [*path, name])
                elif action.option_strings and action.nargs != 0:
                    expected = sorted(map(str, action.choices)) if action.choices is not None else []
                    for option in action.option_strings:
                        self.assertEqual(self.complete(*path, option, ''), expected)
        visit(self.parser, [])

    def test_values_and_safe_failures(self):
        self.assertEqual(self.complete('leads', 'list', '--limit', '2'), ['2', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29'])
        self.assertEqual(self.complete('leads', 'list', '--limit=99'), ['--limit=99'])
        self.assertEqual(self.complete('leads', 'list', '--limit', '20', '--c'), ['--cursor'])
        for words in [('auth', 'login', '--browser-driver', ''), ('--credential-file', ''),
                      ('events', 'capture', '1', '--email', ''), ('notifications', 'create', '--message', '--'),
                      ('unknown', ''), ('auth', 'unknown', ''), ('--bad', ''), ('--json=yes', ''),
                      ('leads', 'list', '--limit', 'invalid', ''), ('leads', 'show', '12', '--', '--'),
                      ('--help', ''), ('--version', ''), ('--', ''), ('--', 'auth', ''), ('$(touch marker)', ''), ('leads', 'show', '')]:
            with self.subTest(words=words):
                self.assertEqual(self.complete(*words), [])

    def test_bash_partial_words(self):
        for line, expected in [
                ("uptible --profile 'synthetic name' auth ", ['uptible', '--profile', 'synthetic name', 'auth', '']),
                ('uptible --profile : auth ', ['uptible', '--profile', ':', 'auth', '']),
                ('uptible --profile = auth ', ['uptible', '--profile', '=', 'auth', '']),
                ('uptible --profile "unfinished ', ['uptible', '--profile', 'unfinished ']),
                ('uptible --profile x\\ ', ['uptible', '--profile', 'x ']),
                ('uptible --profile x\\', ['uptible', '--profile', 'x']),
                ('uptible --profile café auth ', ['uptible', '--profile', 'café', 'auth', '']),
                ('uptible no trailing', ['uptible', 'no'])]:
            point = len(line.encode()) if line != 'uptible no trailing' else len('uptible no')
            self.assertEqual(bash_words(line, point), expected)
        for line, point in [('', 0), ('uptible', 20), ('uptible ', -1), ('x' * 32769, 1)]:
            with self.assertRaises(ValueError):
                bash_words(line, point)

    def test_parser_aliases_and_fixed_choices(self):
        parser = argparse.ArgumentParser()
        parser.add_subparsers().add_parser('example', aliases=['ex']).add_argument('--format', choices=['json', 'text'])
        self.assertEqual(candidates(parser, [], 'ex'), ['ex', 'example'])
        self.assertEqual(candidates(parser, ['ex', '--format'], 'j'), ['json'])
        self.assertEqual(candidates(parser, ['ex'], '--format=t'), ['--format=text'])

    def test_local_entry_points_do_not_dispatch(self):
        for args in [['completion', 'bash'], ['completion', 'zsh'], ['--_complete', '1', 'uptible', ''], ['--_complete-bash', '8', 'uptible '],
                     ['--_complete', '4', 'uptible', 'auth', 'logout', '--local', '']]:
            with self.subTest(args=args), patch.object(sys, 'argv', ['uptible', *args]), \
                    patch.object(uptible_cli, 'run', side_effect=AssertionError('dispatch')), \
                    patch.object(uptible_cli, 'Store', side_effect=AssertionError('credential store')), \
                    patch.object(uptible_cli, 'request', side_effect=AssertionError('network')), \
                    patch.object(uptible_cli.webbrowser, 'open', side_effect=AssertionError('browser')), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(uptible_cli.main(), 0)
        for args in [[], ['x'], ['-1', 'uptible', ''], ['9', 'uptible', ''], ['0', 'uptible'],
                     ['1', 'uptible', 'x' * 32769]]:
            with patch.object(sys, 'argv', ['uptible', '--_complete', *args]), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(uptible_cli.main(), 2)
                self.assertEqual(out.getvalue(), '')

    def test_real_shell_adapters(self):
        cases = [(['uptible', 'no'], ['notifications']),
                 (['uptible', 'auth', 'lo'], ['login', 'logout']),
                 (['uptible', 'notifications', 'edit', '12', '--no-'], ['--no-display-maps-only']),
                 (['uptible', 'events', 'capture', '1', '--e'], ['--email', '--event-id']),
                 (['uptible', 'billing', 'status', '--c'], ['--claim-cursor', '--cursor']),
                 (['uptible', 'leads', 'list', '--limit', '99'], ['99']),
                 (['uptible', '--profile', 'synthetic profile', 'stats', ''], ['show']),
                 (['uptible', '--profile', ':', 'auth', ''], ['login', 'logout', 'status']),
                 (['uptible', '--profile', '=', 'auth', ''], ['login', 'logout', 'status']),
                 (['uptible', 'auth', 'login', '--browser-driver', ''], []),
                 (['uptible', 'bad', ''], []),
                 (['uptible', 'notifications', 'create', '--message', '$(touch marker)', '--no-'], ['--no-display-maps-only'])]
        for shell in ('bash', 'zsh'):
            if not shutil.which(shell):
                self.skipTest(f'{shell} is unavailable')
            with tempfile.TemporaryDirectory() as temporary:
                tmp = Path(temporary)
                cli = tmp / 'uptible'
                cli.write_text('#!' + sys.executable + '\n' + '''import sys
import socket
import keyring
import uptible_cli

def forbidden(*args, **kwargs):
    raise AssertionError("Completion attempted I/O or dispatch")

socket.socket.connect = forbidden
socket.socket.bind = forbidden
keyring.get_keyring = forbidden
uptible_cli.Store = forbidden
uptible_cli.run = forbidden
uptible_cli.request = forbidden
uptible_cli.webbrowser.open = forbidden
sys.exit(uptible_cli.main())
''')
                cli.chmod(0o755)
                script = tmp / 'completion'
                generated = subprocess.run([str(cli), 'completion', shell], text=True, capture_output=True, check=True)
                script.write_text(generated.stdout)
                env = dict(os.environ, PATH=str(tmp) + os.pathsep + os.environ['PATH'])
                if shell == 'zsh':
                    untrusted = tmp / 'untrusted'
                    untrusted.mkdir()
                    untrusted.chmod(0o777)
                    (untrusted / '_uptible_untrusted').write_text('#compdef uptible-untrusted\nreturn 99\n')
                    paths = subprocess.check_output([shell, '-fc', 'print -rl -- $fpath'], text=True).splitlines()
                    env['FPATH'] = os.pathsep.join([str(untrusted), *paths])
                    audit = subprocess.run([shell, '-fc', 'autoload -Uz compaudit; compaudit'],
                                           text=True, capture_output=True, env=env, timeout=20)
                    self.assertNotEqual(audit.returncode, 0)
                    self.assertIn(str(untrusted), audit.stdout.splitlines())
                for words, expected in cases:
                    with self.subTest(shell=shell, words=words):
                        result = self.drive_shell(shell, script, words, tmp, env)
                        self.assertEqual(result, expected)
                if shell == 'bash':
                    self.assertEqual(self.drive_shell(shell, script, ['uptible', 'leads', 'list', '--limit', '=', '99'], tmp, env, 'uptible leads list --limit=99'), ['99'])
                    self.assertEqual(self.drive_shell(shell, script, ['uptible', '--issuer', 'https', ':', '//example.invalid', '--client-id', 'synthetic', 'auth', ''], tmp, env, 'uptible --issuer https://example.invalid --client-id synthetic auth '), ['login', 'logout', 'status'])
                self.assertFalse((tmp / 'marker').exists())

    def drive_shell(self, shell, script, words, cwd, env, raw_line=None):
        line = raw_line or shlex.join(words)
        array = ' '.join(map(shlex.quote, words))
        if shell == 'bash':
            command = f'source "$1"\n[[ $(complete -p uptible) == *"_uptible_complete"* ]] || exit 7\nCOMP_WORDS=({array})\nCOMP_CWORD={len(words) - 1}\nCOMP_LINE={shlex.quote(line)}\nCOMP_POINT={len(line.encode())}\n_uptible_complete\nprintf "%s\\n" "${{COMPREPLY[@]}}"'
        else:
            command = f'autoload -Uz compinit\ncompinit -D\n[[ -z $_comps[uptible-untrusted] ]] || exit 8\nsource "$1"\n[[ $_comps[uptible] == _uptible_complete ]] || exit 7\ncompadd() {{ shift; printf "%s\\n" "$@"; }}\nwords=({array})\nCURRENT={len(words)}\n_uptible_complete'
        result = subprocess.run([shell, '-f' if shell == 'zsh' else '--noprofile', '-c', command, 'test', str(script)],
                                text=True, capture_output=True, cwd=cwd, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout.splitlines() if result.stdout.strip() else []


if __name__ == '__main__':
    unittest.main()
