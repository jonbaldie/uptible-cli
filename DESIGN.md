# Client design

## Events and billing

Event commands send the caller's notification ID, session ID, event ID and payload directly to the authenticated operations. The server owns receipt identity and processing. The client requires a processed receipt and never retries a write automatically. An uncertain outcome tells the customer to repeat the exact command.

Billing status is a read of one page for each of two independent lists. The client passes each opaque cursor through without interpreting it. The server owns eligibility and access decisions. This command performs no checkout operation.

## Permission upgrades

Login retains its existing default scopes. Event, billing, lead deletion, and notification deletion scopes are opt-in flags. An explicit `auth login --add` requests the union of the existing token scopes and the selected additions. The protected account endpoint validates each token and supplies the account ID. Under the credential lock, the client compares those IDs and requires the approved scope set to match the requested union. It saves the replacement and revokes the old family. Failed or uncertain cleanup is reported. The client cannot upgrade a connection when it cannot determine the existing scopes or account identity.

## Account continuity on refresh

The protected account endpoint supplies the account ID saved with a new or upgraded connection. Every refresh checks the refreshed token against that ID before saving it, including refreshes triggered by expiry or HTTP 401. A check only on deletion would miss an earlier refresh caused by a read. During a permission upgrade, the client also compares the old and refreshed scope sets.

For an older credential without a recorded account ID, the client uses the positive decimal account subject in its access token. If neither is available, it stops before refreshing. A mismatched or unverifiable refresh leaves the previous credential marked refresh-pending. Rotation may have consumed that credential, so recovery requires revocation and reconnection. New opaque credentials can refresh when their protected account response supplies an integer ID.

## Notification deletion

The client validates the notification ID and requires confirmation before it opens the credential store. The server owns account and scope checks. The client makes one `DELETE` request and reports deletion only after HTTP 204. Network failures, damaged HTTP responses, server errors, and unexpected success responses leave the outcome unknown. The customer can read the notification before deciding whether to retry.

The shared request function preserves structured HTTP failures and converts other request exceptions and interrupts into safe network failures. It does not print raw response text or request credentials. An interrupted deletion has an unknown outcome and is not replayed. An interrupted refresh may have consumed its credential, so the pending marker prevents a retry.
