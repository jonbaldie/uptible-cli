#!/usr/bin/env python3
"""Render a formula after checking a verified source archive and its manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def resource(item, indent):
    pad = ' ' * indent
    return f'{pad}resource "{item["name"]}" do\n{pad}  url "{item["url"]}"\n{pad}  sha256 "{item["sha256"]}"\n{pad}end\n'


def render(version, url, digest, module_digest, resources):
    common = '\n'.join(resource(item, 2) for item in resources if item['platform'] == 'all')
    linux = '\n'.join(resource(item, 4) for item in resources if item['platform'] == 'linux')
    versions = {item['name']: item['version'] for item in resources if item['platform'] == 'all'}
    return f'''class Uptible < Formula
  include Language::Python::Virtualenv

  desc "Connect and manage an Uptible account from the terminal"
  homepage "https://github.com/jonbaldie/uptible-cli"
  url "{url}"
  sha256 "{digest}"

  depends_on "python@3.14"

  on_linux do
    depends_on "cryptography"

{linux}  end

{common}
  def install
    virtualenv_install_with_resources
  end

  test do
    assert_equal "uptible #{{version}}", shell_output("#{{bin}}/uptible --version").strip
    system libexec/"bin/python", "-c", <<~PYTHON
      import hashlib
      import importlib.metadata as metadata
      from pathlib import Path
      import uptible_cli
      assert hashlib.sha256(Path(uptible_cli.__file__).read_bytes()).hexdigest() == "{module_digest}"
      assert metadata.version("uptible-cli") == "{version}"
      for name, expected in {json.dumps(versions, sort_keys=True)}.items():
          assert metadata.version(name) == expected, name
    PYTHON
  end
end
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--sdist', required=True, type=Path)
    parser.add_argument('--manifest', type=Path, help='Defaults to BUILD_MANIFEST.json beside the sdist')
    parser.add_argument('--url')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('version must look like 1.2.3')
    expected = f'uptible_cli-{args.version}.tar.gz'
    if args.sdist.name != expected:
        parser.error(f'sdist must be named {expected}')
    manifest = json.loads((args.manifest or args.sdist.parent / 'BUILD_MANIFEST.json').read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    digest = hashlib.sha256(args.sdist.read_bytes()).hexdigest()
    if manifest['version'] != args.version or manifest['source_revision'] != revision or manifest['artifacts'].get(expected) != digest:
        parser.error('source archive does not match the verified version, revision and digest')
    inputs = (ROOT / 'scripts/homebrew-resources.json').read_bytes()
    if hashlib.sha256(inputs).hexdigest() != manifest['inputs']['homebrew-resources.json']:
        parser.error('formula resources differ from the verified inputs')
    with tarfile.open(args.sdist) as archive:
        member = archive.extractfile(f'uptible_cli-{args.version}/src/uptible_cli/__init__.py')
        if member is None or hashlib.sha256(member.read()).hexdigest() != manifest['module_sha256']:
            parser.error('source module differs from the verified module')
    resources = json.loads(inputs)
    requirements = {re.sub(r'[-_.]+', '-', match[1].lower()): match[2]
                    for match in re.finditer(r'^([A-Za-z0-9_.-]+)==([^\s;]+)',
                                             (ROOT / 'scripts/runtime-requirements.txt').read_text(), re.M)}
    for item in resources:
        if requirements.get(item['name']) != item['version']:
            parser.error(f'resource is not in the runtime inputs: {item["name"]}')
    url = args.url or f'https://github.com/jonbaldie/uptible-cli/releases/download/v{args.version}/{expected}'
    if not re.fullmatch(r'(https|file)://[A-Za-z0-9_./:%+~@?=&-]+', url):
        parser.error('URL must be an HTTPS or file URL without quotes, spaces or interpolation')
    print(render(args.version, url, digest, manifest['module_sha256'], resources), end='')


if __name__ == '__main__':
    main()
