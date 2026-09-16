export const entitlementStates = [
  'GUEST',
  'PREMIUM_ACTIVE',
  'PREMIUM_TRIAL',
  'PREMIUM_EXPIRED',
  'PREMIUM_INACTIVE',
] as const;

export type EntitlementState = (typeof entitlementStates)[number];
export type TrialEligibility = 'eligible' | 'ineligible' | 'unknown';
