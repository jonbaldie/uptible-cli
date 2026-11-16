# CLI format and contract mapping verification

Base: `474d8c30083b4d8e9c756ca7ff5048ab562f9643`. Proposed head: `527087d3f016f444975bee87022e5af6da1cc74d`.

`python3 scripts/check-format.py` passed on the head. A temporary trailing space inserted in a tracked Python file caused the checker to exit nonzero with a trailing-whitespace diagnostic; the original bytes were restored and the checker passed again. The check covers Python indentation consistency, trailing whitespace and final newline, not all Python style conventions.

The 1.3.0 candidate describes `GET /api/v1/me` as equivalent to `GET /api/v1/account`. The existing `account show` uses the latter. The candidate also adds a browser-session alternative and optional lead-view filter; the documentation records their disposition. This is a source-contract inspection, not proof of deployed compatibility.

The change is textual and affects CI only; there is no user-interface screenshot.
