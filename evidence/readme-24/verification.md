# Post-launch README draft evidence

Source candidate: bbe1029fe96c717209f6d2832d2c1c1aa2bdecbf.
Base: ca8869e922cf58c6804592a974c2a4cb2ffc9774.

Only README.md changes. `git diff --check` exits 0. Independent Gemini 4 Argon Medium review returns PASS+NOTES for draft preparation. The Homebrew command, virtual environment description, update command and production login default match the formula renderer and release workflow.

The complete before/after diff is attached as `readme.patch` beside this report. It removes stale availability statements in Install, Connect your account, API compatibility, Current limitations and Release.

This is a future post-Go README. No release publication, public formula availability, clean macOS installation or production authentication is established by this evidence. Issue24 remains open. Keep the PR draft until CLI v0.1.0 and the formula are published and the clean macOS install plus production authentication checks pass. There is no executable change requiring a new runtime test.
