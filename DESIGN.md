# Client design

## Events and billing

Event commands send the caller's notification ID, session ID, event ID and payload directly to the authenticated operations. The server owns receipt identity and processing. The client requires a processed receipt and never retries a write automatically. An uncertain outcome tells the customer to repeat the exact command.

Billing status is a read of one page for each of two independent lists. The client passes each opaque cursor through without interpreting it. The server owns eligibility and access decisions. This command performs no checkout operation.

## Permission upgrades

Login retains its existing default scopes. Event, billing, lead deletion, and notification deletion scopes are opt-in flags. An explicit `auth login --add` requests the union of the existing token scopes and the selected additions. The protected account endpoint validates each token and supplies the account ID. Under the credential lock, the client compares those IDs and requires the approved scope set to match the requested union. It saves the replacement and revokes the old family. Failed or uncertain cleanup is reported. The client cannot upgrade a connection when it cannot determine the existing scopes or account identity.

If the old access credential has expired, the client reads its account ID from the token subject before refreshing. It compares that ID with the protected account response and compares the old and refreshed scopes before saving the refresh result. A mismatched or unverifiable refresh leaves the previous credential marked refresh-pending. Rotation may have consumed that credential, so recovery requires revocation and reconnection.

## Notification deletion

The client validates the notification ID and requires confirmation before it opens the credential store. The server owns account and scope checks. The client makes one `DELETE` request and reports deletion only after HTTP 204. Network failures, server errors, and unexpected success responses leave the outcome unknown. The customer can read the notification before deciding whether to retry.
