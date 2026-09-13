# PitchValue mobile

Dark-first React Native foundation built with Expo SDK 57, TypeScript, and Expo Router. It contains UI shells and typed public API contract foundations; it does not yet contain production data fetching, prediction, purchase, authentication, advertising, notification, or analytics behavior.

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

## Expo Go and future native builds

The current dependency set is supported by Expo Go, including AsyncStorage for the one-time onboarding marker. No custom native code is present. A Development Build and EAS Build become appropriate when later approved work introduces StoreKit, production notifications, custom native modules, or release signing. No prebuild/eject step is currently required.

Application identifiers are intentionally omitted until production values are approved. The existing Expo config uses a clearly development-oriented URL scheme and does not claim App Store readiness.
