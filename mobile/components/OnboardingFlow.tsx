import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppHeader, Button } from '@/components/ui';
import { colors, radii, spacing, typeScale } from '@/theme/tokens';

const steps = [
  {
    eyebrow: '18+ confirmation',
    title: 'For adults only',
    body: 'PitchValue is intended for users aged 18 or over. Play responsibly.',
  },
  {
    eyebrow: '1 of 3',
    title: 'Read the programme',
    body: 'Browse a calm chronological view of synthetic match previews.',
  },
  {
    eyebrow: '2 of 3',
    title: 'Understand the edge',
    body: 'Future insights will explain value with clear context and uncertainty.',
  },
  {
    eyebrow: '3 of 3',
    title: 'Stay in control',
    body: 'Treat every selection as information, never as a guarantee.',
  },
] as const;

export function OnboardingFlow({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const content = steps[step] ?? steps[0];
  const lastStep = step === steps.length - 1;
  return (
    <SafeAreaView
      edges={['top', 'bottom', 'left', 'right']}
      style={styles.screen}
    >
      <View style={styles.brand}>
        <Text style={styles.wordmark}>PitchValue</Text>
        <Text style={styles.tagline}>Find value beyond the odds.</Text>
      </View>
      <View style={styles.card}>
        <AppHeader eyebrow={content.eyebrow} title={content.title} />
        <Text style={styles.body}>{content.body}</Text>
        <Button
          onPress={
            lastStep ? onComplete : () => setStep((current) => current + 1)
          }
        >
          {step === 0
            ? 'I am 18 or older'
            : lastStep
              ? 'Open Today'
              : 'Continue'}
        </Button>
      </View>
      <Text style={styles.progress}>
        {step + 1} / {steps.length}
      </Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'space-between',
    padding: spacing.lg,
    paddingVertical: spacing.xl,
  },
  brand: { gap: spacing.xs, marginTop: spacing.xl },
  wordmark: { color: colors.text, fontSize: typeScale.hero, fontWeight: '900' },
  tagline: { color: colors.secondary, fontSize: typeScale.body },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.lg,
    borderWidth: 1,
    gap: spacing.lg,
    padding: spacing.lg,
  },
  body: {
    color: colors.textSecondary,
    fontSize: typeScale.body,
    lineHeight: 25,
  },
  progress: {
    color: colors.textSecondary,
    fontSize: typeScale.caption,
    textAlign: 'center',
  },
});
