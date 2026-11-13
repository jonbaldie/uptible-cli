# Uptible CLI

Use `uptible` to connect an Uptible account from your terminal, check the connection, and view your account. This version also lets you disconnect and revoke the connection.

## Install

You need Python 3.11 or later and pip. From a checkout of this repository, create a virtual environment and install the CLI:

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

Run `uptible notifications delete 123` and confirm the prompt. Use `--yes` to confirm without a prompt. A successful command returns `{"deleted": true, "id": 123}` after the server confirms deletion. The CLI never automatically repeats the delete request. A lost or damaged response, or an interruption while waiting for it, leaves the outcome unknown. An unreadable or invalid nonempty error body is also treated as damaged, even when the status is 4xx. A complete empty error body or valid JSON error keeps its status handling. Run `uptible notifications show 123` before deciding whether to retry. A missing or foreign notification returns HTTP 404.

## Add permissions

Use `uptible auth login --add` with one or more of `--events`, `--billing`, `--delete-leads`, `--delete-notifications`, and `--email-change`. The browser asks you to approve the existing permissions and the additions. Sign in to the same account. Deleting leads or notifications and requesting email changes requires your current password in the browser.

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

If refresh fails or is interrupted, its outcome can be unknown. The CLI retains the old credential and refuses to replay it. The CLI does not save a refreshed credential if it belongs to another account or the account cannot be verified. During a permission upgrade, it also rejects changed permissions. The previous refresh credential may already be consumed. Revoke the connection on your account page, run `auth logout --local`, and then run `auth login` with the same issuer, client ID, profile, and storage options.

Older connections may not contain a recorded account ID. If their access token has no usable account subject, the CLI stops before refreshing. Revoke the connection, forget it locally, and log in again to record the account ID. For these identity failures and refresh account or permission mismatches, the error includes both commands with the selected options, quoted for a POSIX shell. Login requests the default permissions. Include any opt-in permission flags again if you need them.

## Output and help

Add `--json` before the command for machine-readable output. Results are JSON objects on standard output. Operational errors are JSON objects on standard error with `error.code` and `error.message`. Argument parser errors use standard text even with `--json`. Output can contain account information, but not credentials.

Recognized API and OAuth error codes are retained. HTTP failures also include `error.http_status`. A valid server request ID appears as `error.correlation_id` in JSON and as `Request ID` in text output; include it when reporting a failed request. Validation failures can include `error.fields`, containing recognized field names. Server messages and validation values are not printed. If a write outcome is uncertain, `error.code` keeps the recovery outcome, such as `create_uncertain`, and `error.server_code` retains the recognized server code when available.

HTTP requests have a 15-second timeout. A read receiving HTTP 429 or 503 retries at most once when `Retry-After` is an integer from 0 to 2 seconds. A missing header causes one immediate retry. A date, a longer delay, or a malformed value does not trigger a retry. Writes are never automatically replayed.

Exit codes are `0` for success, `2` for usage or configuration errors, `3` for server or network failures, and `1` for other failures. Use `uptible --help` and command-specific help such as `uptible auth login --help` for options.

## Enable shell completion

Completion discovers local command names, options and fixed choices. It never reads saved credentials, opens a browser, contacts the service or runs an account action. Free-form values such as account identifiers, file paths, email addresses and cursors have no suggestions. Root options such as `--profile` and `--json` belong before the command, as in normal execution.

Generate the Bash function from the installed CLI, then load it in your current shell:

```sh
mkdir -p ~/.local/share/uptible
uptible completion bash > ~/.local/share/uptible/completion.bash
source ~/.local/share/uptible/completion.bash
```

Add `source ~/.local/share/uptible/completion.bash` to your Bash startup file to load it in future shells. Bash 3.2 and later are supported.

For Zsh, initialize its completion system before loading the generated function:

```sh
mkdir -p ~/.local/share/uptible
uptible completion zsh > ~/.local/share/uptible/completion.zsh
autoload -Uz compinit
compinit
source ~/.local/share/uptible/completion.zsh
```

Add those last three lines to `~/.zshrc`. If your configuration already runs `compinit`, add only the `source` line after it. Zsh 5.9 is exercised by the shell checks.

In either shell, type `uptible no` and press Tab to complete `notifications`. Type `uptible auth lo` and press Tab twice to see `login` and `logout`. Type `uptible leads list --limit 9` and press Tab twice for the matching fixed numeric choices. `uptible notifications edit 123 --no-` completes `--no-display-maps-only`.

After upgrading the installed CLI, rerun the generation command for your shell and source the resulting file again. Candidates come from the installed parser on each Tab press. Use `uptible completion --help` to find the supported shells. Generation and querying require the installed `uptible` executable on `PATH`.

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
| Preview a notification | `uptible notifications preview ID` opens the browser list for manual selection |
| Submit capture or tracking events | `uptible events capture`, `uptible events track` |
| Read lifetime billing | `uptible billing status` |
| Request email update and confirm it | `uptible account update --email ADDRESS`, `uptible account confirm-email` |
| Settings, security and onboarding | `uptible account settings`, `uptible account security`, `uptible account onboarding` |
| Review lifetime checkout | `uptible billing checkout` opens the browser review page |
| Arbitrary statistics windows and time zones | Not supported by the server |

The connection routes are experimental and may change before a public API contract is published. Browser actions have explicit continuity and completion limits in the [capability reference](docs/capabilities.md). Full contract coverage, server compatibility and distribution remain open in [issue #1](https://github.com/jonbaldie/uptible-cli/issues/1).

## Development

Run the synthetic loopback tests with `python -m unittest discover -s tests -v`. The tests use an explicit browser driver and do not open a system browser or contact a real account.

To build and verify the committed checkout as installable distributions, run:

```sh
python3 scripts/verify-artifact.py /tmp/uptible-verified
```

The output directory must be empty and the checkout clean. The command builds twice from the commit in independent environments with hashed build and runtime inputs from PyPI. It compares artifact hashes and selected dependency hashes, checks package file lists, installs the wheel, and runs all synthetic tests outside the checkout. It requires altered dependency bytes, an unexpected wheel member, an omitted completion command and broken generated shell code to fail verification. Install Bash and Zsh before running this gate. The artifacts include `BUILD_MANIFEST.json`, `SOURCE_REVISION`, `SHA256SUMS`, dependency reports, and negative-control logs. See [the release design](DESIGN.md#release-inputs-and-reproducibility) for the exact reproducibility claim and supported matrix. CI runs Python 3.11 through 3.14 on Linux. These checks do not establish operating-system keyring support or deployed-service compatibility. Remaining command coverage stays in issue #1.

## Release

Pushing a tag such as `v0.1.0` runs `.github/workflows/release.yml`. The tag must match the version in `pyproject.toml` and in `uptible_cli.VERSION`. The workflow builds and verifies the distributions with `scripts/verify-artifact.py`, then renders a Homebrew formula with `scripts/homebrew-formula.py`. A macOS job installs, tests and audits that formula from the built source distribution. Only then does it publish a GitHub release with the wheel, the source distribution, `SHA256SUMS`, `SOURCE_REVISION`, `BUILD_MANIFEST.json` and `uptible.rb`. Pull requests run the same steps without publishing.

To publish through Homebrew, copy the released `uptible.rb` to `Formula/uptible.rb` in `jonbaldie/homebrew-tap`. Then check `brew install jonbaldie/tap/uptible` and `brew test jonbaldie/tap/uptible`. The formula installs into its own Python 3.14 virtual environment. The renderer authenticates the source archive against the verifier manifest. The formula verifies pinned source resources, installed module identity, and dependency versions. Follow [the dependency update procedure](DESIGN.md#compatibility-and-dependency-updates) when changing those inputs.


To rehearse Homebrew locally without publishing, use the verified source archive. Set `verified` to the absolute output directory from the verifier:

```sh
verified=/absolute/path/to/uptible-verified
brew tap-new --no-git local/uptible
python3 scripts/homebrew-formula.py --version 0.1.0 \
  --sdist "$verified/uptible_cli-0.1.0.tar.gz" --url "file://$verified/uptible_cli-0.1.0.tar.gz" \
  > "$(brew --repository)/Library/Taps/local/homebrew-uptible/Formula/uptible.rb"
brew install local/uptible/uptible
brew test local/uptible/uptible
brew audit --strict --formula local/uptible/uptible
```

This local tap is a release rehearsal. No public Homebrew package is available yet. After the maintainer publishes and verifies the release and tap, the customer install command becomes `brew install jonbaldie/tap/uptible`. A later published version updates with `brew update` and `brew upgrade jonbaldie/tap/uptible`. Production publication, clean-machine installation from the public tap, and login against `https://uptible.com` remain unperformed Go actions in [issue #24](https://github.com/jonbaldie/uptible-cli/issues/24).

## Update your email address

Request the extra permission explicitly. The browser asks for your current password during consent. The CLI never collects a password or confirmation code.

```sh
uptible auth login --add --email-change
uptible account update --email new-address@example.com
uptible account confirm-email
uptible account show
```

For a new connection, omit `--add`. The update command sends only the new address and reports `confirmation_required`. It does not report an identity change. Check the browser's signed-in account, then enter the emailed recipient code and current password in **Confirm email change** on the account page. Afterwards, `account show` reads the authoritative identity. The existing connection continues after confirmation.

Invalid, expired, replaced or used codes do not change the address. If the request outcome is unknown, inspect the recipient mailbox and account page before requesting another code. The CLI never automatically repeats an email request.

## Open browser actions

Use `account settings`, `account security`, `account onboarding`, `installation open`, `notifications preview ID`, `billing checkout`, or `billing open`. The [capability reference](docs/capabilities.md) lists their routes and limits.

These commands open a fixed page on your selected service. The browser has an independent session. Compare its identity with `account show` before you submit a form. Opening the page does not confirm that a setting changed, a preview rendered or a payment completed. Handoff JSON reports `completed: false` and `account_binding_verified: false` because the service has no account-bound return receipt.

## Run the opt-in test account suite

Provision an isolated service and a dedicated disposable test account first. Register the public client for loopback OAuth callbacks. Use the installed CLI's Python environment and set every target explicitly:

```sh
UPTIBLE_INTEGRATION=dedicated-test-account \
UPTIBLE_TEST_ISSUER=https://test.example.com \
UPTIBLE_TEST_CLIENT_ID=registered-public-client \
UPTIBLE_TEST_ACCOUNT_ID=123 \
python -m unittest discover -s tests -p test_integration.py -v
```

The suite uses fresh temporary credentials and real system-browser OAuth. Sign in to the dedicated account and approve notification deletion with current-password proof in the browser. The suite verifies the returned account ID before it creates one uniquely named synthetic draft. It reads, archives, restores and deletes only that draft, then revokes its own connection. Existing credentials and unrelated notifications are untouched. A failed cleanup requires attention before rerunning.

For a test account with lifetime access, add `UPTIBLE_TEST_LIFETIME_ACCESS=yes` to check lead, statistics and installation reads. The suite does not submit events, change account identity, close an account, initiate checkout or contact a payment provider. Browser email confirmation and payment outcomes require separate acceptance runs. The suite rejects the default production issuer, requires an explicit test issuer and skips entirely without the opt-in value. Default tests use synthetic local HTTP and OAuth fixtures.
