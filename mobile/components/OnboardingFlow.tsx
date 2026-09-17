import { useState, type ReactNode } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { colors, radii, spacing, typography } from '@/theme/tokens';

export const onboardingPages = [
  {
    title: 'Hundreds of matches. Only the strongest signals.',
    body: 'Explore football with publication-safe analysis and honest unavailable states.',
  },
  {
    title: 'Find value, not just winners.',
    body: 'PitchValue compares probability and market context without promising outcomes.',
  },
  {
    title: 'Save a match. Get a Final Check.',
    body: 'Future account features can preserve your context without blocking guest discovery.',
  },
] as const;

function BrandLockup() {
  const { t } = useLanguage();
  return (
    <View
      accessibilityLabel={t('PitchValue. Find value beyond the odds.')}
      style={styles.brand}
    >
      <Text style={styles.wordmark}>PitchValue</Text>
      <Text style={styles.tagline}>{t('Find value beyond the odds.')}</Text>
    </View>
  );
}

export function AgeConfirmation({
  onAccept,
  onExit,
  storageError = false,
}: {
  onAccept: () => void;
  onExit: () => void;
  storageError?: boolean;
}) {
  const { t } = useLanguage();
  return (
    <FirstLaunchPage>
      <BrandLockup />
      <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.title}>
          {t('For adults 18+')}
        </Text>
        <Text style={styles.body}>
          {t(
            'PitchValue is a decision-support product, not a sportsbook. Betting can involve financial loss. You are responsible for following the laws that apply where you live.',
          )}
        </Text>
        <View
          accessibilityLabel={t('Legal information pending approved content')}
          style={styles.legal}
        >
          <Text style={styles.legalTitle}>{t('Before continuing')}</Text>
          <Text style={styles.secondary}>
            {t('Terms · Privacy · Responsible Gambling')}
          </Text>
          <Text style={styles.caption}>
            {t(
              'Full legal information and destinations are not yet available.',
            )}
          </Text>
        </View>
        <Button
          accessibilityLabel={t('Confirm I am 18 or older')}
          onPress={onAccept}
        >
          {t('I’m 18 or older')}
        </Button>
        {storageError ? <StorageError /> : null}
        <Button
          accessibilityLabel={t('Exit PitchValue')}
          onPress={onExit}
          variant="secondary"
        >
          {t('Exit')}
        </Button>
      </View>
    </FirstLaunchPage>
  );
}

export function ExitConfirmation({ onReview }: { onReview: () => void }) {
  const { t } = useLanguage();
  return (
    <FirstLaunchPage>
      <BrandLockup />
      <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.title}>
          {t('PitchValue remains locked')}
        </Text>
        <Text style={styles.body}>
          {t(
            'Close the app to exit. PitchValue will not enter the product unless the 18+ confirmation is completed.',
          )}
        </Text>
        <Button onPress={onReview} variant="secondary">
          {t('Review age requirement')}
        </Button>
      </View>
    </FirstLaunchPage>
  );
}

export function OnboardingFlow({
  onComplete,
  storageError = false,
}: {
  onComplete: () => void;
  storageError?: boolean;
}) {
  const { t } = useLanguage();
  const [page, setPage] = useState(0);
  const content = onboardingPages[page] ?? onboardingPages[0];
  const lastPage = page === onboardingPages.length - 1;
  return (
    <FirstLaunchPage>
      <BrandLockup />
      <View style={styles.card}>
        <Text style={styles.eyebrow}>{t('GET STARTED')}</Text>
        <Text accessibilityRole="header" style={styles.title}>
          {t(content.title)}
        </Text>
        <Text style={styles.body}>{t(content.body)}</Text>
        <View
          accessibilityLabel={`${t('Onboarding page')} ${page + 1} ${t('of')} ${onboardingPages.length}`}
          style={styles.dots}
        >
          {onboardingPages.map((item, index) => (
            <View
              key={item.title}
              style={[styles.dot, index === page && styles.dotActive]}
            />
          ))}
        </View>
        <View style={styles.actions}>
          {page > 0 ? (
            <Button
              onPress={() => setPage((current) => current - 1)}
              variant="secondary"
            >
              {t('Back')}
            </Button>
          ) : null}
          <Button
            onPress={
              lastPage ? onComplete : () => setPage((current) => current + 1)
            }
          >
            {lastPage ? t('Explore PitchValue') : t('Next')}
          </Button>
        </View>
        {!lastPage ? (
          <Button
            accessibilityLabel={t('Skip onboarding and open Today')}
            onPress={onComplete}
            variant="quiet"
          >
            {t('Skip')}
          </Button>
        ) : null}
        {storageError ? <StorageError /> : null}
      </View>
    </FirstLaunchPage>
  );
}

function StorageError() {
  const { t } = useLanguage();
  return (
    <Text accessibilityLiveRegion="polite" style={styles.error}>
      {t('First-launch progress could not be saved. Please try again.')}
    </Text>
  );
}

function FirstLaunchPage({ children }: { children: ReactNode }) {
  return (
    <SafeAreaView
      edges={['top', 'bottom', 'left', 'right']}
      style={styles.safe}
    >
      <ScrollView
        contentContainerStyle={styles.screen}
        keyboardDismissMode="on-drag"
        keyboardShouldPersistTaps="handled"
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { backgroundColor: colors.background, flex: 1 },
  screen: {
    flexGrow: 1,
    gap: spacing.xl,
    justifyContent: 'center',
    padding: spacing.lg,
  },
  brand: { alignItems: 'center', gap: spacing.xs },
  wordmark: { color: colors.text, ...typography.pageTitle },
  tagline: { color: colors.accent, ...typography.body },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.lg,
    borderWidth: 1,
    gap: spacing.lg,
    padding: spacing.lg,
  },
  eyebrow: { color: colors.secondary, ...typography.caption },
  title: { color: colors.text, ...typography.pageTitle },
  body: { color: colors.textSecondary, ...typography.body },
  legal: {
    borderLeftColor: colors.accent,
    borderLeftWidth: 3,
    gap: spacing.xs,
    paddingLeft: spacing.md,
  },
  legalTitle: { color: colors.text, ...typography.body, fontWeight: '700' },
  secondary: { color: colors.textSecondary, ...typography.body },
  caption: { color: colors.textSecondary, ...typography.caption },
  error: { color: colors.negative, ...typography.metadata },
  dots: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'center',
  },
  dot: {
    backgroundColor: colors.border,
    borderRadius: radii.pill,
    height: 8,
    width: 8,
  },
  dotActive: { backgroundColor: colors.secondary, width: 24 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
