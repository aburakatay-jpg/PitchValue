import { useState } from 'react';
import { StyleSheet, Text, TextInput, View, Switch } from 'react-native';

import {
  Button,
  Screen,
  SectionHeader,
  sharedStyles,
  stackScreenEdges,
} from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import VALID_COUNTRIES from '@/lib/countries.json';
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

type EmailMode = 'SIGN_IN' | 'SIGN_UP' | 'VERIFY';

export function EmailAuthShell({
  onSignIn,
  onSignUp,
  onVerify,
}: {
  onSignIn?: ((email: string, password: string) => Promise<void>) | undefined;
  onSignUp?: ((email: string, password: string, countryCode: string, ageAcknowledged: boolean) => Promise<{ deliveryState: string }>) | undefined;
  onVerify?: ((token: string) => Promise<void>) | undefined;
}) {
  const { t } = useLanguage();
  const [mode, setMode] = useState<EmailMode>('SIGN_IN');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [countryCode, setCountryCode] = useState('');
  const [ageAcknowledged, setAgeAcknowledged] = useState(false);
  const [verificationToken, setVerificationToken] = useState('');

  const [emailTouched, setEmailTouched] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [confirmPasswordTouched, setConfirmPasswordTouched] = useState(false);
  const [countryCodeTouched, setCountryCodeTouched] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);

  const validEmail = /^\S+@\S+\.\S+$/.test(email.trim());
  const validPassword =
    password.length >= 8 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /[0-9]/.test(password) &&
    password.toLowerCase() !== email.toLowerCase().trim();
  const validCountryCode = VALID_COUNTRIES.includes(countryCode.trim().toUpperCase());
  const passwordsMatch = password === confirmPassword;

  const handler = mode === 'SIGN_IN' ? onSignIn : mode === 'SIGN_UP' ? onSignUp : onVerify;

  const submit = async () => {
    setEmailTouched(true);
    setPasswordTouched(true);
    if (mode === 'SIGN_UP') setConfirmPasswordTouched(true);
    setCountryCodeTouched(true);
    setServiceError(null);

    if (mode === 'VERIFY') {
      if (!verificationToken || !onVerify) return;
      setSubmitting(true);
      try {
        await onVerify(verificationToken.trim());
      } catch {
        setServiceError(authErrorCopy.SERVICE_UNAVAILABLE);
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (!validEmail || !validPassword || !handler) return;

    if (mode === 'SIGN_UP') {
      if (!passwordsMatch) return;
      if (!validCountryCode) {
        setServiceError('Enter a valid 2-letter country code.');
        return;
      }
      if (!ageAcknowledged) {
        setServiceError('You must acknowledge that you are 18 or older.');
        return;
      }
    }

    setSubmitting(true);
    try {
      if (mode === 'SIGN_IN') {
        await onSignIn!(email.trim(), password);
      } else if (mode === 'SIGN_UP') {
        const { deliveryState } = await onSignUp!(
          email.trim(),
          password,
          countryCode.trim().toUpperCase(),
          ageAcknowledged,
        );
        if (deliveryState === 'VERIFICATION_DELIVERY_UNAVAILABLE') {
          setServiceError('E-posta teslimi şu anda kullanılamıyor. Daha sonra tekrar deneyin. (Email delivery is currently unavailable.)');
        } else {
          setMode('VERIFY');
        }
      }
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
          mode === 'SIGN_IN'
            ? t('Sign in with email')
            : mode === 'SIGN_UP'
              ? t('Create an account')
              : t('Verify email')
        }
        detail={
          handler
            ? mode === 'VERIFY'
              ? t('Enter the verification token sent to your email.')
              : t('Use your PitchValue email identity. Your session is stored securely on this device.')
            : t('Email sign-in is currently unavailable.')
        }
      />
      {mode !== 'VERIFY' && (
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
      )}
      <View style={sharedStyles.card}>
        {mode === 'VERIFY' ? (
          <>
            <Text nativeID="token-label" style={styles.label}>
              {t('Verification Token')}
            </Text>
            <TextInput
              accessibilityLabelledBy="token-label"
              autoCapitalize="none"
              autoCorrect={false}
              onChangeText={setVerificationToken}
              returnKeyType="done"
              style={styles.input}
              value={verificationToken}
            />
          </>
        ) : (
          <>
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
            <View style={styles.switchRow}>
              <Text nativeID="password-label" style={styles.label}>
                {t('Password')}
              </Text>
              <Button variant="secondary" onPress={() => setShowPassword(!showPassword)}>
                {showPassword ? t('Hide password') : t('Show password')}
              </Button>
            </View>
            <TextInput
              accessibilityLabelledBy="password-label"
              autoCapitalize="none"
              autoComplete={
                mode === 'SIGN_IN' ? 'current-password' : 'new-password'
              }
              onBlur={() => setPasswordTouched(true)}
              onChangeText={setPassword}
              returnKeyType="done"
              secureTextEntry={!showPassword}
              style={styles.input}
              value={password}
            />
            {passwordTouched && !validPassword ? (
              <Text accessibilityLiveRegion="polite" style={styles.error}>
                {password.toLowerCase() === email.toLowerCase().trim() && password.length > 0
                  ? t('Password cannot be the same as email.')
                  : t('Password must be 8+ chars with uppercase, lowercase, and number.')}
              </Text>
            ) : null}

            {mode === 'SIGN_UP' && (
              <>
                <Text nativeID="confirm-password-label" style={styles.label}>
                  {t('Confirm Password')}
                </Text>
                <TextInput
                  accessibilityLabelledBy="confirm-password-label"
                  autoCapitalize="none"
                  autoComplete="new-password"
                  onBlur={() => setConfirmPasswordTouched(true)}
                  onChangeText={setConfirmPassword}
                  returnKeyType="done"
                  secureTextEntry={!showPassword}
                  style={styles.input}
                  value={confirmPassword}
                />
                {confirmPasswordTouched && !passwordsMatch ? (
                  <Text accessibilityLiveRegion="polite" style={styles.error}>
                    {t('Passwords do not match.')}
                  </Text>
                ) : null}
                <Text nativeID="country-label" style={[styles.label, { marginTop: spacing.sm }]}>
                  {t('Country Code (2 letters)')}
                </Text>
                <TextInput
                  accessibilityLabelledBy="country-label"
                  autoCapitalize="characters"
                  maxLength={2}
                  onBlur={() => setCountryCodeTouched(true)}
                  onChangeText={setCountryCode}
                  returnKeyType="next"
                  style={styles.input}
                  value={countryCode}
                />
                {countryCodeTouched && !validCountryCode ? (
                  <Text accessibilityLiveRegion="polite" style={styles.error}>
                    {t('Please enter a valid 2-letter country code.')}
                  </Text>
                ) : null}

                <View style={styles.switchRow}>
                  <Switch
                    onValueChange={setAgeAcknowledged}
                    value={ageAcknowledged}
                  />
                  <Text style={styles.secondary}>
                    {t('I am 18 years of age or older.')}
                  </Text>
                </View>
              </>
            )}
          </>
        )}
        {serviceError ? (
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {t(serviceError)}
          </Text>
        ) : null}
        <Button
          accessibilityLabel={
            mode === 'VERIFY'
              ? t('Verify')
              : mode === 'SIGN_IN'
                ? t('Sign in')
                : t('Sign up')
          }
          disabled={!handler || submitting}
          onPress={() => void submit()}
        >
          {submitting
            ? t('Please wait')
            : mode === 'VERIFY'
              ? t('Verify')
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
  switchRow: { alignItems: 'center', flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
});
