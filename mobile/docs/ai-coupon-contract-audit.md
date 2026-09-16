# AI and Coupon Builder contract audit

PitchValue currently has no production AI/LLM route, explanation route, assistant session, conversation persistence, assistant rate-limit contract, or server-side AI entitlement enforcement. The public prediction list is the only partially supported, publication-safe context source. It does not expose an authoritative “best” ranking contract, public explanation evidence, or a stable public prediction identifier intended for assistant sessions.

The production backend also has no Coupon Builder route, approved Safe/Balanced/Bold algorithm, stable coupon-selection reference, 1–4 validation contract, or same-match deduplication response. The public prediction list can describe the eligible public pool, but mobile must not turn that list into an invented intelligent builder.

The Phase 6 UI therefore fails closed:

- all four canonical AI features are visible on a calm landing page;
- Today’s Best Value displays only the public endpoint order and never locally ranks it;
- Explain a Pick can select public context but cannot generate an explanation;
- Ask PitchValue accepts ephemeral draft text but cannot submit or fake an answer;
- Coupon Builder presents the three canonical risk labels and pool availability, but generates no coupon;
- empty pools stay empty, and unavailable services remain explicit;
- no conversation, selection, or coupon is written to AsyncStorage;
- no shadow or unpublished record, mock fallback, local Bet Score, edge, agreement, or prediction is used.

## Contract classification

| Capability                           | Classification              | Safe mobile behavior                                  |
| ------------------------------------ | --------------------------- | ----------------------------------------------------- |
| AI explanation endpoint              | MISSING                     | Explanation unavailable                               |
| Structured assistant context         | MISSING                     | Show selected public fields only                      |
| Ask PitchValue endpoint              | MISSING                     | Ephemeral input; submit disabled                      |
| Conversation/session persistence     | MISSING                     | No history or storage claim                           |
| Public prediction pool               | PARTIALLY_SUPPORTED         | Read-only `/api/v1/predictions`                       |
| Today’s Best Value ordering          | BLOCKED_BY_PRODUCT_DECISION | Preserve server order; do not call it a computed rank |
| AI authentication                    | BLOCKED_BY_AUTH             | No identity or session invented                       |
| AI entitlement enforcement           | BLOCKED_BY_ENTITLEMENT      | One presentation boundary; no access claim            |
| Coupon Builder endpoint              | MISSING                     | Builder unavailable                                   |
| Coupon eligible pool                 | PARTIALLY_SUPPORTED         | Count only public predictions                         |
| Coupon risk semantics                | BLOCKED_BY_PRODUCT_DECISION | Presentation labels only                              |
| Stable coupon prediction reference   | MISSING                     | No generated or saved coupon                          |
| Selection validation / deduplication | MISSING                     | State requirement; generate nothing                   |

Production enablement requires server-owned grounding, refusal policy, prompt-injection controls, public-safe structured evidence, authoritative “best” and risk semantics, stable selection/version references, bounded validation/deduplication, server-side entitlement enforcement, and rate limiting. Data retention and conversation-history behavior also require an explicit product/privacy decision.
