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
  Button,
  Screen,
  SectionHeader,
  sharedStyles,
  stackScreenEdges,
} from '@/components/ui';
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
  email = null,
  onSignOut,
}: {
  entitlement: EntitlementState;
  onSignIn: () => void;
  email?: string | null;
  onSignOut?: (() => void) | undefined;
}) {
  const guest = entitlement === 'GUEST';
  const { t, language, setLanguage } = useLanguage();
  const { preference, setPreference } = useAppearance();
  const version = Constants.expoConfig?.version ?? t('Unavailable');
  const showLegalPlaceholder = (destination: string) =>
    Alert.alert(destination, t('Final legal content is not yet available.'));

  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <ProfileGroup title={t('Account')}>
        {guest ? (
          <Button onPress={onSignIn} variant="secondary">
            {t('Sign In')}
          </Button>
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
        <InformationRow
          label={t('Premium')}
          value={t(entitlementLabels[entitlement])}
        />
      </ProfileGroup>

      <ProfileGroup title={t('Preferences')}>
        <View style={sharedStyles.rowBetween}>
          <Text style={styles.label}>{t('Language')}</Text>
          <View style={styles.languageActions}>
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
  const { state } = useEntitlement();
  const session = useProductSession();
  return (
    <ProfileView
      entitlement={state}
      email={session.user?.email ?? null}
      onSignIn={() => router.push('/auth' as Href)}
      onSignOut={() => void session.signOut()}
    />
  );
}

const styles = createThemedStyleSheet({
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
  languageActions: { flexDirection: 'row', gap: spacing.sm },
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
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  appearanceOptionText: {
    color: colors.textSecondary,
    flexShrink: 1,
    textAlign: 'center',
    ...typography.caption,
  },
  appearanceOptionTextSelected: { color: colors.onBrand },
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
