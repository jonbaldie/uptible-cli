# CLI artifact readiness handover

Goal: help the maintainer decide whether Uptible and its CLI are ready for production launch. This unit prepares reproducible CLI artifacts and an authenticated local installation rehearsal. It performs no publication, production account login, or full-program issue closure.

Frozen candidate: `61a24e1726b04e64734d457bb543c898dd9c331c` on `fix/reproducible-cli-artifacts`, based on current remote main `0c068965e01a3c38bcb4388e169fb806eeeb4cf8`. The worktree is clean. Source and all existing80 tests are byte-identical to main. Full patch is `DIFF.patch`. Root owns forge writes, independent review, evidence upload, merge, and issue disposition.

## Result

Portable platform-marked wheel hashes now cover build and runtime inputs. The verifier archives committed source, takes timestamps from that commit, constructs two independent build environments at different wall-clock times, compares wheel/sdist bytes and selected dependency hashes, installs both runtime environments, authenticates installed provenance and runs80 installed tests outside the checkout. Retained negative controls require altered dependency bytes and an unexpected wheel member to fail. Formula rendering authenticates the source archive and resource manifest, and the formula test authenticates the installed CLI module and common dependency versions.

Python minimum is now3.11, with parent-approved `filelock>=4.2.10,<5`. All21 pinned versions have no known advisories in the retained PyPI/pip-audit snapshots. This does not establish absence of undisclosed vulnerabilities. The existing credential critical section is unchanged; shared-directory upstream advisory findings are not13 separately exploitable CLI bugs. Initial artifacts and scans are retained but superseded by the `final-*` evidence.

## Verified matrix

| Surface | Actual environment | Result |
| --- | --- | --- |
| Artifact verifier | macOS26.6.2 arm64, CPython3.14.5 | Two builds and two runtime installs; identical artifacts/dependency resolutions;80 tests pass; both negative controls reject |
| Artifact verifier | Linux arm64 Docker python:3.11-slim, CPython3.11.18 | Same checks;80 tests pass at actual minimum |
| Artifact verifier | Linux arm64 Docker python:3.14-slim, CPython3.14.10 | Same checks;80 tests pass |
| Metadata boundary | Linux arm64 CPython3.10.22 | pip rejects wheel: requires Python>=3.11 |
| Source formula boundary | Modified copy of final sdist + original manifest | Renderer rejects digest mismatch, exit2 |
| Local Homebrew | macOSarm64, Homebrew Python3.14.10 | Install succeeds; linked formula test, strict audit and all80 installed tests pass; installed module matches final manifest |
| Homebrew negative control | Same installed client, harmless appended comment | Formula test fails AssertionError; exact bytes restored; formula test passes |
| Static hygiene | Current commit | Ruby syntax, formula style in tap, git diff --check pass; no source/test diff |

Python3.12/3.13 Linux are configured CI lanes and have not been executed locally for this handover. macOS3.11/3.12/3.13, x86_64, Windows, PyPy, OS keyring backends, Linux Homebrew and production service compatibility have no observed verification in this unit. CI still includes fresh hosted macOS install/test/strict-audit gate; that hosted run is pending root's PR. Local Homebrew is an existing Tier2 host, not a clean-machine public installation.

## Artifact identity

All six final builds happened to yield these same bytes; the supported reproducibility claim remains two builds of one commit on the same OS/interpreter with the same inputs.

```
c0529f0dc62e40c50de804a5fa8bf05d83a378211a9d3c95246e72eae5408cee  uptible_cli-0.1.0-py3-none-any.whl
df8ef3507dd93764639790cbf66e1298fa1c5b712f669541d035a1428b310112  uptible_cli-0.1.0.tar.gz
```

Committed module SHA256: `1b7b1b4ade0dec5d18d41d63e40c5102c5950d45eb2343cc1c7b14da6fb6b8a7`. Source timestamp:1794573203. Manifests, per-build install reports, SHA256SUMS, SOURCE_REVISION and negative controls live in `final-macos/`, `linux-output/final-linux311/`, and `linux-output/final-linux314/`. Final artifact logs record80 tests in159.033s,85.025s and108.974s respectively; Homebrew installed suite records110.719s. These are test durations, not performance claims.

## Homebrew boundary and host effects

Source archive/resource SHA256 and installed module identity are authenticated. Homebrew itself, its Python and resource build backends remain external toolchain inputs. No byte-reproducible Homebrew bottle claim is made. Linux Homebrew also depends on external Homebrew cryptography and is not approved by this work.

Despite NO_AUTO_UPDATE and NO_INSTALL_CLEANUP, Homebrew upgraded dependencies using current formula metadata. Exact changes are retained in `homebrew-install.log`: ca-certificates2026-08-13→2026-11-05; readline8.3.3→8.3.6; sqlite3.53.4→3.54.1; xz5.8.3→5.8.4; lz41.10.0→1.11.1; Python3.14.5→3.14.10. It installed openssl@4 4.1.0 and unlinked openssl@3 3.6.4. Old dependency kegs remain. Root was notified; shared dependency kegs/links were not rolled back or deleted.

Initial brew test refused the deliberate --skip-link install; the task-owned formula was linked, then the actual test passed. Standalone Ruby style selected nonformula rules; style in the real tap passes. Both failed setup attempts remain in raw evidence and are not counted as passed tests. Homebrew strict audit exits0 with a Homebrew rubocop-md obsolete-configuration warning. Existing test subprocess ResourceWarnings also occur in unchanged tests; direct PID/process inspection found no surviving task test processes.

Cleanup completed: task-owned Uptible install/link and local/uptibleartifact20261113 tap removed, task verifier temporary directories self-cleaned, no task Docker containers remain, own Python bytecode scratch removed. Shared dependency kegs, Docker images/caches, reviewable branch/worktree, source, artifacts and logs are retained. No user data or private app source was copied into the public CLI repository.

## Evidence and remaining Go actions

`public-evidence.zip` contains sanitized CLI-only logs/manifests and this report for root to attach; paths are redacted. Root must upload attachments and read back the public PR body so reviewers receive accessible evidence links. No local-machine or private-agent-session evidence URL should appear in the saved public body.

No tag, GitHub release, public tap push, purchase/provider mutation, production mutation or customer message occurred. Publication, clean-machine installation/update from the public channel, production login/account journey and original issue24 Go acceptance remain unperformed. README preserves current checkout-only availability and future publication/update instructions. Draft PR25 must not land unchanged; root coordinates its disposition. Issue1 full command/API parity and issue24 original criteria are not closed by this unit.

Poteto Feature playbook and local design comparison are in PLAN.md. Model the Domain led to marked requirements rather than a single-host freeze; Build the Lever produced repeatable construction and retained negative controls; Prove It Works required installed artifact/Homebrew authentication. The requested model families and nested delegate were unavailable/forbidden, so inherited Codex performed implementation and local whole-diff/comment review; root supplies independent reviewers. Tap the Sign preserved prior authorization and Go limits. Land the Plane was applied through final verification/current-main check and scoped cleanup; parent ownership explicitly reserves merge/sync and reviewable worktree removal.
