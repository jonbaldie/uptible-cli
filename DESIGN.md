# Events and billing

Event commands send the caller's notification ID, session ID, event ID and payload directly to the authenticated operations. The server owns receipt identity and processing. The client requires a processed receipt and never retries a write automatically. An uncertain outcome tells the customer to repeat the exact command.

Billing status is a read of one page for each of two independent lists. The client passes each opaque cursor through without interpreting it. The server owns eligibility and access decisions. This command performs no checkout operation.

Login retains its existing default scopes. Event and billing scopes are opt-in flags. An explicit `auth login --add` requests the union of the existing token scopes and the selected additions. The protected account endpoint validates each token and supplies the account ID. Under the credential lock, the client compares those IDs, saves the replacement, and revokes the old family. Failed or uncertain cleanup is reported. The client cannot upgrade a connection when it cannot determine the existing scopes or account identity.
