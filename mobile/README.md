# PitchValue mobile

Dark-first React Native client built with Expo SDK 57, TypeScript, and Expo Router. Today, Explore, and Match Detail use typed read-only public API contracts. The mobile app does not calculate predictions, edge, Bet Score, publication decisions, or model agreement; it does not contain purchase, authentication, advertising, notification, or analytics behavior.

## Requirements

- Node.js 22.13 or newer (Node 24.16 was used for this foundation)
- npm 11
- Expo Go on a physical iPhone for early preview

## Setup and commands

```powershell
cd mobile
npm install
npm start
```

Scan the QR code with the iPhone camera and open it in Expo Go while the phone and PC can reach each other. Use `npm run web` for a browser preview. Run `npm run typecheck`, `npm run lint`, `npm run format:check`, and `npm test` for validation.

Copy `.env.example` to a local `.env` only when overriding the API endpoint. `EXPO_PUBLIC_API_BASE_URL` is public client configuration: never put credentials, signing keys, database passwords, service-role keys, or other secrets in any `EXPO_PUBLIC_*` variable.

Synthetic fixture previews are disabled by default. They require both a development build and the explicit `EXPO_PUBLIC_ENABLE_MOCK_DATA=true` flag. Production builds ignore this flag and fail closed to honest empty/unavailable states; API failures never activate mock data.

First launch is a fail-closed two-stage flow: an 18+ confirmation followed by exactly three tutorial pages. Guest access then opens Today without account creation. Separate, strictly validated AsyncStorage markers preserve age confirmation and tutorial completion; the exact legacy completion marker remains supported for users of the earlier combined flow.

Apple and Google account controls are honest disabled presentation shells. The Email route provides accessible form and validation foundations but cannot submit until account/session endpoints exist. Premium presentation uses App Store-owned price and trial placeholders; purchase and restore controls remain disabled. No local identity, entitlement, transaction, or trial is fabricated.

Today reads chronological fixtures from `GET /api/v1/fixtures/today`. Explore reads only publication-eligible analysis from `GET /api/v1/predictions`. Match Detail reads the canonical fixture, public analysis, V1 market states, Final Check, persisted statistics, and freshness from `GET /api/v1/matches/{match_id}`. Missing analysis and unavailable sections remain explicit and never activate shadow or mock fallbacks. The small public-data hook aborts superseded requests, retains successful data during a failed refresh, and never changes backend freshness semantics. Device-offline detection is intentionally not inferred from generic request failures.

## Expo Go and future native builds

The current dependency set is supported by Expo Go, including AsyncStorage for the one-time onboarding marker. No custom native code is present. A Development Build and EAS Build become appropriate when later approved work introduces StoreKit, production notifications, custom native modules, or release signing. No prebuild/eject step is currently required.

Application identifiers are intentionally omitted until production values are approved. The existing Expo config uses a clearly development-oriented URL scheme and does not claim App Store readiness.

Physical iPhone acceptance remains outstanding; use [the Phase 4 checklist](docs/physical-device-checklist.md) rather than treating simulator or automated tests as device approval. The approved PitchValue splash/wordmark artwork is not present, so the native splash currently uses only the canonical dark background and requires the approved asset before brand acceptance.
