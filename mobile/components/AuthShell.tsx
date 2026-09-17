import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import {
  Button,
  Screen,
  SectionHeader,
  sharedStyles,
  stackScreenEdges,
} from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { colors, radii, spacing, typography } from '@/theme/tokens';

export const authErrorCopy = {
  INVALID_EMAIL: 'Enter a valid email address.',
  INCORRECT_CREDENTIALS: 'The email or password is incorrect.',
  ACCOUNT_EXISTS: 'An account already exists for this email.',
  NETWORK_UNAVAILABLE: 'Your network connection is unavailable.',
  SERVICE_UNAVAILABLE: 'Account services are temporarily unavailable.',
} as const;

export function AuthEntry({
  onEmail,
  onGuest,
}: {
  onEmail: () => void;
  onGuest: () => void;
}) {
  const { t } = useLanguage();
  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <SectionHeader
        title={t('Sign in to PitchValue')}
        detail={t(
          'Email sign-in and Guest discovery are available. Apple and Google require external activation.',
        )}
      />
      <View style={styles.stack}>
        <Button
          accessibilityLabel={t('Continue with Apple, unavailable')}
          disabled
        >
          {t('Continue with Apple')} · {t('Coming later')}
        </Button>
        <Button
          accessibilityLabel={t('Continue with Google, unavailable')}
          disabled
        >
          {t('Continue with Google')} · {t('Coming later')}
        </Button>
        <Button accessibilityLabel={t('Continue with Email')} onPress={onEmail}>
          {t('Continue with Email')}
        </Button>
      </View>
      <View accessibilityLabel={t('or')} style={styles.divider}>
        <View style={styles.line} />
        <Text style={styles.secondary}>{t('or')}</Text>
        <View style={styles.line} />
      </View>
      <Button onPress={onGuest} variant="secondary">
        {t('Continue as Guest')}
      </Button>
      <Text style={styles.caption}>
        {t(
          'SMS sign-in is not offered. Continue as Guest to browse public analysis.',
        )}
      </Text>
    </Screen>
  );
}

type EmailMode = 'SIGN_IN' | 'SIGN_UP';

export function EmailAuthShell({
  onSignIn,
  onSignUp,
}: {
  onSignIn?: ((email: string, password: string) => Promise<void>) | undefined;
  onSignUp?: ((email: string, password: string) => Promise<void>) | undefined;
}) {
  const { t } = useLanguage();
  const [mode, setMode] = useState<EmailMode>('SIGN_IN');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailTouched, setEmailTouched] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const validEmail = /^\S+@\S+\.\S+$/.test(email.trim());
  const validPassword = password.length >= 10;
  const handler = mode === 'SIGN_IN' ? onSignIn : onSignUp;
  const submit = async () => {
    setEmailTouched(true);
    setPasswordTouched(true);
    if (!validEmail || !validPassword || !handler) return;
    setSubmitting(true);
    setServiceError(null);
    try {
      await handler(email.trim(), password);
    } catch {
      setServiceError(
        mode === 'SIGN_IN'
          ? authErrorCopy.INCORRECT_CREDENTIALS
          : authErrorCopy.SERVICE_UNAVAILABLE,
      );
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Screen keyboardAware safeAreaEdges={stackScreenEdges}>
      <SectionHeader
        title={
          mode === 'SIGN_IN' ? t('Sign in with email') : t('Create an account')
        }
        detail={
          handler
            ? t(
                'Use your PitchValue email identity. Your session is stored securely on this device.',
              )
            : t('Email sign-in is currently unavailable.')
        }
      />
      <View style={styles.modeRow}>
        <Button
          onPress={() => setMode('SIGN_IN')}
          variant={mode === 'SIGN_IN' ? 'primary' : 'secondary'}
        >
          {t('Sign In')}
        </Button>
        <Button
          onPress={() => setMode('SIGN_UP')}
          variant={mode === 'SIGN_UP' ? 'primary' : 'secondary'}
        >
          {t('Sign Up')}
        </Button>
      </View>
      <View style={sharedStyles.card}>
        <Text nativeID="email-label" style={styles.label}>
          {t('Email')}
        </Text>
        <TextInput
          accessibilityLabelledBy="email-label"
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          onBlur={() => setEmailTouched(true)}
          onChangeText={setEmail}
          returnKeyType="next"
          style={styles.input}
          value={email}
        />
        {emailTouched && !validEmail ? (
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {t(authErrorCopy.INVALID_EMAIL)}
          </Text>
        ) : null}
        <Text nativeID="password-label" style={styles.label}>
          {t('Password')}
        </Text>
        <TextInput
          accessibilityLabelledBy="password-label"
          autoCapitalize="none"
          autoComplete={
            mode === 'SIGN_IN' ? 'current-password' : 'new-password'
          }
          onBlur={() => setPasswordTouched(true)}
          onChangeText={setPassword}
          returnKeyType="done"
          secureTextEntry
          style={styles.input}
          value={password}
        />
        {passwordTouched && !validPassword ? (
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {t('Password must contain at least 10 characters.')}
          </Text>
        ) : null}
        {serviceError ? (
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {t(serviceError)}
          </Text>
        ) : null}
        <Button
          accessibilityLabel={mode === 'SIGN_IN' ? t('Sign in') : t('Sign up')}
          disabled={!handler || submitting}
          onPress={() => void submit()}
        >
          {submitting
            ? t('Please wait')
            : mode === 'SIGN_IN'
              ? t('Sign In')
              : t('Sign Up')}
        </Button>
        {mode === 'SIGN_IN' ? (
          <Text style={styles.caption}>
            {t('Password recovery is currently unavailable.')}
          </Text>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.sm },
  divider: { alignItems: 'center', flexDirection: 'row', gap: spacing.md },
  line: { backgroundColor: colors.border, flex: 1, height: 1 },
  secondary: { color: colors.textSecondary, ...typography.body },
  caption: { color: colors.textSecondary, ...typography.caption },
  modeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  label: { color: colors.text, ...typography.body, fontWeight: '700' },
  input: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    color: colors.text,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    ...typography.body,
  },
  error: { color: colors.negative, ...typography.metadata },
});
