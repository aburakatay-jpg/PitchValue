# My Bets production contract audit

Phase 5 found no production user-record or settlement contract in the current backend. Existing prediction snapshots are canonical public engine outputs, and shadow settlement is internal model-validation evidence; neither is a user-owned tracked record.

| Capability                            | Current classification      | Safe mobile behavior                           |
| ------------------------------------- | --------------------------- | ---------------------------------------------- |
| Save/unsave match                     | MISSING                     | No production Save control                     |
| Save/unsave prediction                | MISSING                     | No production Save control                     |
| Tracked user selection                | MISSING                     | My Bets reports tracking unavailable           |
| User ownership/session                | BLOCKED_BY_AUTH             | No unauthenticated personal endpoint calls     |
| Guest persistence/migration           | BLOCKED_BY_PRODUCT_DECISION | No AsyncStorage substitute                     |
| Active records                        | MISSING                     | Section remains visible with unavailable state |
| History records                       | MISSING                     | No fabricated result rows                      |
| WON/LOST/VOID/WITHDRAWN result states | MISSING                     | No client settlement mapping                   |
| Stake                                 | MISSING                     | No default or unit stake                       |
| Odds at save time                     | MISSING                     | Current odds are never substituted             |
| Return/payout and ROI inputs          | MISSING                     | No monetary performance metrics                |
| Changed/withdrawn analysis linkage    | MISSING                     | No historical relationship inferred            |

Production implementation requires user-owned save/list/mutation endpoints, semantic uniqueness, immutable original evidence, current-analysis linkage, authoritative settlement, stake/return semantics where applicable, and guest/account ownership decisions. Until then, My Bets is an honest contract-readiness surface rather than a fake personal ledger.
