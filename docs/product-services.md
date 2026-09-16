# Product services

PitchValue product services keep canonical prediction computation global and user data scoped.
Revision `20260916_0012` adds provider-neutral users, identities, opaque sessions, entitlement and
commerce evidence, and saved-selection references. It does not add `user_id` to prediction
snapshots or engine execution.

## Authentication

- Guest and email sessions are code-ready.
- Passwords use salted `scrypt`; plaintext passwords are never persisted.
- Access and refresh tokens are opaque, random values. Only SHA-256 token fingerprints are stored.
- Refresh rotates and revokes the previous session. Logout revokes the active session.
- Apple and Google use a verifier boundary and remain `EXTERNAL_CREDENTIAL_REQUIRED`.
- Password-reset delivery has a fail-closed provider boundary and remains an external
  email-service activation requirement; no reset success is fabricated.
- Guest-to-account linking is intentionally not automatic; migration semantics require a product
  decision.

## Entitlements and commerce

Entitlement is resolved from persisted, verified evidence. Mobile `premium=true` values are never
accepted as authority. Monthly, three-month, and annual identifiers have a provider-neutral
contract; prices and trial eligibility must come from the store. Verification and restore routes
fail closed until an approved store verifier is configured. No card data is stored.

## My Bets

Saved selections belong to one user and reference active, publication-eligible canonical
prediction evidence. Removing a record retains it as `REMOVED`; settled losses and withdrawals
remain auditable. Stake, currency, and saved odds are optional and are never synthesized. ROI is
null unless every settled monetary record has sufficient evidence in one currency.

Settlement uses completed canonical full-time results for 1X2, supported half-goal totals, BTTS,
Double Chance, and team totals. Scheduled, live, and postponed fixtures remain unsettled.
Cancelled fixtures are void. Abandoned fixtures and corrected final results require explicit
review; operator-specific house rules are not guessed.

## AI and Coupon Builder

AI accepts only active public prediction context and cannot create a prediction, probability, Bet
Score, edge, Final Check, or shadow fallback. The production adapter remains
`EXTERNAL_CREDENTIAL_REQUIRED`; deterministic adapters exist only for contract tests.

Coupon Builder reads only publication-eligible records, selects at most one market per match, and
returns fewer than requested with `INSUFFICIENT_ELIGIBLE_POOL`. SAFE, BALANCED, and BOLD only order
existing eligible evidence; they never lower publication gates.

## Activation

`GET /api/v1/product-services/readiness` reports code readiness separately from external credentials
and production activation. Scheduler and publication remain disabled. This code adds no paid
provider, monitoring, authentication, commerce middleware, or AI usage.
