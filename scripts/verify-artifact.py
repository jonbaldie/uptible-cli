#!/usr/bin/env python3
"""Build and verify distributions from the committed checkout."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None, env=None):
    print('+', *map(str, args), flush=True)
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True)


def output(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: python scripts/verify-artifact.py OUTPUT_DIRECTORY')
    if output('git', 'status', '--porcelain', '--untracked-files=all'):
        sys.exit('Commit or remove all checkout changes before verification')
    revision = output('git', 'rev-parse', 'HEAD')
    dest = Path(sys.argv[1]).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        sys.exit('Output directory must be empty')
    with tempfile.TemporaryDirectory(prefix='uptible-verify-') as tmp:
        tmp = Path(tmp)
        source = tmp / 'source'
        source.mkdir()
        archive = tmp / 'source.tar'
        with archive.open('wb') as f:
            subprocess.run(['git', 'archive', revision], cwd=ROOT, stdout=f, check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(source)
        envdir = tmp / 'venv'
        venv.EnvBuilder(with_pip=True).create(envdir)
        python = envdir / 'bin' / 'python'
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        run(python, '-m', 'pip', 'install', '-r', source / 'scripts/verification-requirements.txt', cwd=tmp, env=env)
        run(python, '-m', 'build', '--no-isolation', '--outdir', dest, source, cwd=tmp, env=env)
        wheels = list(dest.glob('*.whl'))
        sdists = list(dest.glob('*.tar.gz'))
        if len(wheels) != 1 or len(sdists) != 1:
            sys.exit('Expected one wheel and one source distribution')
        with zipfile.ZipFile(wheels[0]) as wheel:
            files = set(wheel.namelist())
        wheel_allowed = {'uptible_cli/__init__.py', 'uptible_cli/__main__.py'}
        dist_info = re.compile(r'uptible_cli-[^/]+\.dist-info/(METADATA|WHEEL|entry_points.txt|top_level.txt|RECORD)')
        if any(name not in wheel_allowed and not dist_info.fullmatch(name) for name in files) or not wheel_allowed <= files:
            sys.exit(f'Unexpected wheel contents: {sorted(files)}')
        with tarfile.open(sdists[0]) as tar:
            members = tar.getmembers()
            files = {m.name.split('/', 1)[1] for m in members if m.isfile() and '/' in m.name}
            if any(not (m.isfile() or m.isdir()) for m in members):
                sys.exit('Unexpected source archive member type')
        allowed = {'PKG-INFO', 'README.md', 'pyproject.toml', 'setup.cfg',
                   'src/uptible_cli/__init__.py', 'src/uptible_cli/__main__.py',
                   'src/uptible_cli.egg-info/PKG-INFO', 'src/uptible_cli.egg-info/SOURCES.txt',
                   'src/uptible_cli.egg-info/dependency_links.txt', 'src/uptible_cli.egg-info/entry_points.txt',
                   'src/uptible_cli.egg-info/requires.txt', 'src/uptible_cli.egg-info/top_level.txt',
                   'tests/test_cli.py'}
        if not files <= allowed or not {'pyproject.toml', 'src/uptible_cli/__init__.py'} <= files:
            sys.exit(f'Unexpected source distribution contents: {sorted(files)}')
        envdir = tmp / 'installed'
        venv.EnvBuilder(with_pip=True).create(envdir)
        python = envdir / 'bin' / 'python'
        env['BROWSER'] = '/bin/false'
        run(python, '-m', 'pip', 'install', wheels[0], cwd=tmp, env=env)
        cli = envdir / 'bin' / 'uptible'
        version = re.search(r'^version\s*=\s*"([^"]+)"', (source / 'pyproject.toml').read_text(), re.M).group(1)
        actual = subprocess.check_output([cli, '--version'], cwd=tmp, env=env, text=True).strip()
        if actual != f'uptible {version}':
            sys.exit(f'Unexpected version: {actual}')
        run(cli, '--help', cwd=tmp, env=env)
        run(python, '-c', 'import importlib.metadata as m, uptible_cli; from pathlib import Path; import sys; assert m.version("uptible-cli") == sys.argv[1]; assert Path(uptible_cli.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); assert any(e.name == "uptible" and e.value == "uptible_cli:main" for e in m.entry_points(group="console_scripts"))', version, cwd=tmp, env=env)
        run(python, '-m', 'unittest', 'discover', '-s', source / 'tests', '-v', cwd=tmp, env=env)
        lines = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}' for p in sorted(wheels + sdists)]
        (dest / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
        (dest / 'SOURCE_REVISION').write_text(revision + '\n')
        print('Verified source', revision, '\n' + '\n'.join(lines))


if __name__ == '__main__':
    main()
