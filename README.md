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

This is a prerelease. The public service and distribution are not yet available. Once the service is available, run:

```sh
uptible auth login
uptible auth status
uptible account show
```

The CLI opens your browser for authorization and listens for the response on a temporary loopback port. Approve access in the browser. The command then displays your account. If your browser cannot open, set a default browser and retry. A browser and a loopback connection are required.

When refresh is enabled on the server, the CLI refreshes an expired access credential automatically and saves the rotated refresh credential.

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

Use the returned ID and revision in place of the example values. Edit requires the current revision and a message. Omitted settings remain unchanged. If an edit conflicts, fetch the notification, review the current settings and revision, and decide whether to retry. Use `--help` on create or edit for configuration options. Activation, installation and activity require lifetime access. `deactivate`, `archive`, and `restore` are also available. Listing returns `next_after`; pass that value as `--after` for the next page. Permanent deletion is not available in this version.

Existing connections made before these commands may lack their permissions. If a command returns HTTP 403, check lifetime access. If the connection lacks permissions, log out and log in again to approve the expanded non-destructive permissions.

## Disconnect

Revoke the server connection and remove the saved local credential:

```sh
uptible auth logout
```

To forget the local credential without revoking the server connection, use `auth logout --local`. The server connection may remain active. Revoke it on your account page if needed.

## Credential storage

The CLI uses an available supported operating-system keyring backend. To use a private file instead, add `--credential-file /path/to/private/credentials` before the command on every invocation. On Unix, the directory must be owned by you and inaccessible to other users. The CLI creates the file with mode `0600`. Keep it private.

For an alternate service, pass `--issuer` and its registered `--client-id` before every command. The explicit flags override the built-in defaults; environment variables do not select a connection. Use `--profile NAME` before the command to select a separate keyring connection. For file storage, use a distinct file for each profile, issuer, and client ID. Do not copy a rotating refresh credential between machines. Simultaneous use can revoke the token family.

## Recover a connection

If login reports that a grant may have been created or that revocation could not be confirmed, inspect your account connections and revoke any unintended grant before retrying.

If refresh fails or is interrupted, its outcome can be unknown. The CLI retains the old credential and refuses to replay it. Revoke the connection on your account page, run `auth logout --local`, and log in again with the same issuer, client ID, and storage options.

## Output and help

Add `--json` before the command for machine-readable output. Results are JSON objects on standard output. Operational errors are JSON objects on standard error with `error.code` and `error.message`. Argument parser errors use standard text even with `--json`. Output can contain account information, but not credentials.

Exit codes are `0` for success, `2` for usage or configuration errors, `3` for server or network failures, and `1` for other failures. Use `uptible --help` and command-specific help such as `uptible auth login --help` for options.

## Current limitations

The connection routes are experimental and may change before a public API contract is published. Leads, statistics, events, billing, permanent notification deletion, and other account operations are not implemented. Full command coverage, server compatibility, reproducible release dependencies and distribution remain open in [issue #1](https://github.com/jonbaldie/uptible-cli/issues/1).

## Development

Run the synthetic loopback tests with `python -m unittest discover -s tests -v`. The tests use an explicit browser driver and do not open a system browser or contact a real account.

To build and verify the committed checkout as installable distributions, run:

```sh
python3 scripts/verify-artifact.py /tmp/uptible-verified
```

The output directory must be empty and the checkout clean. The command builds a wheel and source distribution from the commit, checks their file lists, installs the wheel in a fresh temporary environment, and runs the synthetic tests outside the checkout. It records the commit and SHA-256 digests alongside the artifacts. It downloads pinned build tools and the package's runtime dependencies from the configured Python package index. CI runs this check on Linux with Python 3.10 and 3.14 and retains the artifacts. These checks do not establish operating-system keyring support, deployed-service compatibility, or a release channel. Runtime dependencies are not locked for release; full distribution and command coverage remain in issue #1.
