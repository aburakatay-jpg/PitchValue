import { StyleSheet, Text, View } from 'react-native';

import { Badge, Button, sharedStyles } from '@/components/ui';
import { colors, spacing, typeScale } from '@/theme/tokens';
import type { TrialEligibility } from '@/types/entitlement';

export const plans = [
  {
    id: 'monthly',
    name: 'Monthly',
    price: '499.99 TL / month',
    detail: 'No trial',
  },
  {
    id: 'quarterly',
    name: '3 Months',
    price: '999.99 TL total',
    detail: '333.33 TL/month · No trial',
  },
] as const;

export function annualPlanCopy(eligibility: TrialEligibility) {
  if (eligibility === 'eligible')
    return { detail: 'Eligible for a 3-day trial', cta: 'Preview 3-day trial' };
  if (eligibility === 'ineligible')
    return { detail: '~250 TL/month', cta: 'Continue with annual' };
  return {
    detail: '~250 TL/month · Trial eligibility checked at purchase',
    cta: 'Review annual option',
  };
}

export function PaywallPlanCard({
  name,
  price,
  detail,
  highlighted = false,
  cta = 'Purchase unavailable in this preview',
}: {
  name: string;
  price: string;
  detail: string;
  highlighted?: boolean;
  cta?: string;
}) {
  return (
    <View style={[sharedStyles.card, highlighted && styles.highlighted]}>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.name}>{name}</Text>
        {highlighted ? <Badge label="Best value" tone="accent" /> : null}
      </View>
      <Text style={styles.price}>{price}</Text>
      <Text style={styles.detail}>{detail}</Text>
      <Button accessibilityLabel={cta} disabled>
        {cta}
      </Button>
    </View>
  );
}

export function PaywallShell({
  trialEligibility = 'unknown',
}: {
  trialEligibility?: TrialEligibility;
}) {
  const annual = annualPlanCopy(trialEligibility);
  return (
    <View style={styles.stack}>
      {plans.map((plan) => (
        <PaywallPlanCard key={plan.id} {...plan} />
      ))}
      <PaywallPlanCard
        name="Annual"
        price="2,999.99 TL total"
        detail={annual.detail}
        highlighted
        cta={annual.cta}
      />
      <Text style={styles.footnote}>
        Development preview only. No payment action is connected.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  highlighted: { borderColor: colors.accent },
  name: { color: colors.text, fontSize: typeScale.title, fontWeight: '700' },
  price: { color: colors.text, fontSize: typeScale.title, fontWeight: '800' },
  detail: { color: colors.textSecondary, fontSize: typeScale.body },
  footnote: {
    color: colors.textSecondary,
    fontSize: typeScale.caption,
    textAlign: 'center',
  },
});
