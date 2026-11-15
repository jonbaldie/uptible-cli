The installed Uptible CLI artifact from commit `8b9d0392cfc27dfebd279af79b82e6aea8bab992` passed its exact-source artifact gate and all 16 real deployed integration checks against API contract 1.2.0.

Two independent builds produced identical artifacts. The installed suite ran 108 tests: 107 passed and one explicitly gated deployed test was skipped. The separate deployed run recorded here used the installed console command, a fresh synthetic account, a real browser and PKCE approval. All six artifact negative controls were rejected.

| Behavior | Observed result |
| --- | --- |
| Omitted setting on create | Draft persisted with `false`; show returned `false` |
| Explicit enable | Saved `true` and incremented the revision |
| Stale revision | Safe HTTP 409 conflict; saved value, message and revision remained unchanged |
| Omitted setting on edit | Existing `true` remained `true` |
| Explicit disable | Saved `false`; show returned `false` |
| Explicit enable on create | Second draft persisted with `true`; exact idempotent replay returned the same draft |
| List | Returned both saved boolean values |
| Website readback | Visible checkbox was checked after enable and unchecked after disable/reload |

Both drafts were deleted using the supported CLI. Server logout revoked the connection. Supported website account closure returned the browser to login. Scoped readback confirmed zero live account, notification, capture, track, receipt, presence, lifetime-grant, access-token, refresh-token, authorization-code or token-family rows. It retained the closed-account record, two idempotency-key tombstones and two session rows. The unique credential file, lock and fixture password were removed. No synthetic access grant was needed.

Registration dispatched the framework verification notification. The effective mailer and transport were observed as `log`/`log`. External network traffic was not monitored.

This run covers draft configuration. It does not establish payment, activation, ingestion, or rendered widget behavior. Concurrency checks used the documented revision field; the CLI does not send an ETag header.

Wheel SHA-256: `b105a2c15b88d961769fc81c73da91c40f6bdb9592d99509ac8d54bfda9925ea`.

Source distribution SHA-256: `2b449fa40ecfd4ed54aaf509795b12c0f54949b4ab07ce59526404d9151491ee`.

The two cropped checkbox screenshots contain no account identity, authorization code, credentials, hostname, or other page content.
