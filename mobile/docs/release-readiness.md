# Mobile UX release-readiness matrix

This matrix separates code-ready UX from external launch dependencies. It does not certify physical-device behavior.

| Area                                 | Current classification                | Evidence / remaining work                                                                                    |
| ------------------------------------ | ------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Today                                | Code-ready                            | Real public API, chronological, retained refresh data, explicit empty/stale/error states                     |
| Explore                              | Code-ready with backend limitation    | Public-only and fail-closed; fixture context remains unavailable                                             |
| Match Detail / Markets / Final Check | Code-ready                            | Public contract only; sectional failure and nullable values preserved                                        |
| First launch                         | Code-ready with legal/asset blockers  | Fail-closed storage and guest flow; final legal content and approved splash absent                           |
| Auth                                 | Backend blocker                       | Honest disabled shells; no identity/session backend                                                          |
| Commerce                             | Backend blocker                       | Honest presentation; no store products, purchases, restore, or entitlement sync                              |
| My Bets                              | Backend blocker                       | Honest unavailable workspace; no user record or settlement contract                                          |
| AI                                   | Backend/product blocker               | Public context shell only; no explanation, session, refusal, rate-limit, or entitlement service              |
| Coupon Builder                       | Backend/product blocker               | Presentation only; no generation, risk semantics, stable references, validation, or deduplication            |
| Accessibility                        | Physical-device validation required   | Automated semantics improved; real VoiceOver, Dynamic Type, keyboard, and OLED checks outstanding            |
| Native branding                      | Asset blocker                         | Generic template assets remain; approved PitchValue splash/wordmark required                                 |
| Legal                                | Legal blocker                         | Final Terms, Privacy, Responsible Gambling, Support content/destinations required                            |
| Release configuration                | UX release blocker                    | Production API URL, iOS bundle ID, Android package, production URL scheme, signing/build metadata unresolved |
| Expo dependencies                    | Post-V1 / non-blocking for this batch | Eight SDK 57 packages are behind recommended patch versions                                                  |

## Release configuration placeholders

- `scheme` is still `pitchvalue-dev`.
- iOS `bundleIdentifier` is absent.
- Android `package` is absent.
- production API URL must be supplied explicitly; release builds fail closed when it is absent.
- approved icon and splash artwork are not installed.
- signing, store records, privacy metadata, support URL, and legal URLs remain external release work.

No camera, microphone, location, contacts, or photo-library permission is declared in `app.json`.
