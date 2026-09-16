export type AssistantContractCapability =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'MISSING'
  | 'BLOCKED_BY_AUTH'
  | 'BLOCKED_BY_ENTITLEMENT'
  | 'BLOCKED_BY_PRODUCT_DECISION';

export const assistantFeatures = [
  'Coupon Builder',
  'Today’s Best Value',
  'Explain a Pick',
  'Ask PitchValue',
] as const;

export type AssistantFeature = (typeof assistantFeatures)[number];

export const assistantContract = {
  explanationEndpoint: 'PARTIALLY_SUPPORTED',
  explainPick: 'PARTIALLY_SUPPORTED',
  askPitchValue: 'PARTIALLY_SUPPORTED',
  structuredContext: 'SUPPORTED',
  publicPredictionPool: 'SUPPORTED',
  todaysBestValueRanking: 'BLOCKED_BY_PRODUCT_DECISION',
  conversationSession: 'MISSING',
  conversationPersistence: 'MISSING',
  rateLimiting: 'MISSING',
  aiEntitlementEnforcement: 'SUPPORTED',
  aiAuthentication: 'SUPPORTED',
  couponBuilderEndpoint: 'SUPPORTED',
  couponEligiblePool: 'SUPPORTED',
  couponRiskSemantics: 'SUPPORTED',
  couponStablePredictionReference: 'PARTIALLY_SUPPORTED',
  couponDeduplication: 'SUPPORTED',
  couponSelectionValidation: 'SUPPORTED',
} as const satisfies Readonly<Record<string, AssistantContractCapability>>;

export const productionAssistantAvailable = false;
export const productionCouponBuilderAvailable = false;

export const couponRiskOptions = [
  {
    key: 'SAFE',
    label: 'Safe',
    detail: 'Prioritizes stronger supporting evidence.',
  },
  {
    key: 'BALANCED',
    label: 'Balanced',
    detail: 'Balances confidence and potential value.',
  },
  {
    key: 'BOLD',
    label: 'Bold',
    detail: 'Uses more aggressive combinations from eligible signals.',
  },
] as const;

export type CouponRisk = (typeof couponRiskOptions)[number]['key'];
