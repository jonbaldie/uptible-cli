#!/usr/bin/env python3
"""Build twice from committed source and verify the installed artifact."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WHEEL_FILES = {'uptible_cli/__init__.py', 'uptible_cli/__main__.py', 'uptible_cli/completion.py'}
DIST_INFO = re.compile(r'uptible_cli-[^/]+\.dist-info/(METADATA|WHEEL|entry_points.txt|top_level.txt|RECORD)')
SOURCE_FILES = {'PKG-INFO', 'README.md', 'pyproject.toml', 'setup.cfg',
                'src/uptible_cli/__init__.py', 'src/uptible_cli/__main__.py', 'src/uptible_cli/completion.py',
                'src/uptible_cli.egg-info/PKG-INFO', 'src/uptible_cli.egg-info/SOURCES.txt',
                'src/uptible_cli.egg-info/dependency_links.txt', 'src/uptible_cli.egg-info/entry_points.txt',
                'src/uptible_cli.egg-info/requires.txt', 'src/uptible_cli.egg-info/top_level.txt',
                'tests/test_cli.py', 'tests/test_completion.py', 'tests/test_integration.py', 'tests/test_contract.py',
                'MANIFEST.in', 'docs/contracts/README.md', 'docs/contracts/manifest.json',
                'docs/contracts/v1.1.0.json', 'docs/contracts/cli-operations.json'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, cwd, env):
    print('+', *map(str, args), flush=True)
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True)


def output(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def python_at(envdir):
    return envdir / 'bin/python'


def pip(python, *args, cwd, env):
    return run(python, '-m', 'pip', '--isolated', *args, cwd=cwd, env=env)


def install_inputs(python, requirements, report, cwd, env):
    pip(python, 'install', '--index-url', 'https://pypi.org/simple', '--no-cache-dir',
        '--only-binary=:all:', '--require-hashes', '--force-reinstall', '--report', report,
        '-r', requirements, cwd=cwd, env=env)
    data = json.loads(report.read_text())
    return sorted([{'name': item['metadata']['name'].lower().replace('_', '-'),
                    'version': item['metadata']['version'],
                    'sha256': item['download_info']['archive_info']['hashes']['sha256']}
                   for item in data['install']], key=lambda item: item['name'])


def check_wheel(path):
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
    files = set(names)
    if (len(names) != len(WHEEL_FILES) + 5 or len(files) != len(WHEEL_FILES) + 5 or not WHEEL_FILES <= files
            or len({name.split('/')[0] for name in files - WHEEL_FILES}) != 1
            or any(name not in WHEEL_FILES and not DIST_INFO.fullmatch(name) for name in files)):
        raise ValueError(f'Unexpected wheel contents: {sorted(files)}')


def normalize_sdist(path, epoch):
    with tarfile.open(path) as tar:
        members = tar.getmembers()
        if (len({m.name for m in members}) != len(members)
                or any(not (m.isfile() or m.isdir()) for m in members)):
            raise ValueError('Unexpected source archive member type or duplicate')
        roots = {m.name.split('/')[0] for m in members}
        files = {m.name.split('/', 1)[1] for m in members if m.isfile() and '/' in m.name}
        if (len(roots) != 1 or not files <= SOURCE_FILES
                or not {'pyproject.toml', 'src/uptible_cli/__init__.py', 'tests/test_contract.py',
                        'docs/contracts/manifest.json', 'docs/contracts/v1.1.0.json',
                        'docs/contracts/cli-operations.json', 'docs/contracts/README.md'} <= files
                or any('..' in Path(m.name).parts or m.name.startswith('/') for m in members)):
            raise ValueError(f'Unexpected source distribution contents: {sorted(files)}')
        contents = [(m.name, tar.extractfile(m).read() if m.isfile() else None) for m in members]
    with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=epoch) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            for name, data in sorted(contents):
                info = tarfile.TarInfo(name)
                info.mtime = epoch
                info.mode = 0o755 if data is None else 0o644
                if data is None:
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
                else:
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))


def build_once(tmp, revision, epoch, env, report_dir):
    tmp.mkdir()
    source = tmp / 'source'
    source.mkdir()
    archive = tmp / 'source.tar'
    with archive.open('wb') as f:
        subprocess.run(['git', 'archive', revision], cwd=ROOT, stdout=f, check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(source)
    envdir = tmp / 'build-env'
    venv.EnvBuilder(with_pip=True).create(envdir)
    python = python_at(envdir)
    resolution = install_inputs(python, source / 'scripts/verification-requirements.txt',
                                report_dir / 'build-install.json', tmp, env)
    distributions = tmp / 'dist'
    run(python, '-m', 'build', '--no-isolation', '--outdir', distributions, source, cwd=tmp, env=env)
    artifacts = sorted(distributions.iterdir())
    if len(artifacts) != 2 or len(list(distributions.glob('*.whl'))) != 1 or len(list(distributions.glob('*.tar.gz'))) != 1:
        raise ValueError('Expected one wheel and one source distribution')
    for path in artifacts:
        if path.suffix == '.whl':
            check_wheel(path)
            with zipfile.ZipFile(path) as wheel:
                if any(wheel.read(name) != (source / 'src' / name).read_bytes() for name in WHEEL_FILES):
                    raise ValueError('Wheel module differs from the committed source')
        else:
            normalize_sdist(path, epoch)
    (report_dir / 'artifacts.json').write_text(json.dumps({p.name: sha256(p) for p in artifacts}, indent=2) + '\n')
    return source, artifacts, resolution


def negative_controls(tmp, source, wheel, dest, env):
    report = json.loads((dest / 'build-a/build-install.json').read_text())
    item = next(item for item in report['install'] if item['metadata']['name'] == 'wheel')
    download = tmp / 'negative-input'
    download.mkdir()
    python = python_at(tmp / 'build-a/build-env')
    pip(python, 'download', '--index-url', 'https://pypi.org/simple', '--no-cache-dir',
        '--only-binary=:all:', '--require-hashes', '--no-deps', '--dest', download,
        '-r', source / 'scripts/verification-requirements.txt', cwd=tmp, env=env)
    dependency = next(download.glob('wheel-*.whl'))
    dependency.write_bytes(dependency.read_bytes() + b'altered-release-input')
    requirement = download / 'tampered.txt'
    requirement.write_text(f'{dependency.as_uri()} --hash=sha256:{item["download_info"]["archive_info"]["hashes"]["sha256"]}\n')
    result = subprocess.run([python, '-m', 'pip', '--isolated', 'install', '--no-deps',
                             '--force-reinstall', '--require-hashes', '-r', requirement],
                            cwd=tmp, env=env, text=True, capture_output=True)
    (dest / 'tampered-input.log').write_text(result.stdout + result.stderr)
    if result.returncode == 0 or 'DO NOT MATCH THE HASHES' not in result.stderr:
        raise ValueError('Tampered dependency did not fail its integrity check')
    unexpected = tmp / 'unexpected.whl'
    shutil.copyfile(wheel, unexpected)
    with zipfile.ZipFile(unexpected, 'a') as archive:
        archive.writestr('unexpected-private-fixture.txt', 'synthetic negative control')
    try:
        check_wheel(unexpected)
    except ValueError as exc:
        (dest / 'unexpected-artifact.log').write_text(str(exc) + '\n')
    else:
        raise ValueError('Unexpected artifact member was accepted')


def completion_controls(python, source, tmp, dest, env):
    module = Path(subprocess.check_output([python, '-c',
                  'import uptible_cli.completion as c; print(c.__file__)'], cwd=tmp, env=env, text=True).strip())
    original = module.read_text()
    mutations = {
        'omitted-completion-command': original.replace('    return sorted(prefix + value for value in values',
            '    values = [value for value in values if value != "notifications"]\n    return sorted(prefix + value for value in values'),
        'broken-completion-shell': original.replace('_uptible_complete() {', '_uptible_complete() ('),
    }
    try:
        for name, mutated in mutations.items():
            if mutated == original:
                raise ValueError('Completion negative control did not change the installed module')
            module.write_text(mutated)
            for cached in module.parent.glob('__pycache__/completion.*.pyc'):
                cached.unlink()
            result = subprocess.run([python, '-m', 'unittest', 'discover', '-s', source / 'tests',
                                     '-p', 'test_completion.py', '-v'], cwd=tmp, env=env, text=True, capture_output=True)
            (dest / (name + '.log')).write_text(result.stdout + result.stderr)
            if result.returncode == 0 or 'FAILED' not in result.stderr:
                raise ValueError(f'Completion negative control was not rejected: {name}')
    finally:
        module.write_text(original)
        for cached in module.parent.glob('__pycache__/completion.*.pyc'):
            cached.unlink()
    if module.read_text() != original:
        raise ValueError('Completion negative control did not restore the installed module')
    run(python, '-m', 'unittest', 'discover', '-s', source / 'tests', '-p', 'test_completion.py', '-v', cwd=tmp, env=env)


def contract_controls(python, source, tmp, dest, env):
    module = Path(subprocess.check_output([python, '-c',
                  'import uptible_cli; print(uptible_cli.__file__)'], cwd=tmp, env=env, text=True).strip())
    original = module.read_text()
    mutations = {
        'boolean-notification-wire-type': original.replace('int(payload["display_maps_only"])', 'bool(payload["display_maps_only"])'),
        'closed-event-receipt': original.replace('not isinstance(result.get("receipt"), str)', 'set(result) != {"receipt", "status"} or not isinstance(result.get("receipt"), str)'),
    }
    try:
        for name, mutated in mutations.items():
            if mutated == original:
                raise ValueError('Contract negative control did not change the installed module')
            module.write_text(mutated)
            for cached in module.parent.glob('__pycache__/__init__.*.pyc'):
                cached.unlink()
            result = subprocess.run([python, '-m', 'unittest', 'discover', '-s', source / 'tests',
                                     '-p', 'test_contract.py', '-v'], cwd=tmp, env=env, text=True, capture_output=True)
            (dest / (name + '.log')).write_text(result.stdout + result.stderr)
            if result.returncode == 0 or 'FAILED' not in result.stderr:
                raise ValueError(f'Contract negative control was not rejected: {name}')
    finally:
        module.write_text(original)
        for cached in module.parent.glob('__pycache__/__init__.*.pyc'):
            cached.unlink()
    if module.read_text() != original:
        raise ValueError('Contract negative control did not restore the installed module')
    run(python, '-m', 'unittest', 'discover', '-s', source / 'tests', '-p', 'test_contract.py', '-v', cwd=tmp, env=env)


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: python scripts/verify-artifact.py OUTPUT_DIRECTORY')
    if sys.implementation.name != 'cpython' or sys.platform not in {'darwin', 'linux'} or not (3, 11) <= sys.version_info[:2] <= (3, 14):
        sys.exit('Release verification supports CPython 3.11 through 3.14 on macOS and Linux')
    if output('git', 'status', '--porcelain', '--untracked-files=all'):
        sys.exit('Commit or remove all checkout changes before verification')
    if not all(shutil.which(shell) for shell in ('bash', 'zsh')):
        sys.exit('Artifact verification requires Bash and Zsh for completion checks')
    revision = output('git', 'rev-parse', 'HEAD')
    epoch = int(output('git', 'show', '-s', '--format=%ct', revision))
    dest = Path(sys.argv[1]).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        sys.exit('Output directory must be empty')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('PYTHON', 'PIP_', 'UPTIBLE_TEST_', 'UPTIBLE_INTEGRATION'))}
    env.update(SOURCE_DATE_EPOCH=str(epoch), PYTHONHASHSEED='0', BROWSER='/bin/false', PIP_CONFIG_FILE=os.devnull)
    with tempfile.TemporaryDirectory(prefix='uptible-verify-') as temporary:
        tmp = Path(temporary)
        builds = []
        started = []
        for name in ('build-a', 'build-b'):
            (dest / name).mkdir()
            started.append(time.time_ns())
            builds.append(build_once(tmp / name, revision, epoch, env, dest / name))
            if name == 'build-a':
                time.sleep(3)
        source, artifacts, resolution = builds[0]
        hashes = {p.name: sha256(p) for p in artifacts}
        if hashes != {p.name: sha256(p) for p in builds[1][1]} or resolution != builds[1][2]:
            raise ValueError('Independent builds or dependency resolutions differ')
        installed_resolutions = []
        for name, (build_source, build_artifacts, _) in zip(('build-a', 'build-b'), builds):
            envdir = tmp / name / 'installed'
            venv.EnvBuilder(with_pip=True).create(envdir)
            python = python_at(envdir)
            installed_resolutions.append(install_inputs(python, build_source / 'scripts/runtime-requirements.txt',
                                                        dest / name / 'runtime-install.json', tmp, env))
            wheel = next(p for p in build_artifacts if p.suffix == '.whl')
            requirement = tmp / name / 'artifact.txt'
            requirement.write_text(f'{wheel.as_uri()} --hash=sha256:{hashes[wheel.name]}\n')
            pip(python, 'install', '--no-deps', '--require-hashes', '-r', requirement, cwd=tmp, env=env)
            pip(python, 'check', cwd=tmp, env=env)
        if installed_resolutions[0] != installed_resolutions[1]:
            raise ValueError('Independent runtime dependency resolutions differ')
        python = python_at(tmp / 'build-a/installed')
        cli = python.parent / 'uptible'
        version = re.search(r'^version\s*=\s*"([^"]+)"', (source / 'pyproject.toml').read_text(), re.M).group(1)
        actual = subprocess.check_output([cli, '--version'], cwd=tmp, env=env, text=True).strip()
        if actual != f'uptible {version}':
            raise ValueError(f'Unexpected version: {actual}')
        run(cli, '--help', cwd=tmp, env=env)
        run(python, '-c', 'import importlib.metadata as m, uptible_cli; from pathlib import Path; import sys; assert m.version("uptible-cli") == sys.argv[1]; assert Path(uptible_cli.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); assert any(e.name == "uptible" and e.value == "uptible_cli:main" for e in m.entry_points(group="console_scripts"))', version, cwd=tmp, env=env)
        run(python, '-m', 'unittest', 'discover', '-s', source / 'tests', '-v', cwd=tmp, env=env)
        contract_controls(python, source, tmp, dest, env)
        completion_controls(python, source, tmp, dest, env)
        negative_controls(tmp, source, next(p for p in artifacts if p.suffix == '.whl'), dest, env)
        for path in artifacts:
            shutil.copyfile(path, dest / path.name)
        manifest = {'source_revision': revision, 'source_date_epoch': epoch, 'version': version,
                    'python': sys.version, 'platform': sys.platform, 'build_started_ns': started,
                    'artifacts': hashes, 'build_dependencies': resolution,
                    'runtime_dependencies': installed_resolutions[0],
                    'module_sha256': sha256(source / 'src/uptible_cli/__init__.py'),
                    'server_contract': json.loads((source / 'docs/contracts/manifest.json').read_text()),
                    'inputs': {name: sha256(source / 'scripts' / name) for name in
                               ('verification-requirements.txt', 'runtime-requirements.txt', 'homebrew-resources.json')},
                    'negative_controls': ['tampered dependency hash rejected', 'unexpected wheel member rejected',
                                          'omitted completion command rejected', 'broken generated shell rejected',
                                          'boolean notification wire type rejected', 'closed event receipt rejected']}

        (dest / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (dest / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes.items())))
        (dest / 'SOURCE_REVISION').write_text(revision + '\n')
        print('Verified source', revision, '\n' + (dest / 'SHA256SUMS').read_text())


if __name__ == '__main__':
    main()
