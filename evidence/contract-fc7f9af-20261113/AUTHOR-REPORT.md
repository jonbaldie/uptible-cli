# Final CLI contract candidate evidence

Uptible app and CLI maintainers need production launch readiness evidence without production deployment or public publication. This bounded unit removes one accepted purpose docstring and rebuilds the committed CLI candidate.

## Source and artifacts

The final source revision is `fc7f9afa8fb63fc7e377f3719571d4d9a64956fa`. Its tree is `6b304198dfb8d351df52a3bbbd6277cb6be134cd`. The parent is `b37eec69b7e3e1ba5f980cf44d5befeaa568a049`. The only source change is deletion of the first-line purpose docstring in `tests/test_contract.py`.

The final artifact hashes are recorded in `SHA256SUMS` and `BUILD_MANIFEST.json`.

- Wheel SHA256 is `9276b86fae4daeff0f79cae2279f41204bb82ee11c4d9e7ea11e6a3d341a66e0`.
- Source archive SHA256 is `f629e29648192f9ac6bc484ad027002796b7d53528f25cd8e490a608596e756e`.
- Product module SHA256 is `64ecf3f8bde9398ef8686492e33bce95abdbad1b09bc9960556aab7667ef0597`.
- Pinned contract SHA256 is `69478e641f5fe22df2012abf3cec8db0089b8f083b228f26f99b093c1002868c`.

The product module and pinned OpenAPI 3.0.3 contract 1.1.0 bytes are unchanged. Every wheel member, including metadata and dependency declarations, is byte identical to the prior wheel. ZIP member timestamps changed with the new commit epoch. Build and selected runtime dependency names, versions, and input hashes are identical. All dependency input files are unchanged.

The source archive has one changed file content, the exact first-line deletion. All four Python test files have identical ASTs after docstrings are removed. `artifact-equivalence.safe.json` and `verify-equivalence.py` record and reproduce these comparisons. The packet includes the prior artifacts under `baseline` so the comparison needs no private session access.

## Exact artifact gate

The repository verifier ran successfully at the final commit with CPython 3.14.10 on `Darwin 25.6.0 arm64`. It built twice from clean committed archives in independent environments. Artifact hashes and selected dependency hashes matched.

The installed suite ran 103 tests and passed with one intended skip. The skipped test requires an explicitly provisioned real integration account. The run did not use one. Contract restoration ran six tests successfully. Completion restoration ran seven tests successfully.

All six negative controls failed as required. They cover a tampered dependency hash, unexpected wheel member, omitted completion command, broken generated shell, boolean notification wire value, and closed additive event receipt. The verifier restored the installed module and reran the affected suites successfully.

`logs/artifact-verification.log` is the sanitized complete run. The passing suite emitted subprocess ResourceWarning messages. Cleanup verified that no owned subprocess survived. An initial default `python3` invocation used unsupported CPython 3.9.6 and was rejected before any build. `logs/unsupported-default-python.log` preserves that preflight result separately.

## Installed wheel readback

A new standalone virtual environment installed the final wheel with its hash and the pinned runtime inputs. `pip check` passed. A subprocess outside the checkout imported the installed module, checked its product hash, read distribution version 0.1.0, and matched all six selected runtime dependency versions against the manifest.

Five installed CLI commands passed their expected outcomes. They cover version, root help, notification list help, notification create help, and conflicting notification cursors. The conflicting cursor command exited with code 2. `installed-command-receipt.safe.json` contains the complete command outputs. The temporary installation and work directory were removed after readback.

## Scope and limits

These are synthetic consumer and packaging results. They do not establish compatibility with a deployed Uptible server. The server contract is a staged candidate. Normal CLI requests do not negotiate or enforce the server version. The opt-in real-account integration path remains unrun in this unit.

No new native operating-system credential proof is claimed. The prior independent proof remains evidence for its original artifact. The direct wheel-member, dependency declaration, input lock, and selected dependency comparisons let the coordinator assess its applicability to this candidate. Root owns the independent installed-wheel and native acceptance verdict.

This unit performed no provider configuration, shared development changes, forge changes, merge, production deployment, package release, or public publication. Historical reports remain attached to their original revision. Root owns source review, forge operations, independent approval, integration, merge, and sync.

Laziness Protocol limited the source change to the accepted deletion. Prove It Works required the new exact artifact gate, full byte comparisons, and standalone installed readback. Scoped land-the-plane cleanup retained the clean source worktree for root review and removed owned temporary resources.
