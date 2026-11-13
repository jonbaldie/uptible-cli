# Command and browser capability reference

The management API uses `/api/v1`. The prerelease CLI is awaiting a pinned, published contract and a declared minimum compatible server release. This table records implemented commands and browser boundaries; it does not claim complete contract compatibility.

| Capability | Command | Protocol and completion |
| --- | --- | --- |
| Authorize a connection | `auth login` | System browser, PKCE S256, ephemeral IPv4 loopback callback. Browser and callback access are required. Device authorization is unsupported. |
| Inspect connection and account | `auth status`, `account show` | `GET /api/v1/account`; the server supplies the account identity. |
| Add sensitive permissions | `auth login --add` with selected flags | New browser consent. Email and deletion permissions require the current password in the browser. Failed or different-account upgrades retain the existing connection. |
| Revoke current grant | `auth logout` | `POST /api/v1/logout`, then local removal. `--local` removes only local storage. |
| Request email update | `account update --email ADDRESS` | `POST /api/v1/account/email-change`, with opt-in `account:email:write`. HTTP 202 and `confirmation_required` mean pending recipient confirmation. |
| Confirm email update | `account confirm-email` | Opens `/billing`. The authenticated browser posts the recipient code and current password to `/account/oauth-email-change/confirm`. `account show` reads the resulting identity. |
| Settings, connected clients and security | `account settings`, `account security` | Opens `/billing`. Password change, recovery, Google linking, connection revocation and closure remain browser actions. Closure requires password confirmation and soft-deletes the account; it is not a data purge. |
| Onboarding | `account onboarding` | Opens `/onboarding`. Registration, sign-in, email verification and password reset use browser authentication routes. |
| Notification configuration | `notifications list`, `show`, `create`, `edit` | Collection GET/POST and item GET/PUT under `/api/v1/notifications`. `edit` is the update command. Create uses a caller-selected idempotency key; edits require the current revision. |
| Notification lifecycle | `notifications activate`, `deactivate`, `archive`, `restore` | Explicit target-state PUT on the selected notification action. |
| Permanent notification deletion | `notifications delete ID` | Item DELETE, explicit confirmation and separately consented `notifications:delete`. Only HTTP 204 confirms deletion. |
| Notification preview | `notifications preview ID` | Verifies API ownership, then opens `/notifications`. Find the item across pages and select Preview. The CLI cannot select the modal, bind the browser account or confirm rendering. |
| Lead reads and deletion | `leads list`, `show`, `delete` | `/api/v1/leads`; notification/date filters and opaque cursors. UTC `--from` is inclusive and `--until` is exclusive. Deletion requires confirmation and opt-in `leads:delete`. |
| Dashboard statistics | `stats show` | `GET /api/v1/statistics`; fixed inclusive rolling hour and 24-hour UTC windows returned with `as_of`. Arbitrary windows and other time zones are unsupported by the server. |
| Installation and tracking status | `installation show`, `installation open` | `GET /api/v1/installation` or browser `/install`. The embed and public collectors use separate browser protocols. |
| Notification activity | `notifications activity ID` | Item `/activity` GET. |
| Capture and track | `events capture`, `events track` | Notification `/capture` or `/track` POST with separately consented `events:write`; exact stable IDs and payload identify retries. A `processed` receipt confirms processing. No async status operation is documented. |
| Billing status and history | `billing status` | `GET /api/v1/billing`, opt-in `billing:read`. Each opaque cursor traverses its own bounded order or claim list. |
| Lifetime checkout | `billing checkout` | Opens `/billing` to review the single $99 lifetime offer. The browser submits authenticated CSRF-protected `POST /pay` after user action. Opening the page does not initiate or confirm a purchase. |
| Payment reconciliation and claims | `billing open` | Browser `/billing`, with form confirmations. These are browser and provider protocols, not management write operations. |
| Receipt or portal operations | `billing status`, `billing open` | The documented history and claim forms are available. There is no documented management receipt download, recurring subscription or provider portal API. Retired Stripe card, invoice and cancellation routes have no CLI replacement. |
| Provider updates and internal processing | No customer CLI command | Provider webhooks, background jobs and private storage are outside the management API. |

Every browser command validates the selected issuer origin and uses a fixed same-origin path. URLs contain no bearer token, password, recipient code, email address or account selector. The HTTP development exception is limited to `127.0.0.1`.

The browser has a separate session and may belong to another account. Compare its signed-in identity with `account show` before submitting a form. Handoff JSON explicitly returns `completed: false` and `account_binding_verified: false`. The service supplies no account-bound handoff token or return receipt. Opening a page cannot establish account continuity or completion. Commands that need the changed state must read it through the API afterwards.

For security changes, follow the browser's current-password and recipient-code checks. Invalid, expired, replaced, foreign or already used email codes leave identity unchanged. An email request has an unknown outcome after a damaged response or server failure; inspect the mailbox and account page before requesting another code. Requests are never automatically replayed.
