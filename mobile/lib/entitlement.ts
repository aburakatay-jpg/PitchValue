import { entitlementStates, type EntitlementState } from '@/types/entitlement';

export function isEntitlementState(value: unknown): value is EntitlementState {
  return entitlementStates.includes(value as EntitlementState);
}

export function hasPremiumAccess(state: EntitlementState): boolean {
  return state === 'PREMIUM_ACTIVE' || state === 'PREMIUM_TRIAL';
}
