# CLI API compatibility reference

CLI `0.1.0` targets management API major `1` at `/api/v1`. Its minimum compatible server contract is `1.1.0`, expressed as a public semantic contract version rather than an application build number. OAuth must also be enabled and the public client registered on the selected service.

The bundled OpenAPI 3.0.3 candidate is [v1.1.0.json](v1.1.0.json). [manifest.json](manifest.json) pins its version and SHA-256. The exact candidate SHA-256 is `69478e641f5fe22df2012abf3cec8db0089b8f083b228f26f99b093c1002868c`.

This candidate is staged for compatibility testing. Public server publication and independent acceptance are pending. Its presence here does not establish production availability, deployed compatibility, a published package, or a public server reference URL. Before release, verify the publicly served manifest and snapshot against these exact bytes and run the test-account journey against the intended compatible test server. Link the published reference and protocol guides once available.

## Server requirements and support policy

The server advertises its contract in the `Uptible-API-Version` header on management success and problem responses. Compatible values are at least `1.1.0` within major `1`. Missing, malformed, older or different-major values do not establish compatibility. Update the server before attempting capabilities whose availability is unknown. The opt-in integration suite checks this header with a read before mutating a draft. The normal CLI does not negotiate a reduced command set or prevent writes to an older server. Operators must select a compatible service.

Within major `1`, compatible additions include optional request properties, new operations and response fields. Consumers ignore unknown response fields. They retain the documented required fields, types, operation identities, scopes, receipt identities and retry meanings. Breaking changes require a new major API path. A successor preserves the preceding major for at least 12 months after general availability and gives at least 180 days of public retirement notice, subject to urgent security changes. No retirement date is scheduled in this candidate.

CLI and package versions are independent of the server contract version. Before CLI 1.0, minor CLI releases may change command names or JSON fields with a changelog entry. Patch releases preserve command meanings, exit codes and existing JSON fields. Scripts must ignore additive fields. Platform and packaging support are recorded in [the release design](../../DESIGN.md#release-inputs-and-reproducibility).

## Operation mapping

[cli-operations.json](cli-operations.json) is the executable consumer test table. Each row records the operation ID, method, route, required OAuth scopes, command arguments and expected outbound request. The human capability table also records the [browser handoffs](../capabilities.md). Cookie authentication alternatives in the server schema belong to first-party browser clients. The CLI always uses OAuth bearer credentials and never sends browser cookies or CSRF tokens.

| Operation ID | CLI command | OAuth scope |
| --- | --- | --- |
| `get_api_v1_account` | `account show` | `account:read` |
| `post_api_v1_account_email_change` | `account update` | `account:email:write` |
| `post_api_v1_logout` | `auth logout` | Any current OAuth grant |
| `get_api_v1_billing` | `billing status` | `billing:read` |
| `get_api_v1_installation` | `installation show` | `installation:read` |
| `get_api_v1_statistics` | `stats show` | `statistics:read` |
| `get_api_v1_leads` | `leads list` | `leads:read` |
| `get_api_v1_leads_id` | `leads show` | `leads:read` |
| `delete_api_v1_leads_id` | `leads delete` | `leads:delete` |
| `get_api_v1_notifications` | `notifications list` | `notifications:read` |
| `post_api_v1_notifications` | `notifications create` | `notifications:write` |
| `get_api_v1_notifications_id` | `notifications show` | `notifications:read` |
| `put_api_v1_notifications_id` | `notifications edit` | `notifications:write` |
| `delete_api_v1_notifications_id` | `notifications delete` | `notifications:delete` |
| `put_api_v1_notifications_id_target` | `notifications activate` | `notifications:write` |
| `get_api_v1_notifications_id_activity` | `notifications activity` | `activity:read` |
| `post_api_v1_notifications_id_capture` | `events capture` | `events:write` |
| `post_api_v1_notifications_id_track` | `events track` | `events:write` |

## Check consumer compatibility

Run the installed CLI tests outside the source checkout with the checkout's tests directory. The artifact verifier does this automatically. The tests launch actual installed CLI subprocesses against an isolated synthetic HTTP service, inspect each outgoing method, path, header, filter and JSON payload, and validate them against the pinned schema. Every pinned management operation must have one mapped command. A real synthetic OAuth journey checks that requested scopes cover the mapping. Success fixtures include unknown response fields, including email acknowledgements and event receipts.

To check another locally downloaded public schema without changing the pin, set `UPTIBLE_CONTRACT_SCHEMA` to its absolute filename and run `python -m unittest discover -s /absolute/path/to/checkout/tests -p test_contract.py -v` from outside the checkout. This is a consumer request and example-response check. It validates the schema constructs used by these cases and is not a general OpenAPI linter or a proof of every possible compatible schema change. Server schema linting, server behavior and live browser protocols need separate verification. Compatible new operations do not require a CLI command until deliberately adopted. Every operation in the pinned snapshot remains mapped.

Negative controls reject a removed operation, newly required OAuth scope, wrong integer wire type, invalid lifecycle value and narrowed input range. The artifact gate also mutates the installed consumer to send a boolean notification field and reject additive event receipts. Both mutations must fail the contract traffic tests, then the exact restored module must pass. Altered dependency inputs, unexpected wheel members and broken completion behavior must fail too. A pin update requires deliberate review of the schema bytes, manifest, operation mapping, examples and real-server results. Never replace the first version's server baseline to make a change pass.

## Request and response behavior

Notification lists use one explicit bounded page. `--after` and `--before` carry positive ID cursors and cannot be combined. `next_after` and `previous_before` identify the next request, and `--archived include|exclude|only` selects archive visibility. Lead cursors are opaque, account-bound and filter-bound. Billing has separate opaque order and claim cursors. No command silently retrieves every page.

Notification creation sends a caller-selected `Idempotency-Key` and optional `--state draft|active`. Omission keeps the server's draft default. Active creation requires lifetime access. Edits send the current explicit revision. Lifecycle writes set an explicit target. The maps-only switch sends integer `1` or `0`. The server owns input trimming, validation, authorization and access decisions.

Statistics return explicit UTC rolling hour and 24-hour windows. The server does not support arbitrary windows or time zones. Events return `processed` receipts and have no documented asynchronous status endpoint. Repeat uncertain event submissions with the identical operation, IDs and payload. Unknown receipt fields are additive, but missing or invalid receipt/status fields remain uncertain.

The client retains only recognized problem codes, validation field names and canonical request IDs in diagnostics. It ignores arbitrary server messages and validation values. HTTP 401, 403, 404, 409, 422, 429 and server failures retain safe structured context. Session-only HTTP 419 does not apply to CLI OAuth requests. Read retries are bounded to one retry for HTTP 429 or 503 with a numeric delay of at most two seconds. Writes are not replayed automatically. See [output and recovery](../../README.md#output-and-help).
