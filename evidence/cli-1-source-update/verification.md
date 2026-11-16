# Source checkout update verification

The README change documents updating a CLI installed from a source checkout. A fresh checkout copy on macOS with CPython 3.14 ran these commands:

```text
python3.14 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/uptible --version
uptible 0.1.0
.venv/bin/python -m pip install --upgrade .
.venv/bin/uptible --version
uptible 0.1.0
```

The imported module came from the virtual environment's site-packages. This check confirms install and reinstall commands execute. It does not distinguish checkout revisions with the same package version.

Base CLI revision `7adbdbaa4aa64284aee5fe692d34ed7d66e78164` independently passed the release artifact verifier on macOS with CPython 3.14. Its two builds matched and the installed-wheel suite and negative controls passed. The source distribution and wheel passed checksum verification. Gitleaks 8.30.0 scanned the contents of both extracted archives and reported zero findings. Automated scanning does not guarantee absence of secrets.

The release candidate and artifacts in this check are local. No release was published. The documentation-only PR head requires its own CI and review.
