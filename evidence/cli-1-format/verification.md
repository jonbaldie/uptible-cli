# CLI format and contract mapping verification

Base: `474d8c30083b4d8e9c756ca7ff5048ab562f9643`. Proposed head: `527087d3f016f444975bee87022e5af6da1cc74d`.

`python3 scripts/check-format.py` passed on the head. A temporary trailing space inserted in a tracked Python file caused the checker to exit nonzero with a trailing-whitespace diagnostic; the original bytes were restored and the checker passed again. The check covers Python indentation consistency, trailing whitespace and final newline, not all Python style conventions.

The 1.3.0 candidate describes `GET /api/v1/me` as equivalent to `GET /api/v1/account`. The existing `account show` uses the latter. The candidate also adds a browser-session alternative and optional lead-view filter; the documentation records their disposition. This is a source-contract inspection, not proof of deployed compatibility.

The change is textual and affects CI only; there is no user-interface screenshot.

Python 3.14 artifact verifier passed on both exact commits. Each built twice and compared artifacts, installed the wheel, ran 108 tests (one opt-in real-account test skipped), checked consumer compatibility, and ran packaging and behavior negative controls. The two resulting wheel/sdist SHA-256 pairs were:

```text
base wheel  4d22fc8befc0279fbdba02f83771b74a22b94502fc00a6ccca3965e599883321
base sdist  b6de96ff3c186a63f9b108fbd5017c3a56c1ad637e353b10f96e4bdd83577bb1
head wheel  8fd3ac6a9a53fe9567667641f96ca92223ac3516077b8bbd9a6c81ca352f63ab
head sdist  0b8ae0f853f8bbe5d9c543eae7f9f8207393629781c0810b8a71edfa0b063d24
```

Gitleaks scanned the extracted wheel and sdist for each commit and reported no leaks. These are candidate artifacts; no release was published.
