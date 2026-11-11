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

This installs from the checkout. There is no published release or update channel yet. The CLI has been exercised on macOS only.

## Connect your account

This early preview requires an issuer origin and a registered public client ID from your server operator. You do not need a client secret. [Issue #7](https://github.com/jonbaldie/uptible-cli/issues/7) tracks login without this manual configuration. Replace the example values below with the values for your server:

```sh
export UPTIBLE_ISSUER="https://example.test"
export UPTIBLE_CLIENT_ID="PUBLIC_CLIENT_ID"
uptible --issuer "$UPTIBLE_ISSUER" --client-id "$UPTIBLE_CLIENT_ID" auth login
```

The CLI opens your browser for authorization and listens for the response on a temporary loopback port. Approve access in the browser. The command then displays your account.

Use the same issuer and client ID to check your connection or view the account:

```sh
uptible --issuer "$UPTIBLE_ISSUER" --client-id "$UPTIBLE_CLIENT_ID" auth status
uptible --issuer "$UPTIBLE_ISSUER" --client-id "$UPTIBLE_CLIENT_ID" account show
```

When refresh is enabled on the server, the CLI refreshes an expired access credential automatically and saves the rotated refresh credential.

## Disconnect

Revoke the server connection and remove the saved local credential:

```sh
uptible --issuer "$UPTIBLE_ISSUER" --client-id "$UPTIBLE_CLIENT_ID" auth logout
```

To forget the local credential without revoking the server connection, use `auth logout --local`. The server connection may remain active. Revoke it on your account page if needed.

## Credential storage

The CLI uses an available supported operating-system keyring backend. To use a private file instead, add `--credential-file /path/to/private/credentials` before the command on every invocation. On Unix, the directory must be owned by you and inaccessible to other users. The CLI creates the file with mode `0600`. Keep it private.

Use `--profile NAME` before the command to select a separate keyring connection. For file storage, use a distinct file for each profile, issuer, and client ID. Do not copy a rotating refresh credential between machines. Simultaneous use can revoke the token family.

## Recover a connection

If login reports that a grant may have been created or that revocation could not be confirmed, inspect your account connections and revoke any unintended grant before retrying.

If refresh fails or is interrupted, its outcome can be unknown. The CLI retains the old credential and refuses to replay it. Revoke the connection on your account page, run `auth logout --local`, and log in again with the same issuer, client ID, and storage options.

## Output and help

Add `--json` before the command for machine-readable output. Results are JSON objects on standard output. Operational errors are JSON objects on standard error with `error.code` and `error.message`. Argument parser errors use standard text even with `--json`. Output can contain account information, but not credentials.

Exit codes are `0` for success, `2` for usage or configuration errors, `3` for server or network failures, and `1` for other failures. Use `uptible --help` and command-specific help such as `uptible auth login --help` for options.

## Current limitations

The connection routes are experimental and may change before a public API contract is published. Notifications, leads, statistics, installation, events, billing, and other account operations are not implemented. Full command coverage, server compatibility, reproducible release dependencies, hosted CI, and distribution remain open in [issue #1](https://github.com/jonbaldie/uptible-cli/issues/1).

## Development

Run the synthetic loopback tests with `python -m unittest discover -s tests -v`. The tests use an explicit browser driver and do not open a system browser or contact a real account.
