# Linux native credential acceptance

**PASS with notes** for the frozen CLI wheel at commit `45f74138e58c5a57a592702fc1b0833781826a1d`, tree `590dd03f3a4046f9df585505d618a06f1a6fd7cd`. This is bounded Linux credential-storage acceptance for launch-decision evidence. It does not close issue 1 or approve the whole release.

The exact `uptible_cli-0.1.0-py3-none-any.whl` has SHA256 `4301ed4d22ee8ff7731a3ed075cf16d90e1dfe33660abfcd0d9d9d5d92afcfed`. It was installed outside the checkout on Debian 13.7, Linux aarch64, CPython 3.14.10. Runtime dependencies came from the committed requirements with `--require-hashes --only-binary=:all:`. `pip check` passed. The installed module bytes match the reviewed module hash.

The proof uses the actual installed `Store`, automatic `keyring.backends.SecretService.Keyring` selection, D-Bus 1.16.2-2 and gnome-keyring 48.0-1. A direct D-Bus process-owner query matches the explicitly started daemon. There is no replacement credential backend. The daemon and D-Bus run in separate processes from the Store callers. All native operations use fresh Python worker processes against the same daemon.

Four generated identities vary issuer, client and profile one at a time. Each starts empty. Save and exact retrieval, fresh-process retrieval, replacement, preservation of the other identities, deletion and fresh-process absence all pass. The Secret Service collection contains exactly four items after saves and replacement, and zero after deletion. Saving an earlier identity leaves every not-yet-written identity empty.

The explicit file path passes save, exact retrieval and deletion with a 0700 directory, 0600 file and 0600 lock. It rejects the wrong connection, a world-readable file and a public directory. A fresh process with an unavailable D-Bus endpoint rejects native storage with `no_credential_store`; an explicit private file still saves, reads and deletes correctly. The CLI has no nonpersistent credential mode, so that check is not applicable. Final receipts contain 44 passing observations and one not-applicable observation.

The first isolated startup attempt timed out before credential writes. Its log shows D-Bus service activation during startup. The precise platform cause was not established. The verifier then waited for service ownership without triggering activation and directly checked the service PID. The resulting native proof passed, including a final augmented run with the unavailable-service control. The failed attempt is retained as a setup failure, not relabelled as a passing native run or a product defect.

The acceptance container had networking disabled, a read-only root filesystem and a new ephemeral user home. Its only host mount was the read-only verifier script. All credential values were generated synthetic data. No existing host credentials, OAuth endpoint or Uptible server were accessed. Public dependency setup used networking before the acceptance run.

All owned items were verified absent, the owned daemon stopped, synthetic state removed, and the disposable container and image removed. Their absence was read back. Shared images and builder cache were not pruned. No product file, forge record, provider setting, release, deployment or publication changed.

This verifies one Linux aarch64 CPython 3.14.10 Secret Service environment. It does not establish other desktops, locked-keyring interaction, daemon restart recovery, other Python or CPU combinations, Linux Homebrew, Windows, or release-wide acceptance. OS packages and the base image are recorded inputs, not a claim of reproducible OS package resolution.

The packet includes sanitized receipts, provenance, the actual verifier script, a portable Docker recipe, committed runtime pins and the installed dependency list. It contains no credential values, personal paths, private runtime identifiers or host credential data.
