#!/usr/bin/env python3
"""Check the Python source formatting conventions used by this repository."""
from pathlib import Path
import subprocess
import sys
import tabnanny
import tokenize

paths = subprocess.check_output(['git', 'ls-files', '-z', '--', '*.py']).decode().split('\0')
errors = []
for name in filter(None, paths):
    data = Path(name).read_bytes()
    if not data.endswith(b'\n') or data.endswith(b'\n\n'):
        errors.append(f'{name}: expected exactly one final newline')
    for number, line in enumerate(data.splitlines(), 1):
        if line.rstrip(b' \t') != line:
            errors.append(f'{name}:{number}: trailing whitespace')
    try:
        with Path(name).open() as source:
            tabnanny.process_tokens(tokenize.generate_tokens(source.readline))
    except (tabnanny.NannyNag, tokenize.TokenError, IndentationError, SyntaxError) as error:
        errors.append(f'{name}: inconsistent indentation: {error}')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    sys.exit(1)
print('Python formatting checks passed')
