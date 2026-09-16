# PitchValue physical iPhone acceptance checklist

This checklist defines the remaining real-device acceptance work. It does not claim that any physical-device check has been completed. Record the device model, iOS version, build type, date, tester, and result for every run.

Test at least one compact-width iPhone, one standard modern iPhone, and one Pro Max-class iPhone. Repeat the critical paths with large Dynamic Type, VoiceOver, Reduce Motion, light/dark system settings, poor connectivity, and airplane mode where applicable.

## Install and startup

- Clean install the application and confirm the launch background remains `#08111F` with no white flash.
- Confirm the current generic splash placeholder is not accepted as the final branded asset.
- Verify 18+ confirmation appears before any tutorial or product content.
- Select Exit and confirm PitchValue remains locked rather than routing into Today.
- Accept the age gate, complete all three tutorial pages, and reach Today without creating an account.
- Reinstall and test Skip after age confirmation; it must open Today.
- Relaunch after completion and confirm there is no age-gate, tutorial, or Today route flash while storage loads.
- Corrupt or clear first-launch storage in a development build and verify the flow fails closed to 18+.

## Safe areas and device classes

- Verify compact, standard, and Pro Max width classes in portrait orientation.
- Verify notch and Dynamic Island spacing on every route.
- Verify bottom-tab content and modal actions remain above the home indicator.
- Confirm stack screens do not have doubled top spacing below the native header.
- Confirm no primary action is obscured by the keyboard, bottom tabs, or home indicator.

## Today

- Load a real successful fixture response and confirm kickoff order is chronological.
- Pull to refresh and confirm retained content remains visible after a refresh failure.
- Verify successful empty, provider unavailable, stale, DATA_INSUFFICIENT, and no-public-analysis states.
- Verify long team and competition names wrap without losing fixture identity.
- Open Match Detail and return; confirm normal back navigation and assess list-position retention.
- Confirm every card uses its canonical match ID and no first-record fallback exists.

## Explore

- Verify the valid empty state contains no sample prediction.
- In explicit development preview mode only, verify populated cards and navigation.
- Confirm production failures never activate development fixtures.
- Verify Bet Score null remains `Score unavailable`, edge remains server-provided, and order remains server-defined.
- Confirm missing fixture context is presented neutrally and no raw numeric fixture ID is shown.

## Match Detail and All Markets

- Verify scheduled and finished fixtures, long names, missing score, and authoritative final score.
- Verify no public analysis, DATA_INSUFFICIENT, and SCORE_INCOMPLETE states.
- Expand and collapse every market group; check touch targets and VoiceOver expanded state.
- Verify all V1 market families and every canonical market availability state.
- Check Final Check confirmed, changed, withdrawn, and unavailable copy.
- Verify stale, failed, and unavailable freshness remain distinct.
- Confirm missing statistics or one unavailable subsection never blanks valid fixture identity.
- Refresh after loading, force failure, and confirm retained content stays visible without appearing fresh.

## Auth and keyboard

- Verify Apple and Google controls announce disabled/unavailable state.
- Verify Continue as Guest remains visible and returns safely.
- Open Email, focus both fields, and verify keyboard avoidance and natural dismissal.
- Test invalid email and short password announcements with VoiceOver.
- Confirm secure password entry, return-key behavior, scrolling, and reachable disabled submit on compact devices.
- Confirm there is no SMS option and no control can simulate authentication.

## Profile, Paywall, and My Bets

- Verify all six canonical Profile groups and long labels at large Dynamic Type.
- Open My Bets from Track Record and verify Active, History, and Performance selected states.
- Confirm unavailable sections are not presented as successful empty personal records.
- Verify no fake ROI, stake, result, settlement, subscription date, or identity.
- Open and close the Paywall; verify close remains reachable.
- Verify plan names, benefit wrapping, unavailable localized prices, disabled purchase/restore, and no unconditional trial.

## AI and Coupon Builder

- Verify all four canonical feature cards and the single Premium boundary.
- Open Today’s Best Value with empty and populated public pools; confirm published order is preserved.
- Open Explain a Pick and confirm unavailable explanation behavior.
- Enter a long multiline Ask PitchValue draft; verify the input remains above the keyboard and Send remains disabled.
- Verify Safe, Balanced, and Bold selected-state announcements.
- Confirm zero and insufficient pools remain honest, no coupon is generated, and no Save or bookmaker action exists.

## Unknown routes and navigation

- Open an unknown route and verify the dark branded unavailable screen, accessible heading, and Return to Today action.
- Verify Today and Explore return correctly from Match Detail.
- Verify Profile → Auth → Guest/back, Profile → My Bets, Paywall close/back, and AI in-screen feature selection.
- Verify invalid Match Detail IDs never crash or fall back to development data.

## Accessibility

- Navigate every major route with VoiceOver in visual reading order.
- Confirm headings, buttons, tabs, selected/disabled/expanded states, form labels, errors, stale warnings, Final Check, and Premium boundary announcements.
- Confirm decorative tab initials, disclosure glyphs, onboarding dots, and skeletons do not create noise.
- Test large accessibility text sizes; all content and actions must remain reachable by scrolling.
- Enable Reduce Motion and confirm no required information depends on animation.
- Inspect OLED contrast for secondary text, disabled controls, badges, warnings, placeholders, and legal/risk copy.
- Confirm status is always conveyed by text, not color alone.
- Confirm interactive targets remain comfortably tappable.

## Release evidence

- Capture screenshots for successful, empty, unavailable, stale, and locked states without fabricating production data.
- Record any clipping, overlap, focus loss, route reset, stale-state ambiguity, or screen-reader issue with reproduction steps.
- Do not mark physical-device acceptance complete until all critical defects are fixed and rerun across the target matrix.
