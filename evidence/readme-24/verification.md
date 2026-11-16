# Post-launch README draft evidence

Source candidate: eab617d964e0615c97dcd3d9ff0f356ca49faac4.
Base: 7adbdbaa4aa64284aee5fe692d34ed7d66e78164.

Only README.md changes. The draft preserves the contract 1.2.0 pin, 1.1.0 compatibility when the host appearance option is omitted, and the advertised 1.2.0 requirement for explicit appearance changes. The completion example now uses `--no-d`, which returns only `--no-display-maps-only` from the current CLI. `git diff --check` exits 0.

The complete before/after diff is attached as `readme.patch` beside this report. It removes stale availability statements in Install, Connect your account, API compatibility, Current limitations and Release. The Homebrew command, virtual environment description, update command and production login default match the formula renderer and release workflow.

Independent Gemini 4 Argon Medium review passed the integration before the one-character completion correction. A fresh GPT-6.1 Sol review of the final candidate returned PASS+NOTES for draft preparation through the native Codex agent runtime.

This is a future post-Go README. No release publication, public formula availability, clean macOS installation or production authentication is established by this evidence. Issue #24 remains open. Keep PR #32 draft until CLI v0.1.0 and the formula are published and the clean macOS README install plus production authentication checks pass. There is no executable behavior change.
