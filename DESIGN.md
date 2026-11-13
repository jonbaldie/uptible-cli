# Client design

## HTTP failures

The request boundary recognizes fixed API and OAuth error codes, canonical UUID request IDs, and documented validation field names. It ignores arbitrary server messages and validation values. `Failure` carries only that safe context. Recovery wrappers preserve it when changing the local outcome to an uncertain write or refresh, so JSON can distinguish the recovery code from the server code. Text output includes the request ID for support. HTTP status comes from the response, not the body.

The existing read retry policy remains one extra request for HTTP 429 or 503 with a numeric `Retry-After` of at most two seconds; an absent header defaults to zero. Dates, longer delays and malformed values do not retry. The request timeout is 15 seconds and writes are not replayed automatically.

## Events and billing

Event commands send the caller's notification ID, session ID, event ID and payload directly to the authenticated operations. The server owns receipt identity and processing. The client requires a processed receipt and never retries a write automatically. An uncertain outcome tells the customer to repeat the exact command.

Billing status is a read of one page for each of two independent lists. The client passes each opaque cursor through without interpreting it. The server owns eligibility and access decisions. This command performs no checkout operation.

## Permission upgrades

Login retains its existing default scopes. Event, billing, lead deletion, and notification deletion scopes are opt-in flags. An explicit `auth login --add` requests the union of the existing token scopes and the selected additions. The protected account endpoint validates each token and supplies the account ID. Under the credential lock, the client compares those IDs and requires the approved scope set to match the requested union. It saves the replacement and revokes the old family. Failed or uncertain cleanup is reported. The client cannot upgrade a connection when it cannot determine the existing scopes or account identity. Token-decoding failures become structured errors. If a new grant cannot be decoded, the existing upgrade failure path attempts to revoke that grant and reports unconfirmed cleanup.

## Account continuity on refresh

The protected account endpoint supplies the account ID saved with a new or upgraded connection. Every refresh checks the refreshed token against that ID before saving it, including refreshes triggered by expiry or HTTP 401. A check only on deletion would miss an earlier refresh caused by a read. During a permission upgrade, the client also compares the old and refreshed scope sets.

For an older credential without a recorded account ID, the client uses the positive decimal account subject in its access token. If neither is available, it stops before refreshing. A mismatched or unverifiable refresh leaves the previous credential marked refresh-pending. Rotation may have consumed that credential, so recovery requires revocation and reconnection. The first identity or mismatch error gives local logout and login commands with the selected connection options. New opaque credentials can refresh when their protected account response supplies an integer ID.

## Notification deletion

The client validates the notification ID and requires confirmation before it opens the credential store. The server owns account and scope checks. The client makes one `DELETE` request and reports deletion only after HTTP 204. Network failures, damaged HTTP responses, server errors, and unexpected success responses leave the outcome unknown. The customer can read the notification before deciding whether to retry.

The shared request function reads and decodes an error body before retrying or handling its status. A complete empty body remains a status error, as does a valid JSON error. An unreadable or invalid nonempty body becomes a safe network failure. Structured HTTP failures retain their allowlisted codes and fields. The function does not print raw response text or request credentials. An interrupted deletion has an unknown outcome and is not replayed. An interrupted refresh may have consumed its credential, so the pending marker prevents a retry.

## Release inputs and reproducibility

The release artifact is the wheel and normalized source archive built from one clean Git commit. `scripts/verify-artifact.py` sets `SOURCE_DATE_EPOCH` to that commit's committer timestamp. Setuptools uses that timestamp for wheel ZIP members. The verifier writes source archive members in name order with that timestamp, zero ownership, fixed modes, and a gzip header without a filename. This removes wall-clock and checkout-path metadata. Two independent source directories, build environments, and runtime environments must produce identical artifact hashes and dependency resolutions. Their construction starts at different wall-clock times.

The byte reproducibility claim is two builds of the same commit with the same CPython version, operating system, and dependency inputs. Cross-interpreter and cross-platform byte equality is not required. The Git commit identifies the input source. `BUILD_MANIFEST.json` records its timestamp, interpreter, selected dependency wheel hashes, input-file hashes, and output hashes. Checksums detect changed bytes relative to those inputs. They are not publisher signatures.

| Path | Runtime and platform | Release verification |
| --- | --- | --- |
| Wheel and source archive | CPython 3.11 through 3.14, macOS and Linux | Verifier supports these hosts. CI runs all four versions on Linux. |
| Homebrew formula | Homebrew Python 3.14, macOS | Fresh hosted macOS install, module identity, dependency versions, test and strict audit. |
| Homebrew formula on Linux | Homebrew Python 3.14 with Homebrew cryptography | Resources are pinned, but the external cryptography formula is not. This path has no reproducibility or installation approval. |
| Windows, PyPy, future Python versions, OS credential stores | Package compatibility may vary | No release verification claim. Windows dependency markers preserve ordinary pip compatibility but do not establish support. |

`scripts/verification-requirements.txt` pins the build graph, including pip, with wheel hashes. `scripts/runtime-requirements.txt` pins the runtime graph with wheel hashes. Python markers add keyring compatibility dependencies before Python 3.12. Linux markers add SecretStorage and its cryptography graph. Windows markers add pywin32-ctypes. All compatible published wheel hashes are listed so a Mac-generated input file can also resolve a Linux wheel. The verifier requires binary inputs and rejects missing transitive pins. Normal package metadata keeps the public runtime ranges so downstream users retain compatible dependency choices.

Homebrew uses source resources from `scripts/homebrew-resources.json`. The renderer checks their versions against the runtime inputs and their file identity against the manifest. Each resource has its own source archive hash. Homebrew verifies those hashes when fetching. The renderer requires the CLI source archive to match the manifest and current Git revision before it emits a formula. The formula test authenticates the installed CLI module and checks common runtime versions. Homebrew itself, Python, resource build tools, and the Linux cryptography formula remain external toolchain inputs. Homebrew installation is a rehearsal, not a claim of byte-reproducible Homebrew bottles.

## Compatibility and dependency updates

CLI and package versions use the same semantic version. Before 1.0, a minor release may change command names or JSON fields and must describe the change in the changelog. Patch releases preserve command meanings, exit codes, and existing JSON fields. New optional error fields are additive. Scripts must ignore unknown fields. The API remains experimental and there is no claim of complete OpenAPI parity or a published minimum server release.

To update release dependencies, choose versions that support Python 3.11 through 3.14 and satisfy the package metadata. Read upstream wheel metadata for every transitive dependency and its markers. Replace the exact versions and SHA-256 wheel hashes in both requirement files using the corresponding PyPI version's JSON metadata. Keep all supported wheel variants. Update the formula source URLs and SHA-256 hashes from the same versions in `homebrew-resources.json`. Review upstream changes and scan dependency advisories. Do not copy `pip freeze` from one host. Commit the inputs, then run the verifier and all CI interpreter jobs. Rehearse the rendered formula on macOS and review the recorded dependency graph before approving an update.

A failed negative control blocks release verification. The verifier alters a downloaded dependency while retaining its expected hash and requires pip to reject it. It separately adds an unexpected member to a real wheel and requires package hygiene validation to reject it. Completion controls also remove a current command from the installed module and break its generated shell syntax. Each mutation must fail the completion suite. The verifier restores the exact installed module and reruns that suite. The logs remain alongside the verified artifacts.

The prerelease runtime minimum is Python 3.11. Filelock 4.2.10 includes fixes for upstream lock-class advisories and requires that minimum. The client retains its existing `FileLock` critical section in a private current-user directory with mode `0600`. That boundary limits the applicability of shared-directory attacks. Package advisory findings are not a claim that all affected lock classes are reachable through this client. Updating the dependency avoids carrying affected versions without introducing custom credential-lock behavior. Python 3.10 installation is rejected by package metadata.

## Local shell discovery

`build_parser()` constructs the command tree without dispatching a command. Both normal argument parsing and completion use this tree. The completion module reads argparse action metadata, including subparser aliases, option spellings, single-value arguments and fixed choices. It does not maintain a second command registry. The traversal handles the current parser's zero-value flags and single-value arguments. A future variable-length argument requires extending the traversal and its tests.

`uptible completion bash` and `uptible completion zsh` generate shell functions. They pass literal word arrays and the cursor word index to the private `--_complete` query before normal argument parsing. The query traverses syntax without calling `run()`. Invalid query envelopes return exit code 2 with no output; unrecognized syntax has no candidates. Query size is bounded. Output contains only parser-defined names or fixed choices, restricted to letters, digits, periods, underscores and hyphens. User values are never emitted or evaluated. No account or credential completion occurs.

A static generated command table would avoid starting Python on each completion, but would duplicate traversal across two shells and require regeneration whenever a command changes. The local query keeps the command vocabulary in one parser and leaves only shell word handling in each adapter. Bash rejoins its split equals and colon words. Zsh uses its word array directly. Shell generation is additive and does not change normal JSON or exit behavior.

The artifact gate installs the new module and runs the completion tests outside the checkout along with the existing synthetic suite. Real Bash and Zsh adapter checks use a guarded installed CLI that rejects socket connections, credential-store access, dispatch and browser calls. Shell tests require both shells; CI installs Zsh before running the gate. The comprehensive adapter assertions capture Zsh's `compadd` arguments to verify exact candidates. A separate terminal rehearsal verifies actual interactive Tab insertion.
