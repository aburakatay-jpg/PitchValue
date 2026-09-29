# PitchValue - Google Play Data Safety Preparation Matrix

**Status:** Preparation Document Only. Do not claim `PLAY_CONSOLE_CONFIGURATION_NOT_YET_VERIFIED` is complete until verified externally.

This document classifies the data collected by PitchValue for Google Play Data Safety declarations.

## 1. Account Data / Email
- **Collected:** Yes.
- **Why:** App functionality, account management.
- **Linked:** Yes.
- **Deletion:** Deleted upon request, retaining minimum necessary commerce evidence.

## 2. Push Tokens
- **Collected:** Yes (Expo Push Tokens).
- **Why:** Match notifications.
- **Linked:** Yes.
- **Deletion:** Deleted with the account.
- **Deferred:** FCM production activation is currently DEFERRED.

## 3. Purchase / Subscription Evidence
- **Collected:** Yes.
- **Why:** Entitlement administration.
- **Linked:** Yes.
- **Deletion:** Minimal evidence is retained for legal/audit purposes upon account deletion.

## 4. App Activity (Saved Selections / Follows)
- **Collected:** Yes.
- **Why:** App functionality.
- **Linked:** Yes.
- **Deletion:** Erased upon account deletion.

## 5. Deletion Request Path
- **Status:** TECHNICAL_RESOURCE_READY
- **Resource:** The public external web resource (`/account/delete`) handles deletion requests directly, independent of app installation.

## Deferred Provider Boundaries
- Google production login physical verification: DEFERRED
- Google provider cleanup physical acceptance: DEFERRED
- Android FCM production activation: DEFERRED
