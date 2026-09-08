import type { PropsWithChildren, ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type PressableProps,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, radii, spacing, touchTarget, typeScale } from '@/theme/tokens';

export function Screen({ children }: PropsWithChildren) {
  return (
    <SafeAreaView edges={['top']} style={styles.safe}>
      <ScrollView contentContainerStyle={styles.screen}>{children}</ScrollView>
    </SafeAreaView>
  );
}

export function AppHeader({
  eyebrow,
  title,
}: {
  eyebrow?: string;
  title: string;
}) {
  return (
    <View style={styles.header}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
    </View>
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
      <Text style={styles.sectionTitle}>{title}</Text>
      {detail ? <Text style={styles.secondary}>{detail}</Text> : null}
    </View>
  );
}

export function Button({
  children,
  disabled,
  style,
  ...props
}: PressableProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      style={(state) => [
        styles.button,
        disabled && styles.buttonDisabled,
        state.pressed && !disabled && styles.pressed,
        typeof style === 'function' ? style(state) : style,
      ]}
      {...props}
    >
      <Text style={styles.buttonText}>{children as ReactNode}</Text>
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
  tone?: 'primary' | 'accent' | 'positive';
}) {
  return (
    <View style={[styles.badge, { borderColor: colors[tone] }]}>
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
    <View style={styles.stateCard}>
      <Text style={styles.stateTitle}>{title}</Text>
      <Text style={styles.secondary}>{detail}</Text>
    </View>
  );
}

export function LoadingState() {
  return (
    <View accessibilityLabel="Loading PitchValue" style={styles.centered}>
      <ActivityIndicator color={colors.secondary} size="large" />
      <Text style={styles.secondary}>Loading PitchValue…</Text>
    </View>
  );
}

export function ErrorState({ retry }: { retry?: () => void }) {
  return (
    <View style={styles.stateCard}>
      <Text style={styles.stateTitle}>Something went wrong</Text>
      <Text style={styles.secondary}>Please try again when you are ready.</Text>
      {retry ? <Button onPress={retry}>Try again</Button> : null}
    </View>
  );
}

export const sharedStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  label: { color: colors.textSecondary, fontSize: typeScale.caption },
  body: { color: colors.text, fontSize: typeScale.body, lineHeight: 24 },
  strong: { color: colors.text, fontSize: typeScale.body, fontWeight: '700' },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  screen: { padding: spacing.md, paddingBottom: spacing.xl, gap: spacing.lg },
  header: { gap: spacing.xs },
  eyebrow: {
    color: colors.secondary,
    fontSize: typeScale.caption,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  title: { color: colors.text, fontSize: typeScale.hero, fontWeight: '800' },
  sectionHeader: { gap: spacing.xs },
  sectionTitle: {
    color: colors.text,
    fontSize: typeScale.title,
    fontWeight: '700',
  },
  secondary: {
    color: colors.textSecondary,
    fontSize: typeScale.body,
    lineHeight: 23,
  },
  button: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
    borderRadius: radii.md,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
  },
  buttonDisabled: { opacity: 0.45 },
  buttonText: {
    color: colors.text,
    fontSize: typeScale.body,
    fontWeight: '700',
  },
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
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    color: colors.textSecondary,
    fontSize: typeScale.caption,
    fontWeight: '700',
  },
  chipTextSelected: { color: colors.text },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeText: { fontSize: typeScale.caption, fontWeight: '800' },
  stateCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderStyle: 'dashed',
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  stateTitle: {
    color: colors.text,
    fontSize: typeScale.title,
    fontWeight: '700',
  },
  centered: {
    minHeight: 240,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
  },
});
