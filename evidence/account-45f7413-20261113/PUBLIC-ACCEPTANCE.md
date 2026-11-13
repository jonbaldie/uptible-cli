# Independent CLI acceptance

**PASS with notes** for the account email, explicit browser handoff and integration-target guard unit at commit `45f74138e58c5a57a592702fc1b0833781826a1d`, tree `590dd03f3a4046f9df585505d618a06f1a6fd7cd`. This acceptance does not close issue 1 or approve the whole release.

## Fresh checks

The final commit changes only `tests/test_integration.py` since the previously reviewed commit `1d21d1328cd55458c930766141f6db55bc9a3a19`. All eight wheel member payloads are byte-identical. The installed package is outside the source checkout, and the final source archive contains the exact committed integration test.

The old trailing-dot guard failure reproduces by reaching an intercepted login boundary. Calling the final actual integration method rejects 12 production hostname aliases and two malformed targets before starting a process. Two dedicated targets reach the intercepted login boundary. This guard proof performs no login or network request.

The complete artifact verifier exited zero: 97 tests ran (96 passed and one intentional actual-account skip), two independent clean builds, matching dependency resolutions and a final passing seven-test completion suite. Four integrity controls correctly reject a tampered dependency hash, unexpected wheel member, missing completion command and invalid generated shell syntax. The independent archives match the author artifacts byte for byte:

| Artifact | SHA256 |
| --- | --- |
| Wheel | `4301ed4d22ee8ff7731a3ed075cf16d90e1dfe33660abfcd0d9d9d5d92afcfed` |
| Source archive | `061085b10a2e8febcea129c8c460d1e205ae1cf754774a499527d2febb6da00f` |

Actual macOS native keychain acceptance uses the installed final `Store` and `keyring.backends.macOS.Keyring`. Four newly generated, initially empty identities vary issuer, client and profile. Save and exact retrieval, fresh-process retrieval, replacement, separation and deletion all pass. The file fallback also passes save, retrieval and deletion with private directory and file modes. All owned keychain items and lock files were removed and absence was verified. The values are synthetic; no existing credentials or authentication service was accessed.

## Notes and limits

An initial keychain attempt with a temporary HOME failed on its first write with OSStatus -60006 (`PasswordSetError`). Its owned items were confirmed absent. The subsequent run with the actual HOME passed every native check. The platform cause of the first failure is unestablished. Neither attempt read existing credentials.

Two transient subprocess ResourceWarnings appeared in unchanged upgrade tests. Both named child processes were confirmed absent after the passing verifier completed. The warnings were not suppressed.

The previous independent review's 49 actual browser and installed-wheel checks, real opt-in lifecycle checks and ten interactive Bash/Zsh checks are retained evidence on identical product bytes. They are **not fresh final-commit browser runs**. Earlier recipient-code expiry and replacement observations remain author evidence.

This acceptance establishes macOS arm64 CPython 3.14.10 native storage and the bounded CLI unit. Linux and Windows storage, the remaining platform matrix, public distribution, the final integrated schema pin and minimum server compatibility remain open. Review independence is from the author; no different-model-family agreement is claimed. No production deployment, publication or provider action occurred.

The packet contains only this public report, sanitized receipts, artifact provenance and a complete payload checksum manifest. Raw local logs and paths are excluded.
