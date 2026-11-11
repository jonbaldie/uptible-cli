# Events and billing

Event commands send the caller's notification ID, session ID, event ID and payload directly to the authenticated operations. The server owns receipt identity and processing. The client requires a processed receipt and never retries a write automatically. An uncertain outcome tells the customer to repeat the exact command.

Billing status is a read of one page for each of two independent lists. The client passes each opaque cursor through without interpreting it. The server owns eligibility and access decisions. This command performs no checkout operation.

Login retains its existing default scopes. Event and billing scopes are opt-in flags. Existing connection upgrades need account identity verification and safe grant cleanup. Issue #18 tracks that work. This slice does not alter stored credentials when an existing connection attempts login.
