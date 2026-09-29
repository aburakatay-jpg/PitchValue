# PitchValue - App Store Privacy Preparation Matrix

**Status:** Preparation Document Only. Do not claim `APP_STORE_CONNECT_COMPLETE` until verified externally.

This document classifies the data collected by PitchValue for App Store Privacy Label declarations.

## 1. Email Address
- **Processed:** Yes.
- **Why:** Account registration, authentication, and communication.
- **Linked to Account:** Yes.
- **Deleted with Account:** Yes (canonical deletion), with minimum legal/commerce evidence retained.
- **Provider:** Third-party transactional email providers.

## 2. Account/User Identifier
- **Processed:** Yes.
- **Why:** Internal tracking and API relationships.
- **Linked to Account:** Yes.
- **Deleted with Account:** Yes (canonical deletion).

## 3. Push Token / Device Token
- **Processed:** Yes (Expo Push Tokens).
- **Why:** Match event push notifications.
- **Linked to Account:** Yes.
- **Deleted with Account:** Yes.
- **Provider:** Expo, Apple (APNs).

## 4. Purchases / Subscription-linked Information
- **Processed:** Yes.
- **Why:** Entitlement administration and feature gating.
- **Linked to Account:** Yes.
- **Deleted with Account:** Minimum commerce evidence is retained/pseudonymized for legal and audit compliance.

## 5. App Interactions (Saved Selections / Follows)
- **Processed:** Yes.
- **Why:** App functionality (My Bets tracking, Match following).
- **Linked to Account:** Yes.
- **Deleted with Account:** Yes.

## Deferred Provider Boundaries
- Apple production login physical verification: DEFERRED
- Apple provider revocation physical acceptance: DEFERRED
- Apple Hide My Email physical acceptance: DEFERRED
