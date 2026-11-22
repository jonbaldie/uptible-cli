"""Tandem integration: real CLI subprocess against a real Uptible server.

Opt-in; skipped unless UPTIBLE_TANDEM=1 with an explicitly provisioned,
disposable test server and credential file. Never runs against production:
production issuers are refused before any login starts.

Provisioning (disposable local server, see tests/tandem_seed.php):
  1. Generate RSA keys and copy them to the server checkout's
     code/storage/oauth-private.key / oauth-public.key with mode 600.
  2. Seed a throw-away sqlite database with tests/tandem_seed.php
     (TANDEM_SERVER_DIR=<server>/code, synthetic client id, users
     alpha/bravo with lifetime grants and charlie without).
  3. Serve the server checkout on 127.0.0.1 with OAUTH_ENABLED=true and
     OAUTH_ISSUER/OAUTH_AUDIENCE set to that origin.
  4. Log in once with the automated browser driver to mint a credential
     file, e.g.:
       UPTIBLE_TANDEM=1 TANDEM_ISSUER=http://127.0.0.1:8765 \\
       TANDEM_CLIENT_ID=11111111-1111-4111-8111-111111111111 \\
       TANDEM_CREDENTIAL_FILE=/tmp/tandem/creds.json \\
       python -m unittest tests.test_tandem_integration -v

The full OAuth login flow (PKCE, consent, token exchange, logout
revocation) is covered by TandemLoginFlow when TANDEM_BROWSER_DRIVER,
TANDEM_EMAIL and TANDEM_PASSWORD are set. Refresh-token rotation is
not exercised here (access tokens live ~15 minutes); it was verified
by manually expiring a credential copy and confirming the CLI
refreshes against the real server, and by a direct refresh-grant
replay returning invalid_grant.

Rate limits are real: management reads/writes allow 60 requests per
minute and token exchange 30 per minute per account. If a run reports
rate_limited, wait a minute (without other traffic) and retry; do not
raise server limits to make the suite pass.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.parse
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PRODUCTION_HOSTS = {
    "uptible.com",
    "www.uptible.com",
    "uptible.fly.dev",
    "dev-uptible.fly.dev",
}


def tandem_env():
    if os.environ.get("UPTIBLE_TANDEM") != "1":
        return None
    issuer = os.environ.get("TANDEM_ISSUER", "")
    client_id = os.environ.get("TANDEM_CLIENT_ID", "")
    credential_file = os.environ.get("TANDEM_CREDENTIAL_FILE", "")
    host = (urllib.parse.urlsplit(issuer).hostname or "").lower().rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        pass
    if host in PRODUCTION_HOSTS or host.endswith(".uptible.com"):
        raise AssertionError("Tandem test refused: production issuer")
    if not (issuer and client_id and credential_file and os.path.isfile(credential_file)):
        return None
    return issuer, client_id, credential_file


def run_cli(issuer, client_id, credential_file, *args, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    cmd = [
        sys.executable,
        "-m",
        "uptible_cli",
        "--json",
        "--issuer",
        issuer,
        "--client-id",
        client_id,
        "--credential-file",
        credential_file,
        *args,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=ROOT, env=env)
    # Success JSON goes to stdout; error JSON goes to stderr.
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        payload = None
    return proc.returncode, payload, proc.stdout, proc.stderr


@unittest.skipUnless(tandem_env(), "requires UPTIBLE_TANDEM=1 with provisioned issuer, client and credential file")
class TandemCommandMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.issuer, cls.client_id, cls.credential_file = tandem_env()

    def cli(self, *args, **kwargs):
        return run_cli(self.issuer, self.client_id, self.credential_file, *args, **kwargs)

    def test_account_status_and_read_commands(self):
        rc, payload, _, _ = self.cli("auth", "status")
        self.assertEqual(rc, 0, payload)
        self.assertTrue(payload["connected"])
        self.assertIn("email", payload["account"])

        status_email = payload["account"]["email"]
        rc, payload, _, _ = self.cli("account", "show")
        self.assertEqual(rc, 0, payload)
        self.assertTrue(payload["email"])
        self.assertEqual(payload["email"], status_email)

        for args in (
            ("stats", "show"),
            ("installation", "show"),
            ("billing", "status"),
            ("notifications", "list", "--limit", "20"),
            ("leads", "list", "--limit", "20"),
        ):
            with self.subTest(command=args):
                rc, payload, _, err = self.cli(*args)
                self.assertEqual(rc, 0, f"{args}: {payload} {err}")
                self.assertIsInstance(payload, dict)

        rc, listing, _, _ = self.cli("notifications", "list", "--limit", "1")
        self.assertEqual(rc, 0, listing)
        self.assertTrue(listing["data"], "seeded account should own a notification")
        nid = listing["data"][0]["id"]
        rc, payload, _, _ = self.cli("notifications", "show", str(nid))
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["id"], nid)
        rc, payload, _, _ = self.cli("notifications", "activity", str(nid))
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["notification_id"], nid)

    def test_notification_lifecycle_with_revision_conflict(self):
        key = "tandem-" + uuid.uuid4().hex
        rc, created, _, _ = self.cli("notifications", "create", "--idempotency-key", key, "--message", "Tandem draft")
        self.assertEqual(rc, 0, created)
        nid = created["id"]
        self.assertEqual(created["state"], "draft")
        # Idempotent replay returns the same draft.
        rc, replay, _, _ = self.cli("notifications", "create", "--idempotency-key", key, "--message", "Tandem draft")
        self.assertEqual(rc, 0, replay)
        self.assertEqual(replay["id"], nid)
        # Revision-guarded edit succeeds once, then conflicts on stale revision.
        rc, edited, _, _ = self.cli("notifications", "edit", str(nid), "--revision", "1", "--message", "Tandem edited")
        self.assertEqual(rc, 0, edited)
        self.assertEqual(edited["revision"], 2)
        rc, conflict, _, _ = self.cli("notifications", "edit", str(nid), "--revision", "1", "--message", "Stale")
        self.assertEqual(rc, 3, conflict)
        self.assertEqual(conflict["error"]["code"], "conflict")
        for action, expected in (("activate", "active"), ("deactivate", "inactive"), ("archive", "archived"), ("restore", "inactive")):
            rc, payload, _, _ = self.cli("notifications", action, str(nid))
            self.assertEqual(rc, 0, f"{action}: {payload}")
            self.assertEqual(payload["state"], expected)
        # Final delete is scope-dependent: allowed with notifications:delete,
        # cleanly forbidden without. Either way it must not error opaquely.
        rc, payload, _, _ = self.cli("notifications", "delete", str(nid), "--yes")
        if rc == 0:
            self.assertTrue(payload.get("deleted", True))
        else:
            self.assertEqual(rc, 3, payload)
            self.assertEqual(payload["error"]["code"], "forbidden")

    def test_events_are_idempotent(self):
        rc, listing, _, _ = self.cli("notifications", "list", "--limit", "1")
        self.assertEqual(rc, 0, listing)
        nid = listing["data"][0]["id"]
        session, event = "tandem-s-" + uuid.uuid4().hex[:8], "tandem-e-" + uuid.uuid4().hex[:8]
        rc, first, _, _ = self.cli("events", "capture", str(nid), "--session-id", session, "--event-id", event, "--email", "tandem@example.test", "--name", "Tandem")
        self.assertEqual(rc, 0, first)
        rc, second, _, _ = self.cli("events", "capture", str(nid), "--session-id", session, "--event-id", event, "--email", "tandem@example.test", "--name", "Tandem")
        self.assertEqual(rc, 0, second)
        self.assertEqual(first["receipt"], second["receipt"])
        rc, tracked, _, _ = self.cli("events", "track", str(nid), "--session-id", session, "--event-id", event + "-t")
        self.assertEqual(rc, 0, tracked)

    def test_missing_resources_are_not_found(self):
        for args in (("notifications", "show", "999999999"), ("leads", "show", "999999999")):
            rc, payload, _, _ = self.cli(*args)
            self.assertEqual(rc, 3, f"{args}: {payload}")
            self.assertEqual(payload["error"]["code"], "not_found")

    def test_server_validation_maps_to_fields(self):
        key = "tandem-bad-" + uuid.uuid4().hex
        rc, payload, _, _ = self.cli(
            "notifications", "create", "--idempotency-key", key, "--message", "X", "--custom-delay-x-seconds", "0"
        )
        self.assertEqual(rc, 3, payload)
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("custom_delay_x_seconds", payload["error"]["fields"])

    def test_lead_pagination_cursors_are_disjoint(self):
        rc, first, _, _ = self.cli("leads", "list", "--limit", "1")
        self.assertEqual(rc, 0, first)
        cursor = first.get("next_cursor")
        if not cursor:
            self.skipTest("fewer than two leads in fixture")
        rc, second, _, _ = self.cli("leads", "list", "--limit", "1", "--cursor", cursor)
        self.assertEqual(rc, 0, second)
        first_ids = {lead["id"] for lead in first["data"]}
        second_ids = {lead["id"] for lead in second["data"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_not_connected_exit_code(self):
        with tempfile.TemporaryDirectory(prefix="uptible-tandem-empty-") as directory:
            missing = os.path.join(directory, "creds.json")
            rc, payload, _, _ = run_cli(self.issuer, self.client_id, missing, "account", "show")
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["error"]["code"], "not_connected")


@unittest.skipUnless(
    tandem_env()
    and os.environ.get("TANDEM_BROWSER_DRIVER")
    and os.environ.get("TANDEM_EMAIL"),
    "requires UPTIBLE_TANDEM=1 plus TANDEM_BROWSER_DRIVER and TANDEM_EMAIL",
)
class TandemLoginFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.issuer, cls.client_id, _ = tandem_env()

    def test_full_oauth_login_refresh_logout(self):
        with tempfile.TemporaryDirectory(prefix="uptible-tandem-login-") as directory:
            credential_file = os.path.join(directory, "creds.json")
            env = {
                "TANDEM_EMAIL": os.environ["TANDEM_EMAIL"],
                "TANDEM_PASSWORD": os.environ.get("TANDEM_PASSWORD", "password123"),
            }
            rc, payload, out, err = run_cli(
                self.issuer,
                self.client_id,
                credential_file,
                "auth",
                "login",
                "--browser-driver",
                os.environ["TANDEM_BROWSER_DRIVER"],
                "--callback-timeout",
                "30",
                extra_env=env,
            )
            self.assertEqual(rc, 0, f"{payload} {out} {err}")
            self.assertTrue(payload["connected"])
            self.assertEqual(payload["account"]["email"], os.environ["TANDEM_EMAIL"])
            self.assertTrue(os.path.isfile(credential_file))

            rc, payload, _, _ = run_cli(self.issuer, self.client_id, credential_file, "account", "show")
            self.assertEqual(rc, 0, payload)
            self.assertEqual(payload["email"], os.environ["TANDEM_EMAIL"])

            rc, payload, _, _ = run_cli(self.issuer, self.client_id, credential_file, "auth", "logout")
            self.assertEqual(rc, 0, payload)
            self.assertFalse(payload["connected"])
            rc, payload, _, _ = run_cli(self.issuer, self.client_id, credential_file, "auth", "status")
            self.assertEqual(rc, 0, payload)
            self.assertFalse(payload["connected"])


class TandemProductionGuard(unittest.TestCase):
    def test_production_issuers_are_refused(self):
        for issuer in (
            "https://uptible.com",
            "https://uptible.com.",
            "https://www.uptible.com",
            "https://uptible.fly.dev",
            "https://dev-uptible.fly.dev",
        ):
            with self.subTest(issuer=issuer), unittest.mock.patch.dict(
                os.environ,
                {
                    "UPTIBLE_TANDEM": "1",
                    "TANDEM_ISSUER": issuer,
                    "TANDEM_CLIENT_ID": "synthetic",
                    "TANDEM_CREDENTIAL_FILE": __file__,
                },
                clear=True,
            ):
                with self.assertRaises(AssertionError):
                    tandem_env()


if __name__ == "__main__":
    unittest.main()
