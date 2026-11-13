# Changelog

- Add a tag-triggered GitHub release with verified distributions and a rendered Homebrew formula.

- Add lead browsing and explicitly authorized permanent deletion.

- Add notification configuration and lifecycle commands, installation and activity readback.

## Unreleased

- Require Python 3.11 or later and filelock 4.2.10 or later. Update advisory-affected build tools and Linux cryptography without changing credential locking.

- Verify two byte-identical release builds from the committed source timestamp with hashed, platform-marked build and runtime inputs.
- Reject tampered dependency inputs and unexpected wheel contents before release.
- Authenticate Homebrew source archives against the build manifest and test installed module and dependency identity.
- Document the supported release matrix, dependency updates, and unperformed public publication and production sign-in steps.

- Retain recognized API error codes, safe validation field names and request IDs, including through uncertain-write recovery errors.
- Add explicitly authorized permanent notification deletion with confirmation and safe recovery for uncertain outcomes.
- Report damaged or interrupted deletion responses, including unreadable 4xx bodies, as uncertain without exposing response text or credentials.
- Report token-decoding failures safely and attempt to revoke an unusable new permission-upgrade grant.
- Give connection-specific local logout and login commands for refresh mismatches and unknown legacy accounts.
- Verify the selected account before saving any refreshed credential. Older connections that lack both an account ID and a usable account subject must reconnect.
- Reject permission upgrades that change the connected account or add unrequested scopes.
- Add an experimental account connection client with PKCE, rotating refresh credentials, account read, and local or server logout.
