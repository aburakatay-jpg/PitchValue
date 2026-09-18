import {
  config,
  isDevelopmentPreviewEnabled,
  resolveApiBaseUrl,
} from '@/lib/config';
import { hasPremiumAccess, isEntitlementState } from '@/lib/entitlement';
import { tabRoutes } from '@/lib/routes';
import { colors, theme } from '@/theme/tokens';

describe('mobile foundation', () => {
  it('defines exactly four canonical tab routes', () => {
    expect(tabRoutes.map((route) => route.title)).toEqual([
      'Today',
      'Explore',
      'AI',
      'My Bets',
    ]);
  });

  it('makes canonical brand theme tokens available', () => {
    expect(theme.colors).toBe(colors);
    expect(colors.primary).toBe('#4169E1');
    expect(colors.background).toBe('#08111F');
  });

  it.each(['GUEST', 'PREMIUM_ACTIVE', 'PREMIUM_TRIAL', 'PREMIUM_EXPIRED'])(
    'recognizes %s entitlement state',
    (state) => {
      expect(isEntitlementState(state)).toBe(true);
    },
  );

  it('applies canonical premium access rules', () => {
    expect(hasPremiumAccess('GUEST')).toBe(false);
    expect(hasPremiumAccess('PREMIUM_ACTIVE')).toBe(true);
    expect(hasPremiumAccess('PREMIUM_TRIAL')).toBe(true);
    expect(hasPremiumAccess('PREMIUM_EXPIRED')).toBe(false);
  });

  it('loads required environment configuration safely', () => {
    expect(config.apiBaseUrl).toMatch(/^https?:\/\//);
  });

  it('fails closed instead of using localhost in a production build', () => {
    expect(resolveApiBaseUrl(false, undefined)).toBeNull();
    expect(resolveApiBaseUrl(false, '  ')).toBeNull();
    expect(resolveApiBaseUrl(true, undefined)).toBe('http://localhost:8000');
    expect(resolveApiBaseUrl(false, 'https://api.pitchvalue.example')).toBe(
      'https://api.pitchvalue.example',
    );
  });

  it('allows synthetic preview data only behind an explicit development gate', () => {
    expect(isDevelopmentPreviewEnabled(true, 'true')).toBe(true);
    expect(isDevelopmentPreviewEnabled(true, 'false')).toBe(false);
    expect(isDevelopmentPreviewEnabled(false, 'true')).toBe(false);
    expect(isDevelopmentPreviewEnabled(false, undefined)).toBe(false);
  });
});
