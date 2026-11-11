# Uptible CLI

A preliminary client for connecting an account. The server routes used here are experimental and may change before a public API contract is published. This package is not a release and does not yet cover the complete Uptible API.

## Install

Python 3.10 or later and pip are required. From a checked-out revision, create an isolated environment and install the package.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/uptible --version
```

On Windows use `.venv\Scripts\python` and `.venv\Scripts\uptible`. Dependencies are declared in `pyproject.toml`; a locked, reproducible release and update channel have not been published. The CLI has been exercised on macOS only.

## Connect

Obtain the issuer origin and registered public client ID from the server operator. There is no client secret. Replace the example values in each command below with those supplied by the operator.

```sh
uptible --issuer https://example.test --client-id PUBLIC_CLIENT_ID auth login
uptible --issuer https://example.test --client-id PUBLIC_CLIENT_ID auth status
uptible --issuer https://example.test --client-id PUBLIC_CLIENT_ID account show
uptible --issuer https://example.test --client-id PUBLIC_CLIENT_ID auth logout
```

Login opens the system browser and listens temporarily on an ephemeral IPv4 loopback port. It requests `account:read`. The server issues a short-lived access credential and a rotating refresh credential when refresh is enabled. The client saves the rotated credential after use. The default logout revokes the server connection and then removes the local credential. `auth logout --local` removes the local credential only; the server connection may remain active and can be revoked on the account page.

Credentials use an available supported OS keyring backend. For a headless environment, explicitly choose a credential file in a private directory using `--credential-file /path/to/private/credentials`. On Unix the directory must be owned by the user and inaccessible to other users. Files are created with mode 0600 and replaced atomically. Keep the file private and back it up only with appropriate protection. A separate `--profile NAME` selects a separate connection in the keyring. Use a distinct credential file for each profile, issuer, and client ID. Do not copy a saved rotating refresh credential between machines; simultaneous reuse can revoke the whole token family.

Add `--json` before the command for machine-readable output. Command results are JSON objects on stdout and operational failures are objects on stderr with an `error.code` and `error.message`. Exit codes are 0 for success, 2 for usage or configuration, 3 for server/network failures, and 1 for other failures. Argument parser errors use argparse's standard text format. Output may include account information, but never the credentials. A failed or interrupted refresh can leave its outcome unknown. The client retains the old credentials and refuses to replay them, because replay can revoke the token family. Revoke the connection on the account page, run `auth logout --local`, and log in again. Login also attempts to revoke a newly issued grant if the account check or credential save fails. If revocation cannot be confirmed, revoke it on the account page before retrying.

For automated browser tests only, `auth login --browser-driver PATH` executes the given program with the authorization URL as its only argument. This is an explicit injection point and does not fall back to the system browser if it fails. Never use an untrusted driver.

## Current operation coverage

| Command | Experimental route or operation |
| --- | --- |
| `auth login` | `GET /oauth/authorize`, `POST /oauth/token`, `GET /api/v1/account` |
| `auth status` | `GET /api/v1/account`, with refresh as needed |
| `account show` | `GET /api/v1/account`, with refresh as needed |
| `auth logout` | `POST /api/v1/logout`, with refresh as needed |
| `auth logout --local` | Local credential removal only |

Notifications, leads, statistics, installation, events, billing, and other account operations are not implemented. Their documented public schemas and compatibility tests are prerequisites. No claim of full API parity is made.

## Development

```sh
python -m unittest discover -s tests -v
```

The tests use synthetic loopback services and an explicit browser driver. They do not contact a real account or launch a browser.
