import { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SymbolView, type SFSymbol } from 'expo-symbols';

import {
  CountrySelector,
  type RegistrationCountry,
} from '@/components/CountrySelector';
import {
  Button,
  Screen,
  sharedStyles,
  stackScreenEdges,
} from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { ProductServiceError } from '@/lib/product-api';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

export const authErrorCopy = {
  INVALID_EMAIL: 'Enter a valid email address.',
  INCORRECT_CREDENTIALS: 'The email or password is incorrect.',
  ACCOUNT_EXISTS: 'An account already exists for this email.',
  NETWORK_UNAVAILABLE: 'Your network connection is unavailable.',
  SERVICE_UNAVAILABLE: 'Account services are temporarily unavailable.',
  UNABLE_TO_SIGN_IN: 'Unable to sign in',
  UNABLE_TO_CREATE: 'Account cannot be created right now.',
} as const;

type PasswordInputProps = Readonly<{
  labelId: string;
  password: string;
  setPassword: (value: string) => void;
  onBlur?: (() => void) | undefined;
  onSubmit?: (() => void) | undefined;
  inputRef?: React.RefObject<TextInput | null> | undefined;
  autoComplete: 'current-password' | 'new-password';
}>;

function PasswordInput({
  labelId,
  password,
  setPassword,
  onBlur,
  onSubmit,
  inputRef,
  autoComplete,
}: PasswordInputProps) {
  const { t } = useLanguage();
  const [focused, setFocused] = useState(false);
  const [visible, setVisible] = useState(false);

  return (
    <View style={[styles.inputFrame, focused && styles.inputFocused]}>
      <TextInput
        ref={inputRef}
        accessibilityLabel={t('Password')}
        accessibilityLabelledBy={labelId}
        autoCapitalize="none"
        autoComplete={autoComplete}
        onBlur={() => {
          setFocused(false);
          onBlur?.();
        }}
        onChangeText={setPassword}
        onFocus={() => setFocused(true)}
        onSubmitEditing={onSubmit}
        returnKeyType="done"
        secureTextEntry={!visible}
        style={[styles.bareInput, styles.passwordInput]}
        textContentType={
          autoComplete === 'new-password' ? 'newPassword' : 'password'
        }
        value={password}
      />
      <Pressable
        accessibilityLabel={visible ? t('Hide password') : t('Show password')}
        accessibilityRole="button"
        onPress={() => setVisible((current) => !current)}
        style={({ pressed }) => [styles.eyeButton, pressed && styles.pressed]}
        testID="password-visibility-toggle"
      >
        <SymbolView
          name={(visible ? 'eye.slash' : 'eye') as SFSymbol}
          size={21}
          tintColor={colors.textSecondary}
        />
      </Pressable>
    </View>
  );
}

function AuthHeading({ title }: { title: string }) {
  return (
    <View style={styles.authHeading}>
      <Text style={styles.brand}>PitchValue</Text>
      <Text accessibilityRole="header" style={styles.welcomeTitle}>
        {title}
      </Text>
    </View>
  );
}

export function SignInShell({
  onSignIn,
  onCreateAccount,
}: {
  onSignIn?: ((email: string, password: string) => Promise<void>) | undefined;
  onCreateAccount: () => void;
}) {
  const { t } = useLanguage();
  const passwordInput = useRef<TextInput>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailFocused, setEmailFocused] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const validEmail = /^\S+@\S+\.\S+$/.test(email.trim());

  const submit = async () => {
    setEmailTouched(true);
    setServiceError(null);
    if (!validEmail || !password || !onSignIn || submitting) return;
    setSubmitting(true);
    try {
      await onSignIn(email.trim(), password);
    } catch (error) {
      setServiceError(
        error instanceof ProductServiceError && error.kind === 'UNAUTHORIZED'
          ? authErrorCopy.INCORRECT_CREDENTIALS
          : authErrorCopy.UNABLE_TO_SIGN_IN,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Screen keyboardAware safeAreaEdges={stackScreenEdges}>
      <AuthHeading title={t('Welcome back')} />
      <View style={styles.form}>
        <Text nativeID="sign-in-email-label" style={styles.label}>
          {t('Email')}
        </Text>
        <View style={[styles.inputFrame, emailFocused && styles.inputFocused]}>
          <TextInput
            accessibilityLabel={t('Email')}
            accessibilityLabelledBy="sign-in-email-label"
            autoCapitalize="none"
            autoComplete="email"
            autoCorrect={false}
            keyboardType="email-address"
            onBlur={() => {
              setEmailFocused(false);
              setEmailTouched(true);
            }}
            onChangeText={setEmail}
            onFocus={() => setEmailFocused(true)}
            onSubmitEditing={() => passwordInput.current?.focus()}
            returnKeyType="next"
            style={styles.bareInput}
            textContentType="emailAddress"
            value={email}
          />
        </View>
        {emailTouched && !validEmail ? (
          <InlineError message={t(authErrorCopy.INVALID_EMAIL)} />
        ) : null}

        <Text nativeID="sign-in-password-label" style={styles.label}>
          {t('Password')}
        </Text>
        <PasswordInput
          autoComplete="current-password"
          inputRef={passwordInput}
          labelId="sign-in-password-label"
          onSubmit={() => void submit()}
          password={password}
          setPassword={setPassword}
        />
        {serviceError ? <InlineError message={t(serviceError)} /> : null}
        <Button
          accessibilityLabel={t('Sign In')}
          disabled={!onSignIn || submitting}
          onPress={() => void submit()}
          testID="auth-primary"
        >
          {submitting ? t('Please wait') : t('Sign In')}
        </Button>
        <InlineNavigation
          label={t("Don't have an account?")}
          linkLabel={t('Sign Up')}
          onPress={onCreateAccount}
          accessibilityLabel={t('Create an account')}
          testID="auth-create-account"
        />
      </View>

      <View accessibilityLabel={t('or')} style={styles.divider}>
        <View style={styles.line} />
        <Text style={styles.secondary}>{t('or')}</Text>
        <View style={styles.line} />
      </View>
      <View style={styles.socialStack}>
        <SocialAuthButton provider="Apple" />
        <SocialAuthButton provider="Google" />
      </View>
    </Screen>
  );
}

type CreateAccountProps = Readonly<{
  onSignUp?:
    | ((
        email: string,
        password: string,
        countryCode: string,
        ageAcknowledged: boolean,
      ) => Promise<{ deliveryState: string }>)
    | undefined;
  onVerify?: ((token: string) => Promise<void>) | undefined;
  onSignIn: () => void;
  onOpenTerms?: (() => void) | undefined;
  onOpenPrivacy?: (() => void) | undefined;
}>;

export function CreateAccountShell({
  onSignUp,
  onVerify,
  onSignIn,
  onOpenTerms,
  onOpenPrivacy,
}: CreateAccountProps) {
  const { language, t } = useLanguage();
  const passwordInput = useRef<TextInput>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [country, setCountry] = useState<RegistrationCountry | null>(null);
  const [ageAccepted, setAgeAccepted] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [riskAccepted, setRiskAccepted] = useState(false);
  const [emailFocused, setEmailFocused] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [verificationToken, setVerificationToken] = useState('');
  const [deliveryState, setDeliveryState] = useState<string | null>(null);

  const normalizedEmail = email.trim();
  const validEmail = /^\S+@\S+\.\S+$/.test(normalizedEmail);
  const validPassword =
    password.length >= 8 &&
    password.toLowerCase() !== normalizedEmail.toLowerCase();
  const canSubmit = Boolean(
    onSignUp &&
    validEmail &&
    validPassword &&
    country?.apiCode &&
    ageAccepted &&
    termsAccepted &&
    riskAccepted &&
    !submitting,
  );

  const submit = async () => {
    setEmailTouched(true);
    setPasswordTouched(true);
    setServiceError(null);
    if (!canSubmit || !country?.apiCode || !onSignUp) return;
    setSubmitting(true);
    try {
      const result = await onSignUp(
        normalizedEmail,
        password,
        country.apiCode,
        true,
      );
      setDeliveryState(result.deliveryState);
    } catch (error) {
      setServiceError(
        error instanceof ProductServiceError && error.kind === 'CONFLICT'
          ? authErrorCopy.ACCOUNT_EXISTS
          : authErrorCopy.UNABLE_TO_CREATE,
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (deliveryState) {
    return (
      <VerificationShell
        deliveryState={deliveryState}
        onVerify={onVerify}
        token={verificationToken}
        setToken={setVerificationToken}
      />
    );
  }

  return (
    <Screen keyboardAware safeAreaEdges={stackScreenEdges}>
      <AuthHeading title={t('Create your account')} />
      <View style={styles.form}>
        <Text nativeID="registration-email-label" style={styles.label}>
          {t('Email')}
        </Text>
        <View style={[styles.inputFrame, emailFocused && styles.inputFocused]}>
          <TextInput
            accessibilityLabel={t('Email')}
            accessibilityLabelledBy="registration-email-label"
            autoCapitalize="none"
            autoComplete="email"
            autoCorrect={false}
            keyboardType="email-address"
            onBlur={() => {
              setEmailFocused(false);
              setEmailTouched(true);
            }}
            onChangeText={setEmail}
            onFocus={() => setEmailFocused(true)}
            onSubmitEditing={() => passwordInput.current?.focus()}
            returnKeyType="next"
            style={styles.bareInput}
            textContentType="emailAddress"
            value={email}
          />
        </View>
        {emailTouched && !validEmail ? (
          <InlineError message={t(authErrorCopy.INVALID_EMAIL)} />
        ) : null}

        <Text nativeID="registration-password-label" style={styles.label}>
          {t('Password')}
        </Text>
        <PasswordInput
          autoComplete="new-password"
          inputRef={passwordInput}
          labelId="registration-password-label"
          onBlur={() => setPasswordTouched(true)}
          onSubmit={() => void submit()}
          password={password}
          setPassword={setPassword}
        />
        {passwordTouched && !validPassword ? (
          <InlineError
            message={t(
              password.length >= 8 &&
                password.toLowerCase() === normalizedEmail.toLowerCase()
                ? 'Password cannot be the same as email.'
                : 'Password must be at least 8 characters.',
            )}
          />
        ) : null}

        <Text style={styles.label}>{t('Country')}</Text>
        <CountrySelector selected={country} onSelect={setCountry} />
        {country?.value === 'OTHER' ? (
          <InlineError
            message={t('Registration for other regions is not available yet.')}
          />
        ) : null}

        <View style={styles.acknowledgements}>
          <AcknowledgementRow
            checked={ageAccepted}
            label={t('I am 18 years of age or older.')}
            onChange={setAgeAccepted}
            testID="age-acknowledgement"
          />
          <AcknowledgementRow
            checked={termsAccepted}
            label={t('I accept the Terms of Use.')}
            onChange={setTermsAccepted}
            testID="terms-acknowledgement"
          >
            <Text style={styles.acknowledgementText}>
              {language === 'tr' ? null : t('I accept the ')}
              <Text
                accessibilityRole="link"
                onPress={(event) => {
                  event.stopPropagation();
                  onOpenTerms?.();
                }}
                style={styles.inlineLink}
              >
                {t('Terms of Use')}
              </Text>
              {t('Terms acceptance suffix')}
            </Text>
          </AcknowledgementRow>
          <AcknowledgementRow
            checked={riskAccepted}
            label={t(
              'I understand that betting involves a risk of financial loss.',
            )}
            onChange={setRiskAccepted}
            testID="risk-acknowledgement"
          />
          <View style={styles.informationRow} testID="privacy-information">
            <SymbolView
              accessibilityElementsHidden
              name={'info.circle' as SFSymbol}
              size={20}
              tintColor={colors.textSecondary}
            />
            <Text style={styles.informationText}>
              {t('Privacy information prefix')}{' '}
              <Text
                accessibilityRole="link"
                onPress={onOpenPrivacy}
                style={styles.inlineLink}
              >
                {t('Privacy Policy')}
              </Text>
              {t('Privacy information suffix')}
            </Text>
          </View>
        </View>

        {serviceError ? <InlineError message={t(serviceError)} /> : null}
        <Button
          accessibilityLabel={t('Create Account')}
          disabled={!canSubmit}
          onPress={() => void submit()}
          testID="create-account-primary"
        >
          {submitting ? t('Please wait') : t('Create Account')}
        </Button>
        <InlineNavigation
          accessibilityLabel={t('Sign In')}
          label={t('Already have an account?')}
          linkLabel={t('Sign In')}
          onPress={onSignIn}
          testID="registration-sign-in"
        />
      </View>
    </Screen>
  );
}

function VerificationShell({
  deliveryState,
  onVerify,
  token,
  setToken,
}: Readonly<{
  deliveryState: string;
  onVerify?: ((token: string) => Promise<void>) | undefined;
  token: string;
  setToken: (value: string) => void;
}>) {
  const { t } = useLanguage();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unavailable = deliveryState === 'VERIFICATION_DELIVERY_UNAVAILABLE';

  const verify = async () => {
    if (!token.trim() || !onVerify || unavailable || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onVerify(token.trim());
    } catch {
      setError(authErrorCopy.SERVICE_UNAVAILABLE);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Screen keyboardAware safeAreaEdges={stackScreenEdges}>
      <AuthHeading title={t('Verify email')} />
      <View style={[sharedStyles.card, styles.form]}>
        <Text style={styles.secondary}>
          {unavailable
            ? t('Email verification currently unavailable.')
            : t('Enter the verification token sent to your email.')}
        </Text>
        {!unavailable ? (
          <>
            <Text nativeID="token-label" style={styles.label}>
              {t('Verification Token')}
            </Text>
            <TextInput
              accessibilityLabel={t('Verification Token')}
              accessibilityLabelledBy="token-label"
              autoCapitalize="none"
              autoCorrect={false}
              onChangeText={setToken}
              onSubmitEditing={() => void verify()}
              returnKeyType="done"
              style={[styles.inputFrame, styles.verificationInput]}
              value={token}
            />
            {error ? <InlineError message={t(error)} /> : null}
            <Button
              disabled={!token.trim() || !onVerify || submitting}
              onPress={() => void verify()}
            >
              {submitting ? t('Please wait') : t('Verify')}
            </Button>
          </>
        ) : null}
      </View>
    </Screen>
  );
}

function AcknowledgementRow({
  checked,
  label,
  onChange,
  testID,
  children,
}: Readonly<{
  checked: boolean;
  label: string;
  onChange: (value: boolean) => void;
  testID: string;
  children?: React.ReactNode;
}>) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={() => onChange(!checked)}
      style={({ pressed }) => [
        styles.acknowledgementRow,
        pressed && styles.pressed,
      ]}
      testID={testID}
    >
      <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
        {checked ? (
          <SymbolView
            accessibilityElementsHidden
            name={'checkmark' as SFSymbol}
            size={15}
            tintColor={colors.background}
          />
        ) : null}
      </View>
      <View style={styles.acknowledgementCopy}>
        {children ?? <Text style={styles.acknowledgementText}>{label}</Text>}
      </View>
    </Pressable>
  );
}

function InlineNavigation({
  label,
  linkLabel,
  onPress,
  accessibilityLabel,
  testID,
}: Readonly<{
  label: string;
  linkLabel: string;
  onPress: () => void;
  accessibilityLabel: string;
  testID: string;
}>) {
  return (
    <View style={styles.inlineNavigation}>
      <Text style={styles.secondary}>{label}</Text>
      <Pressable
        accessibilityLabel={accessibilityLabel}
        accessibilityRole="link"
        onPress={onPress}
        style={({ pressed }) => pressed && styles.pressed}
        testID={testID}
      >
        <Text style={styles.textLink}>{linkLabel}</Text>
      </Pressable>
    </View>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <Text accessibilityLiveRegion="polite" style={styles.error}>
      {message}
    </Text>
  );
}

function SocialAuthButton({ provider }: { provider: 'Apple' | 'Google' }) {
  const { t } = useLanguage();
  const label = t(`Continue with ${provider}`);
  return (
    <Pressable
      accessibilityLabel={t(`Continue with ${provider}, unavailable`)}
      accessibilityRole="button"
      accessibilityState={{ disabled: true }}
      disabled
      style={styles.socialButton}
      testID={`auth-${provider.toLowerCase()}`}
    >
      <View accessible={false} style={styles.providerIcon}>
        {provider === 'Apple' ? (
          <SymbolView
            name={'apple.logo' as SFSymbol}
            size={22}
            testID="auth-apple-symbol"
            tintColor={colors.text}
          />
        ) : (
          <Text style={styles.googleIcon}>G</Text>
        )}
      </View>
      <Text style={styles.socialButtonText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  authHeading: { gap: spacing.xs },
  brand: { color: colors.accent, ...typography.caption },
  welcomeTitle: { color: colors.text, ...typography.pageTitle },
  form: { gap: spacing.sm },
  divider: { alignItems: 'center', flexDirection: 'row', gap: spacing.md },
  line: { backgroundColor: colors.border, flex: 1, height: 1 },
  secondary: { color: colors.textSecondary, ...typography.body },
  label: { color: colors.text, ...typography.body, fontWeight: '700' },
  inputFrame: {
    alignItems: 'center',
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: touchTarget,
  },
  inputFocused: { borderColor: colors.secondary },
  bareInput: {
    color: colors.text,
    flex: 1,
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    ...typography.body,
  },
  passwordInput: { paddingRight: touchTarget },
  eyeButton: {
    alignItems: 'center',
    height: touchTarget,
    justifyContent: 'center',
    position: 'absolute',
    right: 0,
    width: touchTarget,
  },
  inlineNavigation: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    justifyContent: 'center',
  },
  textLink: { color: colors.secondary, ...typography.body, fontWeight: '700' },
  inlineLink: { color: colors.secondary, fontWeight: '700' },
  socialStack: { gap: spacing.sm },
  socialButton: {
    alignItems: 'center',
    backgroundColor: colors.surfaceRaised,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'center',
    minHeight: touchTarget,
    opacity: 0.72,
    paddingHorizontal: spacing.md,
  },
  providerIcon: {
    alignItems: 'center',
    justifyContent: 'center',
    left: spacing.md,
    position: 'absolute',
    width: touchTarget,
  },
  googleIcon: { color: '#4285F4', fontSize: 21, fontWeight: '800' },
  socialButtonText: {
    color: colors.text,
    ...typography.body,
    fontWeight: '700',
  },
  error: { color: colors.negative, ...typography.caption },
  acknowledgements: { gap: spacing.sm, marginVertical: spacing.xs },
  acknowledgementRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: spacing.sm,
    minHeight: touchTarget,
    paddingVertical: spacing.xs,
  },
  acknowledgementCopy: { flex: 1, minHeight: 24, justifyContent: 'center' },
  acknowledgementText: { color: colors.text, ...typography.body },
  checkbox: {
    alignItems: 'center',
    borderColor: colors.textSecondary,
    borderRadius: radii.sm,
    borderWidth: 1,
    height: 22,
    justifyContent: 'center',
    marginTop: 1,
    width: 22,
  },
  checkboxChecked: {
    backgroundColor: colors.secondary,
    borderColor: colors.secondary,
  },
  informationRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: spacing.sm,
    minHeight: touchTarget,
    paddingVertical: spacing.xs,
  },
  informationText: {
    color: colors.textSecondary,
    flex: 1,
    ...typography.caption,
  },
  verificationInput: {
    color: colors.text,
    paddingHorizontal: spacing.md,
    ...typography.body,
  },
  pressed: { opacity: 0.8 },
});
