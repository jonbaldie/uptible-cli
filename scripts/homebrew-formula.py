#!/usr/bin/env python3
"""Render the Homebrew formula for a verified source distribution.

Usage: python scripts/homebrew-formula.py --version 0.1.0 --sdist PATH [--url URL] > uptible.rb

The default URL is the GitHub release asset for that version. Pass --url only to
install a local build, for example file:///path/to/uptible_cli-0.1.0.tar.gz.
"""
import argparse
import hashlib
from pathlib import Path
import re

# Runtime dependencies resolved for keyring>=25,<26 and filelock>=3.16,<4 on Python 3.14.
# On Linux, cryptography comes from Homebrew's formula, as in homebrew-core's keyring users.
RESOURCES = [
    ('filelock', 'https://files.pythonhosted.org/packages/0f/59/e19834834cb01a32febfbb0f8a23a9088088f5d45991824ff2bc3b5e8acb/filelock-3.32.7.tar.gz', '37b8a3d9811b0f9aef7e5ec5c71bb320de52df51e6ca9bcd6f5ad81187660da7'),
    ('jaraco-classes', 'https://files.pythonhosted.org/packages/06/c0/ed4a27bc5571b99e3cff68f8a9fa5b56ff7df1c2251cc715a652ddd26402/jaraco.classes-3.4.0.tar.gz', '47a024b51d0239c0dd8c8540c6c7f484be3b8fcf0b2d85c13825780d3b3f3acd'),
    ('jaraco-context', 'https://files.pythonhosted.org/packages/af/50/4763cd07e722bb6285316d390a164bc7e479db9d90daa769f22578f698b4/jaraco_context-6.1.2.tar.gz', 'f1a6c9d391e661cc5b8d39861ff077a7dc24dc23833ccee564b234b81c82dfe3'),
    ('jaraco-functools', 'https://files.pythonhosted.org/packages/6c/1f/c23395957d41ccf27c4e535c3d334c4051e5395b3752057ba4cbaec35c56/jaraco_functools-4.6.0.tar.gz', '880c577ec9720b3a052d5bc611fb9f2269b3d87902ef42440df443b88e443280'),
    ('keyring', 'https://files.pythonhosted.org/packages/43/4b/674af6ef2f97d56f0ab5153bf0bfa28ccb6c3ed4d1babf4305449668807b/keyring-25.7.0.tar.gz', 'fe01bd85eb3f8fb3dd0405defdeac9a5b4f6f0439edbb3149577f244a2e8245b'),
    ('more-itertools', 'https://files.pythonhosted.org/packages/52/b8/c63995bebbb9ac9c059350e0fb8c82c2420c85aeca7d34e40aecf3df9281/more_itertools-11.2.1.tar.gz', 'cbf08fd0af284dc69718b9b76a8e6203df624d70209ea511e4219d350c856f63'),
]
LINUX_RESOURCES = [
    ('jeepney', 'https://files.pythonhosted.org/packages/7b/6f/357efd7602486741aa73ffc0617fb310a29b588ed0fd69c2399acbb85b0c/jeepney-0.9.0.tar.gz', 'cf0e9e845622b81e4a28df94c40345400256ec608d0e55bb8a3feaa9163f5732'),
    ('secretstorage', 'https://files.pythonhosted.org/packages/1c/03/e834bcd866f2f8a49a85eaff47340affa3bfa391ee9912a952a1faa68c7b/secretstorage-3.5.0.tar.gz', 'f04b8e4689cbce351744d5537bf6b1329c6fc68f91fa666f60a380edddcd11be'),
]


def resource(name, url, sha256, indent):
    pad = ' ' * indent
    return f'{pad}resource "{name}" do\n{pad}  url "{url}"\n{pad}  sha256 "{sha256}"\n{pad}end\n'


def render(version, url, sha256):
    common = '\n'.join(resource(*r, 2) for r in RESOURCES)
    linux = '\n'.join(resource(*r, 4) for r in LINUX_RESOURCES)
    return f'''class Uptible < Formula
  include Language::Python::Virtualenv

  desc "Connect and manage an Uptible account from the terminal"
  homepage "https://github.com/jonbaldie/uptible-cli"
  url "{url}"
  sha256 "{sha256}"

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
  end
end
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--version', required=True)
    parser.add_argument('--sdist', required=True, type=Path)
    parser.add_argument('--url')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('version must look like 1.2.3')
    expected = f'uptible_cli-{args.version}.tar.gz'
    if args.sdist.name != expected:
        parser.error(f'sdist must be named {expected}')
    url = args.url or f'https://github.com/jonbaldie/uptible-cli/releases/download/v{args.version}/{expected}'
    print(render(args.version, url, hashlib.sha256(args.sdist.read_bytes()).hexdigest()), end='')


if __name__ == '__main__':
    main()
