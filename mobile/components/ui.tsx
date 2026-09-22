import type { PropsWithChildren, ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
  type PressableProps,
} from 'react-native';
import { SafeAreaView, type Edge } from 'react-native-safe-area-context';

import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
  typeScale,
  createThemedStyleSheet,
} from '@/theme/tokens';
import { useRouter } from 'expo-router';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { useLanguage } from '@/features/language/LanguageContext';
import { SymbolView } from 'expo-symbols';

export function Screen({
  children,
  keyboardAware = false,
  onRefresh,
  refreshing = false,
  safeAreaEdges = defaultScreenEdges,
}: PropsWithChildren<{
  keyboardAware?: boolean;
  onRefresh?: (() => void) | undefined;
  refreshing?: boolean;
  safeAreaEdges?: readonly Edge[];
}>) {
  return (
    <SafeAreaView
      edges={safeAreaEdges}
      style={styles.safe}
      testID="screen-safe-area"
    >
      <ScrollView
        automaticallyAdjustKeyboardInsets={keyboardAware}
        contentContainerStyle={styles.screen}
        keyboardDismissMode="on-drag"
        keyboardShouldPersistTaps="handled"
        testID="screen-scroll-view"
        refreshControl={
          onRefresh ? (
            <RefreshControl
              colors={[colors.secondary]}
              onRefresh={onRefresh}
              refreshing={refreshing}
              tintColor={colors.secondary}
            />
          ) : undefined
        }
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export const defaultScreenEdges = ['top', 'left', 'right'] as const;
export const stackScreenEdges = ['bottom', 'left', 'right'] as const;

export function AppHeader({
  eyebrow,
  title,
  hideProfileButton = false,
}: {
  eyebrow?: string | undefined;
  title: string;
  hideProfileButton?: boolean;
}) {
  return (
    <View style={styles.header}>
      <View style={styles.headerTitles}>
        {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
      </View>
      {!hideProfileButton && <ProfileAction />}
    </View>
  );
}

function ProfileAction() {
  const router = useRouter();
  const { state } = useEntitlement();
  const isPremium = state === 'PREMIUM_ACTIVE' || state === 'PREMIUM_TRIAL';

  return (
    <Pressable
      accessibilityLabel={`Open Profile, ${isPremium ? 'Premium' : 'Guest'}`}
      accessibilityRole="button"
      onPress={() => router.push('/profile')}
      style={({ pressed }) => [styles.profileButton, pressed && styles.pressed]}
    >
      <View
        style={[styles.profileAvatar, isPremium && styles.profileAvatarPremium]}
      >
        <SymbolView
          name="person.fill"
          tintColor={isPremium ? colors.accent : colors.textSecondary}
          fallback={
            <Text
              style={{
                fontSize: 18,
                color: isPremium ? colors.accent : colors.textSecondary,
              }}
            >
              👤
            </Text>
          }
        />
      </View>
    </Pressable>
  );
}

export function SectionHeader({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}) {
  return (
    <View style={styles.sectionHeader}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        {title}
      </Text>
      {detail ? <Text style={styles.secondary}>{detail}</Text> : null}
    </View>
  );
}

export function Button({
  accessibilityState,
  children,
  disabled,
  style,
  variant = 'primary',
  ...props
}: PressableProps & { variant?: 'primary' | 'secondary' | 'quiet' | 'auth' }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{
        ...accessibilityState,
        disabled: Boolean(disabled),
      }}
      disabled={disabled}
      style={(state) => [
        styles.button,
        variant === 'secondary' && styles.buttonSecondary,
        variant === 'quiet' && styles.buttonQuiet,
        variant === 'auth' && styles.buttonAuth,
        disabled && styles.buttonDisabled,
        state.pressed && !disabled && styles.pressed,
        typeof style === 'function' ? style(state) : style,
      ]}
      {...props}
    >
      <Text
        style={[
          styles.buttonText,
          variant === 'auth' && !disabled && styles.buttonTextAuth,
          (variant !== 'primary' || disabled) && styles.buttonTextOnSurface,
        ]}
      >
        {children as ReactNode}
      </Text>
    </Pressable>
  );
}

export function Chip({
  label,
  selected = false,
}: {
  label: string;
  selected?: boolean;
}) {
  return (
    <View
      accessibilityLabel={`${label} filter`}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>
        {label}
      </Text>
    </View>
  );
}

export function Badge({
  label,
  tone = 'primary',
}: {
  label: string;
  tone?: 'primary' | 'accent' | 'positive' | 'warning' | 'negative';
}) {
  return (
    <View
      accessibilityLabel={label}
      accessibilityRole="text"
      style={[styles.badge, { borderColor: colors[tone] }]}
    >
      <Text style={[styles.badgeText, { color: colors[tone] }]}>{label}</Text>
    </View>
  );
}

export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <View
      accessibilityLabel={title}
      accessibilityRole="summary"
      style={styles.stateCard}
    >
      <Text style={styles.stateTitle}>{title}</Text>
      <Text style={styles.secondary}>{detail}</Text>
    </View>
  );
}

export function LoadingState() {
  const { t } = useLanguage();
  return (
    <View
      accessibilityLabel={t('Loading')}
      accessibilityLiveRegion="polite"
      accessibilityRole="progressbar"
      style={styles.centered}
    >
      <ActivityIndicator color={colors.secondary} size="large" />
      <Text style={styles.secondary}>{t('Loading')}</Text>
    </View>
  );
}

export function ErrorState({ retry }: { retry?: () => void }) {
  const { t } = useLanguage();
  return (
    <View
      accessibilityLiveRegion="polite"
      accessibilityRole="alert"
      style={styles.stateCard}
    >
      <Text style={styles.stateTitle}>{t('Unavailable')}</Text>
      <Text style={styles.secondary}>{t('Not enough reliable data')}</Text>
      {retry ? <Button onPress={retry}>{t('Retry')}</Button> : null}
    </View>
  );
}

export function UnavailableState({
  title,
  detail,
  retry,
}: {
  title: string;
  detail: string;
  retry?: (() => void) | undefined;
}) {
  const { t } = useLanguage();
  return (
    <View accessibilityLiveRegion="polite" style={styles.stateCard}>
      <Text style={styles.stateTitle}>{title}</Text>
      <Text style={styles.secondary}>{detail}</Text>
      {retry ? (
        <Button accessibilityLabel={`${t('Retry')}: ${title}`} onPress={retry}>
          {t('Retry')}
        </Button>
      ) : null}
    </View>
  );
}

export const sharedStyles = createThemedStyleSheet({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.sm,
  },
  rowBetween: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  label: { color: colors.textSecondary, ...typography.caption },
  body: { color: colors.text, ...typography.body },
  strong: { color: colors.text, ...typography.body, fontWeight: '700' },
});

const styles = createThemedStyleSheet({
  safe: { flex: 1, backgroundColor: colors.background },
  screen: { padding: spacing.md, paddingBottom: spacing.xl, gap: spacing.lg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  headerTitles: { gap: spacing.xs, flexShrink: 1 },
  eyebrow: {
    color: colors.secondary,
    fontSize: typeScale.caption,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  title: { color: colors.text, ...typography.pageTitle },
  sectionHeader: { gap: spacing.xs },
  sectionTitle: {
    color: colors.onBrand,
    ...typography.sectionTitle,
  },
  buttonTextOnSurface: { color: colors.text },
  secondary: {
    color: colors.textSecondary,
    ...typography.body,
  },
  button: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
    borderRadius: radii.md,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  buttonDisabled: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
  },
  buttonSecondary: { backgroundColor: colors.surfaceRaised },
  buttonQuiet: { backgroundColor: colors.transparent },
  buttonAuth: { backgroundColor: colors.authPrimaryBackground },
  buttonText: {
    color: colors.text,
    flexShrink: 1,
    fontSize: typeScale.body,
    fontWeight: '700',
    textAlign: 'center',
  },
  buttonTextAuth: { color: colors.authPrimaryText },
  pressed: { opacity: 0.8 },
  chip: {
    minHeight: 40,
    justifyContent: 'center',
    borderColor: colors.border,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
  },
  chipSelected: {
    backgroundColor: colors.controlSelected,
    borderColor: colors.controlSelected,
  },
  chipText: {
    color: colors.textSecondary,
    fontSize: typeScale.caption,
    fontWeight: '700',
  },
  chipTextSelected: { color: colors.controlSelectedText },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeText: { fontSize: typeScale.caption, fontWeight: '800' },
  stateCard: {
    backgroundColor: colors.surfaceRaised,
    borderRadius: radii.md,
    borderWidth: 0,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  stateTitle: {
    color: colors.text,
    ...typography.sectionTitle,
  },
  centered: {
    minHeight: 240,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
  },
  profileButton: {
    minWidth: touchTarget,
    minHeight: touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileAvatarPremium: {
    borderColor: colors.accent,
  },
});
