import Constants from 'expo-constants';
import { useRouter, type Href } from 'expo-router';
import {
  Alert,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SymbolView, type SFSymbol } from 'expo-symbols';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  Screen,
  SectionHeader,
  sharedStyles,
  stackScreenEdges,
  Button,
} from '@/components/ui';
import { LanguageSelector } from '@/components/LanguageSelector';
import { useLanguage } from '@/features/language/LanguageContext';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import {
  appearancePreferences,
  useAppearance,
  type AppearancePreference,
} from '@/features/appearance/AppearanceContext';
import {
  colors,
  spacing,
  touchTarget,
  typography,
  createThemedStyleSheet,
} from '@/theme/tokens';
import type { EntitlementState } from '@/types/entitlement';

export const profileGroups = [
  'Account',
  'Preferences',
  'Responsible Gaming',
] as const;

export const profileLegalDestinations = [
  '18+ and Age Declaration',
  'Betting Risk and Responsible Gaming',
  'Terms of Use',
  'Privacy Policy',
  'Legal Information',
] as const;

const CONTACT_EMAIL = 'pitchvalue@outlook.com';
const X_HANDLE = '@pitchvalueapp';
const X_URL = 'https://x.com/pitchvalueapp';

const entitlementLabels: Readonly<Record<EntitlementState, string>> = {
  GUEST: 'Premium Inactive',
  PREMIUM_ACTIVE: 'Premium Active',
  PREMIUM_TRIAL: 'Premium Trial',
  PREMIUM_EXPIRED: 'Premium Expired',
  PREMIUM_INACTIVE: 'Premium Inactive',
};

const entitlementStatusLabels: Readonly<Record<EntitlementState, string>> = {
  GUEST: 'Inactive',
  PREMIUM_ACTIVE: 'Active',
  PREMIUM_TRIAL: 'Trial',
  PREMIUM_EXPIRED: 'Expired',
  PREMIUM_INACTIVE: 'Inactive',
};

async function openSupportedUrl(url: string) {
  try {
    if (await Linking.canOpenURL(url)) await Linking.openURL(url);
  } catch {
    // A missing platform handler must not make Profile unusable.
  }
}

function ProfileGroup({
  title,
  children,
  account = false,
}: {
  title: string;
  children: React.ReactNode;
  account?: boolean;
}) {
  return (
    <View style={styles.group}>
      <SectionHeader title={title} />
      <View
        style={[sharedStyles.card, account && styles.accountCard]}
        testID={account ? 'profile-account-card' : undefined}
      >
        {children}
      </View>
    </View>
  );
}

function PremiumStatusRow({
  label,
  value,
  fullValue,
  actionLabel,
  onPress,
}: {
  label: string;
  value: string;
  fullValue: string;
  actionLabel: string;
  onPress?: (() => void) | undefined;
}) {
  const content = (
    <>
      <View style={styles.accountRowLeading}>
        <SymbolView
          accessibilityElementsHidden
          name={'p.circle' as SFSymbol}
          size={20}
          tintColor={colors.textSecondary}
        />
        <Text style={styles.label}>{label}</Text>
      </View>
      <View style={styles.premiumValueArea}>
        <Text
          style={onPress ? styles.premiumInteractiveValue : styles.statusValue}
          testID="profile-premium-value"
        >
          {value}
        </Text>
        {onPress ? (
          <SymbolView
            accessibilityElementsHidden
            name={'chevron.right' as SFSymbol}
            size={15}
            tintColor={colors.textSecondary}
            testID="profile-premium-chevron"
          />
        ) : null}
      </View>
    </>
  );
  return onPress ? (
    <Pressable
      accessibilityLabel={`${label}: ${fullValue}. ${actionLabel}`}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.premiumRow, pressed && styles.pressed]}
      testID="profile-premium-row"
    >
      {content}
    </Pressable>
  ) : (
    <View
      accessible
      accessibilityLabel={`${label}: ${fullValue}`}
      accessibilityRole="text"
      style={styles.premiumRow}
      testID="profile-premium-static-row"
    >
      {content}
    </View>
  );
}

function LegalRow({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.legalRow, pressed && styles.pressed]}
    >
      <Text style={styles.legalLabel}>{label}</Text>
      <SymbolView
        accessibilityElementsHidden
        name={'chevron.right' as SFSymbol}
        size={15}
        tintColor={colors.textSecondary}
      />
    </Pressable>
  );
}

function ContactLink({
  label,
  icon,
  onPress,
  testID,
  divided = false,
}: {
  label: string;
  icon: 'mail' | 'x';
  onPress: () => void;
  testID: string;
  divided?: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="link"
      onPress={onPress}
      style={({ pressed }) => [
        styles.contactLink,
        divided && styles.contactDivider,
        pressed && styles.pressed,
      ]}
      testID={testID}
    >
      {icon === 'mail' ? (
        <SymbolView
          accessibilityElementsHidden
          name={'envelope' as SFSymbol}
          size={18}
          tintColor={colors.textSecondary}
        />
      ) : (
        <Text accessibilityElementsHidden style={styles.xIcon}>
          X
        </Text>
      )}
      <Text style={styles.contactText}>{label}</Text>
    </Pressable>
  );
}

const appearanceLabels: Readonly<Record<AppearancePreference, string>> = {
  system: 'System',
  dark: 'Dark',
  light: 'Light',
};

export function ProfileView({
  entitlement,
  onSignIn,
  onOpenPremium,
  email = null,
  onSignOut,
  authenticated = false,
}: {
  entitlement: EntitlementState;
  onSignIn: () => void;
  onOpenPremium?: (() => void) | undefined;
  email?: string | null;
  onSignOut?: (() => void) | undefined;
  authenticated?: boolean;
}) {
  const guest = !authenticated;
  const { t } = useLanguage();
  const router = useRouter();
  const { preference, setPreference } = useAppearance();
  const version = Constants.expoConfig?.version ?? t('Unavailable');
  const premiumOpensPaywall =
    entitlement === 'GUEST' ||
    entitlement === 'PREMIUM_INACTIVE' ||
    entitlement === 'PREMIUM_EXPIRED';
  const showLegalPlaceholder = (destination: string) =>
    Alert.alert(destination, t('Final legal content is not yet available.'));
  const confirmSignOut = () => {
    if (!onSignOut) return;
    Alert.alert(t('Are you sure you want to sign out?'), undefined, [
      { text: t('Cancel Sign Out'), style: 'cancel' },
      { text: t('Sign Out'), style: 'destructive', onPress: onSignOut },
    ]);
  };

  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <ProfileGroup account title={t('Account')}>
        {guest ? (
          <Pressable
            accessibilityLabel={t('Sign In')}
            accessibilityRole="button"
            onPress={onSignIn}
            style={({ pressed }) => [
              styles.accountSignIn,
              pressed && styles.pressed,
            ]}
            testID="profile-account-sign-in"
          >
            <Text style={styles.accountSignInText}>{t('Sign In')}</Text>
          </Pressable>
        ) : (
          <View
            accessible
            accessibilityLabel={email || t('Signed in')}
            style={styles.accountIdentityRow}
            testID="profile-account-identity"
          >
            <SymbolView
              accessibilityElementsHidden
              name={'person.crop.circle' as SFSymbol}
              size={20}
              tintColor={colors.textSecondary}
            />
            <Text numberOfLines={1} style={styles.accountIdentityText}>
              {email || t('Signed in')}
            </Text>
          </View>
        )}
        <View style={styles.accountDivider} testID="profile-account-divider" />
        <PremiumStatusRow
          label={t('Premium')}
          value={t(entitlementStatusLabels[entitlement])}
          fullValue={t(entitlementLabels[entitlement])}
          actionLabel={t('View Premium')}
          onPress={premiumOpensPaywall ? onOpenPremium : undefined}
        />
      </ProfileGroup>

      <ProfileGroup title={t('Preferences')}>
        <LanguageSelector />
        <View style={styles.preferenceDivider} />
        <View style={styles.appearancePreference}>
          <Text style={styles.label}>{t('Appearance')}</Text>
          <View
            accessibilityLabel={t('Appearance')}
            accessibilityRole="radiogroup"
            style={styles.appearanceActions}
          >
            {appearancePreferences.map((appearance) => {
              const selected = preference === appearance;
              return (
                <Pressable
                  accessibilityLabel={t(appearanceLabels[appearance])}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  key={appearance}
                  onPress={() => setPreference(appearance)}
                  style={({ pressed }) => [
                    styles.appearanceOption,
                    selected && styles.appearanceOptionSelected,
                    pressed && styles.pressed,
                  ]}
                  testID={`appearance-${appearance}`}
                >
                  <Text
                    numberOfLines={2}
                    style={[
                      styles.appearanceOptionText,
                      selected && styles.appearanceOptionTextSelected,
                    ]}
                  >
                    {t(appearanceLabels[appearance])}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      </ProfileGroup>

      <ProfileGroup title={t('Responsible Gaming')}>
        {profileLegalDestinations.map((destination) => (
          <LegalRow
            key={destination}
            label={t(destination)}
            onPress={() => showLegalPlaceholder(t(destination))}
          />
        ))}
      </ProfileGroup>

      <View style={styles.contactArea} testID="profile-contact-area">
        <ContactLink
          icon="mail"
          label={CONTACT_EMAIL}
          divided
          onPress={() => void openSupportedUrl(`mailto:${CONTACT_EMAIL}`)}
          testID="profile-email-link"
        />
        <ContactLink
          icon="x"
          label={X_HANDLE}
          onPress={() => void openSupportedUrl(X_URL)}
          testID="profile-x-link"
        />
      </View>

      {authenticated ? (
        <View testID="profile-account-actions">
          <Pressable
            accessibilityLabel={t('Delete Account')}
            accessibilityRole="button"
            onPress={() => router.push('/account/delete' as Href)}
            style={({ pressed }) => [
              styles.deleteAccountRow,
              pressed && styles.pressed,
            ]}
            testID="profile-delete-account"
          >
            <Text style={styles.deleteAccountText}>{t('Delete Account')}</Text>
          </Pressable>
          {onSignOut ? (
            <Pressable
              accessibilityLabel={t('Sign Out')}
              accessibilityRole="button"
              onPress={confirmSignOut}
              style={({ pressed }) => [
                styles.signOutRow,
                pressed && styles.pressed,
              ]}
              testID="profile-sign-out"
            >
              <Text style={styles.signOutText}>{t('Sign Out')}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      <SafeAreaView
        edges={['bottom']}
        style={styles.footerSafeArea}
        testID="profile-footer"
      >
        <View style={styles.footer}>
          <Text style={styles.versionText}>
            {t('Version')} {version}
          </Text>
          <Text style={styles.copyright}>crtnapp © 2026</Text>
        </View>
      </SafeAreaView>
    </Screen>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const entitlement = useEntitlement();
  const session = useProductSession();
  const { t } = useLanguage();

  if (session.state === 'UNVERIFIED') {
    return (
      <Screen safeAreaEdges={stackScreenEdges}>
        <SectionHeader title={t('Account')} />
        <View style={[sharedStyles.card, { padding: spacing.md, gap: spacing.md }]}>
          <Text style={{ color: colors.text, textAlign: 'center' }}>
            {t('Please verify your email address to access your profile.')}
          </Text>
          <Button onPress={() => router.push('/auth/email' as Href)}>
            {t('Verify Email')}
          </Button>
          <Button onPress={() => void session.signOut()} variant="secondary">
            {t('Sign Out')}
          </Button>
        </View>
      </Screen>
    );
  }

  return (
    <ProfileView
      entitlement={entitlement.state}
      authenticated={session.state === 'AUTHENTICATED'}
      email={session.user?.email ?? null}
      onOpenPremium={entitlement.openPaywall}
      onSignIn={() => router.push('/auth' as Href)}
      onSignOut={() => void session.signOut()}
    />
  );
}

const styles = createThemedStyleSheet({
  group: { gap: spacing.sm },
  accountCard: { gap: 0, paddingVertical: spacing.xs },
  accountSignIn: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
  },
  accountSignInText: {
    color: colors.interactiveTextAccent,
    ...typography.body,
    fontWeight: '700',
  },
  accountIdentityRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    minHeight: touchTarget,
  },
  accountIdentityText: {
    color: colors.text,
    flex: 1,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '600',
  },
  accountDivider: {
    backgroundColor: colors.border,
    height: StyleSheet.hairlineWidth,
    marginVertical: spacing.xs,
  },
  accountRowLeading: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: spacing.sm,
  },
  label: {
    color: colors.text,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '700',
  },
  statusValue: {
    color: colors.textSecondary,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.body,
  },
  premiumInteractiveValue: {
    color: colors.interactiveTextAccent,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.body,
  },
  premiumRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'space-between',
    minHeight: touchTarget,
  },
  premiumValueArea: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: spacing.xs,
  },
  deleteAccountRow: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
  },
  deleteAccountText: {
    color: colors.negative,
    ...typography.body,
    fontWeight: '700',
  },
  signOutRow: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
  },
  signOutText: { color: colors.negative, ...typography.body },
  preferenceDivider: {
    backgroundColor: colors.border,
    height: StyleSheet.hairlineWidth,
  },
  appearancePreference: { gap: spacing.sm },
  appearanceActions: { flexDirection: 'row', gap: spacing.sm },
  appearanceOption: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 10,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    minHeight: touchTarget,
    paddingHorizontal: spacing.xs,
    paddingVertical: spacing.sm,
  },
  appearanceOptionSelected: {
    backgroundColor: colors.appearanceSelectedBackground,
    borderColor: colors.appearanceSelectedBackground,
  },
  appearanceOptionText: {
    color: colors.textSecondary,
    flexShrink: 1,
    textAlign: 'center',
    ...typography.caption,
  },
  appearanceOptionTextSelected: {
    color: colors.appearanceSelectedText,
    fontWeight: '700',
  },
  legalRow: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'space-between',
    minHeight: touchTarget,
    paddingVertical: spacing.sm,
  },
  legalLabel: { color: colors.text, flex: 1, ...typography.body },
  contactArea: {
    alignItems: 'stretch',
  },
  contactLink: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
  },
  contactDivider: {
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  contactText: {
    color: colors.textSecondary,
    flex: 1,
    ...typography.body,
  },
  xIcon: {
    color: colors.textSecondary,
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
    width: 18,
  },
  footer: {
    alignItems: 'center',
    gap: spacing.xs,
    paddingTop: spacing.md,
  },
  footerSafeArea: { paddingBottom: spacing.md },
  versionText: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
  copyright: {
    color: colors.textSecondary,
    opacity: 0.72,
    textAlign: 'center',
    ...typography.caption,
  },
  pressed: { opacity: 0.8 },
});
