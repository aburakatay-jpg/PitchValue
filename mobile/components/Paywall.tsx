import { Text, View } from 'react-native';

import { Badge, Button, SectionHeader, sharedStyles } from '@/components/ui';
import { useCommerce } from '@/features/entitlement/CommerceContext';
import { useLanguage } from '@/features/language/LanguageContext';
import { CanonicalPlan } from '@/lib/commerce';
import {
  colors,
  spacing,
  typography,
  createThemedStyleSheet,
} from '@/theme/tokens';
import type { TrialEligibility } from '@/types/entitlement';

export const premiumBenefits = [
  'Full market analysis',
  'Bet Score details',
  'Model agreement when authoritative data is available',
  'Final Check',
  'AI explanations',
  'Coupon Builder',
] as const;

export function annualPlanDetail(
  eligibility: TrialEligibility,
  t: (k: string) => string,
): string {
  if (eligibility === 'eligible') {
    return t('A trial may be offered after App Store eligibility is verified.');
  }
  return t('Trial eligibility and localized pricing require the App Store.');
}

function PaywallPlanCard({
  id,
  name,
  annual,
  trialEligibility,
  localizedPrice,
  disabled,
  isPurchasing,
  onPurchase,
}: {
  id: CanonicalPlan;
  name: string;
  annual: boolean;
  trialEligibility: TrialEligibility;
  localizedPrice: string | null;
  disabled: boolean;
  isPurchasing: boolean;
  onPurchase: (id: CanonicalPlan) => void;
}) {
  const { t } = useLanguage();
  return (
    <View style={[sharedStyles.card, annual && styles.highlighted]}>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.name}>{t(name)}</Text>
        {annual ? <Badge label={t('Annual option')} tone="accent" /> : null}
      </View>
      <Text style={styles.price}>
        {localizedPrice ?? t('Localized price unavailable')}
      </Text>
      <Text style={styles.detail}>
        {annual
          ? annualPlanDetail(trialEligibility, t)
          : t('Pricing will be supplied by the App Store.')}
      </Text>
      <Button
        accessibilityLabel={`${t(name)} ${
          disabled ? t('purchase unavailable') : ''
        }`}
        disabled={disabled || isPurchasing}
        onPress={() => onPurchase(id)}
      >
        {disabled ? t('Purchase unavailable') : t('Purchase')}
      </Button>
    </View>
  );
}

export function PaywallShell({
  trialEligibility = 'unknown',
}: {
  trialEligibility?: TrialEligibility;
}) {
  const { t } = useLanguage();
  const commerce = useCommerce();

  return (
    <View style={styles.stack}>
      <SectionHeader
        title={t('Unlock full PitchValue analysis')}
        detail={t(
          'Review the planned Premium experience. Store purchases are not available yet.',
        )}
      />
      <View style={sharedStyles.card}>
        {premiumBenefits.map((benefit) => (
          <Text key={benefit} style={styles.benefit}>
            • {t(benefit)}
          </Text>
        ))}
      </View>
      {commerce.products.map((plan) => (
        <PaywallPlanCard
          key={plan.id}
          id={plan.id}
          name={
            plan.id === 'quarterly'
              ? '3 Months'
              : plan.id.charAt(0).toUpperCase() + plan.id.slice(1)
          }
          annual={plan.id === 'annual'}
          trialEligibility={trialEligibility}
          localizedPrice={plan.localizedPrice}
          disabled={!commerce.isConfigured}
          isPurchasing={commerce.isPurchasing}
          onPurchase={commerce.purchase}
        />
      ))}
      <Button
        accessibilityLabel={t('Restore purchases')}
        disabled={!commerce.isConfigured || commerce.isRestoring}
        variant="quiet"
        onPress={commerce.restore}
      >
        {t('Restore Purchases')}{' '}
        {!commerce.isConfigured ? `· ${t('Unavailable')}` : ''}
      </Button>
      <Text style={styles.footnote}>
        {commerce.isConfigured
          ? t(
              'Payment, restoration, and trial confirmation will use the App Store.',
            )
          : t(
              'Payment, restoration, trial confirmation, and entitlement changes are currently unavailable.',
            )}
      </Text>
    </View>
  );
}

export function PaywallPresentation({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
  return (
    <View style={styles.stack}>
      <Button
        accessibilityLabel={t('Close Premium options')}
        onPress={onClose}
        variant="quiet"
      >
        {t('Close')}
      </Button>
      <PaywallShell trialEligibility="unknown" />
    </View>
  );
}

const styles = createThemedStyleSheet({
  stack: { gap: spacing.md },
  highlighted: { borderColor: colors.accent },
  name: { color: colors.text, ...typography.sectionTitle },
  price: { color: colors.text, ...typography.featured },
  detail: { color: colors.textSecondary, ...typography.body },
  benefit: { color: colors.text, ...typography.body },
  footnote: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
});
