# Changelog

- Add a tag-triggered GitHub release with verified distributions and a rendered Homebrew formula.

- Add lead browsing and explicitly authorized permanent deletion.

- Add notification configuration and lifecycle commands, installation and activity readback.

## Unreleased

- Add explicitly authorized permanent notification deletion with confirmation and safe recovery for uncertain outcomes.
- Report damaged or interrupted deletion responses as uncertain without exposing response text or credentials.
- Verify the selected account before saving any refreshed credential. Older connections without a known account ID must reconnect.
- Reject permission upgrades that change the connected account or add unrequested scopes.
- Add an experimental account connection client with PKCE, rotating refresh credentials, account read, and local or server logout.
