# Client design

## HTTP failures

The request boundary recognizes fixed API and OAuth error codes, canonical UUID request IDs, and documented validation field names. It ignores arbitrary server messages and validation values. `Failure` carries only that safe context. Recovery wrappers preserve it when changing the local outcome to an uncertain write or refresh, so JSON can distinguish the recovery code from the server code. Text output includes the request ID for support. HTTP status comes from the response, not the body.

The existing read retry policy remains one extra request for HTTP 429 or 503 with a numeric `Retry-After` of at most two seconds; an absent header defaults to zero. Dates, longer delays and malformed values do not retry. The request timeout is 15 seconds and writes are not replayed automatically.

## Events and billing

Event commands send the caller's notification ID, session ID, event ID and payload directly to the authenticated operations. The server owns receipt identity and processing. The client requires a processed receipt and never retries a write automatically. An uncertain outcome tells the customer to repeat the exact command.

Billing status is a read of one page for each of two independent lists. The client passes each opaque cursor through without interpreting it. The server owns eligibility and access decisions. This command performs no checkout operation.

## Permission upgrades

Login retains its existing default scopes. Event, billing, lead deletion, and notification deletion scopes are opt-in flags. An explicit `auth login --add` requests the union of the existing token scopes and the selected additions. The protected account endpoint validates each token and supplies the account ID. Under the credential lock, the client compares those IDs and requires the approved scope set to match the requested union. It saves the replacement and revokes the old family. Failed or uncertain cleanup is reported. The client cannot upgrade a connection when it cannot determine the existing scopes or account identity. Token-decoding failures become structured errors. If a new grant cannot be decoded, the existing upgrade failure path attempts to revoke that grant and reports unconfirmed cleanup.

## Account continuity on refresh

The protected account endpoint supplies the account ID saved with a new or upgraded connection. Every refresh checks the refreshed token against that ID before saving it, including refreshes triggered by expiry or HTTP 401. A check only on deletion would miss an earlier refresh caused by a read. During a permission upgrade, the client also compares the old and refreshed scope sets.

For an older credential without a recorded account ID, the client uses the positive decimal account subject in its access token. If neither is available, it stops before refreshing. A mismatched or unverifiable refresh leaves the previous credential marked refresh-pending. Rotation may have consumed that credential, so recovery requires revocation and reconnection. The first identity or mismatch error gives local logout and login commands with the selected connection options. New opaque credentials can refresh when their protected account response supplies an integer ID.

## Notification deletion

The client validates the notification ID and requires confirmation before it opens the credential store. The server owns account and scope checks. The client makes one `DELETE` request and reports deletion only after HTTP 204. Network failures, damaged HTTP responses, server errors, and unexpected success responses leave the outcome unknown. The customer can read the notification before deciding whether to retry.

The shared request function reads and decodes an error body before retrying or handling its status. A complete empty body remains a status error, as does a valid JSON error. An unreadable or invalid nonempty body becomes a safe network failure. Structured HTTP failures retain their allowlisted codes and fields. The function does not print raw response text or request credentials. An interrupted deletion has an unknown outcome and is not replayed. An interrupted refresh may have consumed its credential, so the pending marker prevents a retry.
