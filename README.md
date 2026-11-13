# Uptible CLI

Use `uptible` to connect an Uptible account from your terminal, check the connection, and view your account. This version also lets you disconnect and revoke the connection.

## Install

You need Python 3.10 or later and pip. From a checkout of this repository, create a virtual environment and install the CLI:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
uptible --version
```

This installs from the checkout. There is no published release or update channel yet. The automated tests have been exercised on macOS and Linux.

## Connect your account

This is a prerelease. The public service and distribution are not yet available. Once the service is available, run:

```sh
uptible auth login
uptible auth status
uptible account show
```

The CLI opens your browser for authorization and listens for the response on a temporary loopback port. Approve access in the browser. The command then displays your account. If your browser cannot open, set a default browser and retry. A browser and a loopback connection are required.

When refresh is enabled on the server, the CLI refreshes an expired access credential automatically. It verifies the refreshed account before saving the rotated credential. The same check applies when a request triggers a refresh after HTTP 401.

## Browse and delete leads

`uptible leads list --limit 20` lists one page, including leads from inactive and archived notifications. Use `--notification-id` to filter by notification. `--from 2026-01-01` includes that UTC date; `--until 2026-02-01` excludes that UTC date and later dates. Pass the returned `next_cursor` as `--cursor` with the same filters to continue. Use `uptible leads show 123` to inspect one lead.

`uptible leads delete 123` permanently deletes one lead after confirmation. Use `--yes` to confirm in a noninteractive session. Ordinary login grants lead reading, not deletion. To request deletion permission at initial login, use `uptible auth login --delete-leads`. To add it to an existing connection, use `uptible auth login --add --delete-leads` and approve it in the browser. Reading requires lifetime access; deletion permission allows deletion of owned leads even after access ends. If a deletion outcome is unknown, check the lead before deciding whether to retry. A lead that is already gone returns 404.

## Read dashboard statistics

Run `uptible stats show` to read dashboard statistics. This requires lifetime access. Capture counts include currently active, non-archived notifications owned by your account. The hour and day counts cover inclusive rolling UTC intervals ending at `as_of`, spanning the preceding hour and 24 hours. Tracks include all account history, including tracks for inactive, archived, or deleted notifications. The server may cache results for up to one second. `as_of` identifies the window end, not a transactional snapshot.

Ordinary login requests statistics read permission. If statistics returns HTTP 403, check lifetime access and the connection permissions.

## Submit events and inspect billing

When first connecting, add `--events` to request event submission permission or `--billing` to request billing read permission. Both can be selected together. Ordinary login does not request these permissions. To add them to an existing connection, run `uptible auth login --add --events --billing` and approve the requested permissions in the browser.

```sh
uptible events capture 123 --session-id visit-123 --event-id signup-123 --email person@example.com
uptible events track 123 --session-id visit-123 --event-id view-123
uptible billing status
```

Event IDs and session IDs are required. Choose stable IDs yourself. If submission returns an uncertain result, retry the exact notification, operation, IDs, and payload. A `processed` receipt confirms processing. A different capture payload for the same identity conflicts. Only live notifications owned by the connected account and covered by lifetime access can accept events.

Billing status reads lifetime access, purchase eligibility, recent attempts, orders and purchase references. Eligibility does not guarantee checkout availability. The command does not initiate checkout or contact a payment provider. Each response contains up to 20 orders and 20 purchase references. Pass `next_cursor` as `--cursor` and `next_claim_cursor` as `--claim-cursor` to read older entries. Each cursor is opaque and bound to its account and list.

## Configure a notification

Create a draft with a unique key that you keep with the request. If the response is lost, repeat the exact command with the same key. A key identifies one create operation, so use a new key for a different notification.

```sh
uptible notifications create --idempotency-key campaign-2026-01 --message "Someone joined"
uptible notifications list --limit 20
uptible notifications show 1
uptible notifications edit 1 --revision 1 --message "Someone signed up"
uptible notifications activate 1
uptible installation show
uptible notifications activity 1
```

Use the returned ID and revision in place of the example values. Edit requires the current revision and a message. Omitted settings remain unchanged. If an edit conflicts, fetch the notification, review the current settings and revision, and decide whether to retry. Use `--help` on create or edit for configuration options. Activation, installation and activity require lifetime access. `deactivate`, `archive`, and `restore` are also available. Listing returns `next_after`; pass that value as `--after` for the next page.

Existing connections made before these commands may lack their permissions. If a command returns HTTP 403, check lifetime access and the connection permissions.

## Permanently delete a notification

Unlike archive, permanent deletion removes the notification and its collected leads. You can also delete an archived notification. Historical tracks and shared sessions remain, and logs, caches, or backups may retain data.

Ordinary login does not request deletion permission. For a new connection, run `uptible auth login --delete-notifications`. For an existing connection, run `uptible auth login --add --delete-notifications`. Approve the permission and enter your current password in the browser. The CLI does not ask for your password.

Run `uptible notifications delete 123` and confirm the prompt. Use `--yes` to confirm without a prompt. A successful command returns `{"deleted": true, "id": 123}` after the server confirms deletion. The CLI never automatically repeats the delete request. A lost or damaged response, or an interruption while waiting for it, leaves the outcome unknown. Run `uptible notifications show 123` before deciding whether to retry. A missing or foreign notification returns HTTP 404.

## Add permissions

Use `uptible auth login --add` with one or more of `--events`, `--billing`, `--delete-leads`, and `--delete-notifications`. The browser asks you to approve the existing permissions and the additions. Sign in to the same account. Deleting leads or notifications requires your current password in the browser.

The CLI retains the existing connection if you decline or select a different account. It saves the approved connection before revoking the old grant. If it cannot confirm grant cleanup, check your account connections and revoke the unintended connection. If the CLI cannot determine the existing permissions, it stops without replacing the connection.

## Disconnect

Revoke the server connection and remove the saved local credential:

```sh
uptible auth logout
```

To forget the local credential without revoking the server connection, use `auth logout --local`. The server connection may remain active. Revoke it on your account page if needed.

## Credential storage

The CLI uses an available supported operating-system keyring backend. To use a private file instead, add `--credential-file /path/to/private/credentials` before the command on every invocation. On Unix, the directory must be owned by you and inaccessible to other users. The CLI creates the file with mode `0600`. Keep it private.

For an alternate service, pass `--issuer` and its registered `--client-id` before every command. The service must return an integer account ID from its protected account endpoint. The explicit flags override the built-in defaults; environment variables do not select a connection. Use `--profile NAME` before the command to select a separate keyring connection. For file storage, use a distinct file for each profile, issuer, and client ID. Do not copy a rotating refresh credential between machines. Simultaneous use can revoke the token family.

## Recover a connection

If login reports that a grant may have been created or that revocation could not be confirmed, inspect your account connections and revoke any unintended grant before retrying.

If refresh fails or is interrupted, its outcome can be unknown. The CLI retains the old credential and refuses to replay it. The CLI does not save a refreshed credential if it belongs to another account or the account cannot be verified. During a permission upgrade, it also rejects changed permissions. The previous refresh credential may already be consumed. Revoke the connection on your account page, run `auth logout --local`, and log in again with the same issuer, client ID, and storage options.

Older connections may not contain a recorded account ID. If their access token has no usable account subject, the CLI stops before refreshing. Reconnect to record the account ID.

## Output and help

Add `--json` before the command for machine-readable output. Results are JSON objects on standard output. Operational errors are JSON objects on standard error with `error.code` and `error.message`. Argument parser errors use standard text even with `--json`. Output can contain account information, but not credentials.

Exit codes are `0` for success, `2` for usage or configuration errors, `3` for server or network failures, and `1` for other failures. Use `uptible --help` and command-specific help such as `uptible auth login --help` for options.

## Current limitations

| Operation | Command |
| --- | --- |
| Connect, check, or disconnect an account | `uptible auth login`, `uptible auth status`, `uptible auth logout` |
| Show account | `uptible account show` |
| List, show, or create notifications | `uptible notifications list`, `uptible notifications show`, `uptible notifications create` |
| Update notification settings | `uptible notifications edit` |
| Activate or deactivate a notification | `uptible notifications activate`, `uptible notifications deactivate` |
| Archive or restore a notification | `uptible notifications archive`, `uptible notifications restore` |
| Permanently delete a notification | `uptible notifications delete` |
| Show dashboard statistics | `uptible stats show` |
| Show installation details | `uptible installation show` |
| Show notification activity | `uptible notifications activity` |
| List, show, or permanently delete leads | `uptible leads list`, `uptible leads show`, `uptible leads delete` |
| Preview a notification | Not implemented |
| Submit capture or tracking events | `uptible events capture`, `uptible events track` |
| Read lifetime billing | `uptible billing status` |
| Modify an account, view broader statistics, or initiate checkout | Not implemented |

The connection routes are experimental and may change before a public API contract is published. Checkout and other account operations are not implemented. Full command coverage, server compatibility, reproducible release dependencies and distribution remain open in [issue #1](https://github.com/jonbaldie/uptible-cli/issues/1).

## Development

Run the synthetic loopback tests with `python -m unittest discover -s tests -v`. The tests use an explicit browser driver and do not open a system browser or contact a real account.

To build and verify the committed checkout as installable distributions, run:

```sh
python3 scripts/verify-artifact.py /tmp/uptible-verified
```

The output directory must be empty and the checkout clean. The command builds a wheel and source distribution from the commit, checks their file lists, installs the wheel in a fresh temporary environment, and runs the synthetic tests outside the checkout. It records the commit and SHA-256 digests alongside the artifacts. It downloads pinned build tools and the package's runtime dependencies from the configured Python package index. CI runs this check on Linux with Python 3.10 and 3.14 and retains the artifacts. These checks do not establish operating-system keyring support or deployed-service compatibility. Remaining command coverage stays in issue #1.

## Release

Pushing a tag such as `v0.1.0` runs `.github/workflows/release.yml`. The tag must match the version in `pyproject.toml` and in `uptible_cli.VERSION`. The workflow builds and verifies the distributions with `scripts/verify-artifact.py`, then renders a Homebrew formula with `scripts/homebrew-formula.py`. A macOS job installs, tests and audits that formula from the built source distribution. Only then does it publish a GitHub release with the wheel, the source distribution, `SHA256SUMS`, `SOURCE_REVISION` and `uptible.rb`. Pull requests run the same steps without publishing.

To publish through Homebrew, copy the released `uptible.rb` to `Formula/uptible.rb` in `jonbaldie/homebrew-tap`. Then check `brew install jonbaldie/tap/uptible` and `brew test jonbaldie/tap/uptible`. The formula installs into its own Python 3.14 virtual environment. The dependency pins in `scripts/homebrew-formula.py` are resolved for `keyring>=25,<26` and `filelock>=3.16,<4`. Update them when those ranges change.
