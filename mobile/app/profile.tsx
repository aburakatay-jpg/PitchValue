import Constants from 'expo-constants';
import { useRouter, type Href } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Button, Screen, SectionHeader, sharedStyles } from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { colors, spacing, typography } from '@/theme/tokens';
import type { EntitlementState } from '@/types/entitlement';

export const profileGroups = [
  'Account',
  'Subscription',
  'Preferences',
  'Responsible Gaming',
  'App',
] as const;

const entitlementLabels: Readonly<Record<EntitlementState, string>> = {
  GUEST: 'Guest',
  PREMIUM_ACTIVE: 'Premium Active',
  PREMIUM_TRIAL: 'Premium Trial',
  PREMIUM_EXPIRED: 'Premium Inactive',
  PREMIUM_INACTIVE: 'Premium Inactive',
};

function ProfileGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.group}>
      <SectionHeader title={title} />
      <View style={sharedStyles.card}>{children}</View>
    </View>
  );
}

function InformationRow({ label, value }: { label: string; value: string }) {
  return (
    <View
      accessibilityLabel={`${label}: ${value}`}
      style={sharedStyles.rowBetween}
    >
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

export function ProfileView({
  entitlement,
  onSignIn,
  onViewPremium,
  email = null,
  onSignOut,
}: {
  entitlement: EntitlementState;
  onSignIn: () => void;
  onViewPremium: () => void;
  email?: string | null;
  onSignOut?: (() => void) | undefined;
}) {
  const guest = entitlement === 'GUEST';
  const { t, language, setLanguage } = useLanguage();
  return (
    <Screen>
      <ProfileGroup title={t('Account')}>
        <InformationRow
          label={t('Account status')}
          value={t(entitlementLabels[entitlement])}
        />
        {guest ? (
          <>
            <Text style={styles.detail}>
              {t(
                'Guest access includes public Today, Explore, and Match Detail discovery.',
              )}
            </Text>
            <Button onPress={onSignIn} variant="secondary">
              {t('Sign in')}
            </Button>
          </>
        ) : (
          <>
            {email ? <InformationRow label="Email" value={email} /> : null}
            {onSignOut ? (
              <Button onPress={onSignOut} variant="secondary">
                {t('Sign out')}
              </Button>
            ) : null}
          </>
        )}
      </ProfileGroup>
      <ProfileGroup title={t('Subscription')}>
        <InformationRow
          label={t('Access')}
          value={t(entitlementLabels[entitlement])}
        />
        <Button onPress={onViewPremium} variant="secondary">
          {t('View Premium')}
        </Button>
        <Text style={styles.detail}>
          {t(
            'Subscription management and restoration are currently unavailable.',
          )}
        </Text>
      </ProfileGroup>
      <ProfileGroup title={t('Preferences')}>
        <View style={sharedStyles.rowBetween}>
          <Text style={styles.label}>{t('Language')}</Text>
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button
              variant={language === 'en' ? 'primary' : 'secondary'}
              onPress={() => setLanguage('en')}
            >
              EN
            </Button>
            <Button
              variant={language === 'tr' ? 'primary' : 'secondary'}
              onPress={() => setLanguage('tr')}
            >
              TR
            </Button>
          </View>
        </View>
      </ProfileGroup>
      <ProfileGroup title={t('Responsible Gaming')}>
        <Text style={styles.detail}>
          {t('18+ · Betting can involve financial loss.')}
        </Text>
        <Text style={styles.detail}>
          {t('Full Responsible Gambling information is not yet available.')}
        </Text>
      </ProfileGroup>
      <ProfileGroup title={t('App')}>
        <InformationRow
          label={t('Version')}
          value={Constants.expoConfig?.version ?? t('Unavailable')}
        />
        <Text style={styles.detail}>
          {t('Legal and support destinations are not yet available.')}
        </Text>
      </ProfileGroup>
    </Screen>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const { state } = useEntitlement();
  const session = useProductSession();
  return (
    <ProfileView
      entitlement={state}
      email={session.user?.email ?? null}
      onSignIn={() => router.push('/auth/index' as Href)}
      onSignOut={() => void session.signOut()}
      onViewPremium={() => router.push('/paywall')}
    />
  );
}

const styles = StyleSheet.create({
  group: { gap: spacing.sm },
  label: {
    color: colors.text,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '700',
  },
  value: {
    color: colors.secondary,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.body,
  },
  detail: { color: colors.textSecondary, ...typography.body },
});
