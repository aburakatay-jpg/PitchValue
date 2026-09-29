import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  Linking,
  Pressable,
  Text,
  TextInput,
  View,
  Platform,
} from 'react-native';

import { Screen, sharedStyles, stackScreenEdges } from '@/components/ui';
import { LegalModal, LegalTextLink } from '@/components/LegalModal';
import { useLanguage } from '@/features/language/LanguageContext';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { initiateAccountDeletion } from '@/lib/product-api';
import {
  acquireAppleRevocationCredential,
  acquireGoogleRevocationCredential,
} from '@/lib/provider-auth';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
  createThemedStyleSheet,
} from '@/theme/tokens';
import * as SecureStore from 'expo-secure-store';
import type { LegalDocumentId } from '@/legal/content';

export default function DeleteAccountScreen() {
  const router = useRouter();
  const { t } = useLanguage();
  const session = useProductSession();
  const entitlement = useEntitlement();

  const [step, setStep] = useState<
    | 'CONSEQUENCES'
    | 'WARNING'
    | 'REAUTH'
    | 'FINAL_CONFIRM'
    | 'PROCESSING'
    | 'COMPLETED'
  >('CONSEQUENCES');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [deletionState, setDeletionState] = useState<string | null>(null);
  const [legalDocument, setLegalDocument] = useState<LegalDocumentId | null>(
    null,
  );

  const isGuest = session.state === 'GUEST';

  const hasSubscription =
    entitlement.state === 'PREMIUM_ACTIVE' ||
    entitlement.state === 'PREMIUM_TRIAL';

  const onNextFromConsequences = () => {
    if (hasSubscription) {
      setStep('WARNING');
    } else if (isGuest) {
      setStep('FINAL_CONFIRM');
    } else {
      setStep('REAUTH');
    }
  };

  const onNextFromWarning = () => {
    if (isGuest) {
      setStep('FINAL_CONFIRM');
    } else {
      setStep('REAUTH');
    }
  };

  const onNextFromReauth = () => {
    if (!password.trim()) {
      setError(t('Password is required'));
      return;
    }
    setError(null);
    setStep('FINAL_CONFIRM');
  };

  const openSubscriptionManagement = () => {
    if (Platform.OS === 'ios') {
      Linking.openURL('https://apps.apple.com/account/subscriptions');
    } else if (Platform.OS === 'android') {
      Linking.openURL('https://play.google.com/store/account/subscriptions');
    }
  };

  const [authProof, setAuthProof] = useState<string | null>(null);
  const [providerCred, setProviderCred] = useState<any>(null);

  const executeDeletion = async () => {
    if (step === 'PROCESSING') return;
    setStep('PROCESSING');
    setError(null);
    try {
      if (!session.accessToken) throw new Error('No token');

      const payloadProof = isGuest ? null : authProof || password;

      const response = await initiateAccountDeletion(
        session.accessToken,
        payloadProof,
        providerCred,
        new AbortController().signal,
      );

      setPassword(''); // Clear immediately
      setAuthProof(null); // Clear immediately
      setProviderCred(null); // Clear immediately
      setDeletionState(response.deletion_state);

      if (response.deletion_state === 'DELETED') {
        await SecureStore.deleteItemAsync('pitchvalue.product.access.v1');
        await SecureStore.deleteItemAsync('pitchvalue.product.refresh.v1');
        await session.signOut();
        setStep('COMPLETED');
      } else if (response.deletion_state === 'PROCESSING') {
        // Asynchronous processing (Apple/Google)
        await SecureStore.deleteItemAsync('pitchvalue.product.access.v1');
        await SecureStore.deleteItemAsync('pitchvalue.product.refresh.v1');
        await session.signOut();
        setStep('COMPLETED');
      } else if (
        response.deletion_state === 'FAILED_RETRYABLE' ||
        response.deletion_state === 'CREDENTIAL_REQUIRED'
      ) {
        setStep('REAUTH');
        setError(t('Additional authorization required or temporary failure.'));
      }
    } catch {
      setStep('REAUTH');
      setError(t('Deletion failed'));
      setPassword('');
      setAuthProof(null);
      setProviderCred(null);
    }
  };

  return (
    <Screen keyboardAware safeAreaEdges={stackScreenEdges}>
      <View style={styles.container}>
        {step === 'CONSEQUENCES' && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {t('Delete Account')}
            </Text>
            <Text style={styles.bodyText}>
              {t(
                'Deleting your account removes your account, sessions and credentials, My Bets and saved selections, followed matches, and push tokens owned by your account. Minimum commerce, entitlement, legal-acceptance, and deletion-audit evidence may be retained and delinked when required.',
              )}
            </Text>
            <Text style={styles.bodyText}>
              {t(
                'An active subscription does not block account deletion. The same email may later be used to create a new account.',
              )}
            </Text>
            <View style={styles.legalLinks}>
              <LegalTextLink
                label={t('Privacy Policy')}
                onPress={() => setLegalDocument('privacy')}
                testID="delete-legal-privacy"
              />
              <LegalTextLink
                label={t('Terms of Use')}
                onPress={() => setLegalDocument('terms')}
                testID="delete-legal-terms"
              />
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={onNextFromConsequences}
              style={[styles.button, styles.destructiveButton]}
            >
              <Text style={styles.buttonText}>{t('Continue')}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.back()}
              style={styles.buttonSecondary}
            >
              <Text style={styles.buttonSecondaryText}>{t('Cancel')}</Text>
            </Pressable>
          </View>
        )}

        {step === 'WARNING' && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {t('Active Subscription')}
            </Text>
            <Text style={styles.bodyText}>
              {t(
                'Deleting your PitchValue account does not automatically cancel your App Store or Google Play subscription. You must manage your billing separately.',
              )}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={openSubscriptionManagement}
              style={styles.buttonSecondary}
            >
              <Text style={styles.buttonSecondaryText}>
                {t('Manage Subscription')}
              </Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={onNextFromWarning}
              style={styles.button}
            >
              <Text style={styles.buttonText}>{t('Continue')}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.back()}
              style={styles.textButton}
            >
              <Text style={styles.textButtonText}>{t('Cancel')}</Text>
            </Pressable>
          </View>
        )}

        {step === 'REAUTH' && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {t('Security Confirmation')}
            </Text>
            <Text style={styles.bodyText}>
              {t('Please verify your identity to confirm this action.')}
            </Text>

            <Pressable
              accessibilityRole="button"
              onPress={async () => {
                setError(null);
                try {
                  const result = await acquireAppleRevocationCredential();
                  if (result?.providerUnavailable) {
                    setError(
                      t('Apple verification is unavailable in this build.'),
                    );
                  } else if (result && result.authProof) {
                    setAuthProof(result.authProof);
                    setProviderCred(result.revocationCredential);
                    setStep('FINAL_CONFIRM');
                  }
                } catch (e: any) {
                  if (e.message !== 'CANCELED') {
                    setError(t('Apple verification failed.'));
                  }
                }
              }}
              style={[styles.button, styles.providerButton]}
            >
              <Text style={styles.providerButtonText}>
                {t('Verify with Apple')}
              </Text>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={async () => {
                setError(null);
                try {
                  const result = await acquireGoogleRevocationCredential();
                  if (result?.providerUnavailable) {
                    setError(
                      t('Google verification is unavailable in this build.'),
                    );
                  } else if (result && result.authProof) {
                    setAuthProof(result.authProof);
                    setProviderCred(result.revocationCredential);
                    setStep('FINAL_CONFIRM');
                  }
                } catch (e: any) {
                  if (e.message !== 'CANCELED') {
                    setError(t('Google verification failed.'));
                  }
                }
              }}
              style={[styles.button, styles.providerButton]}
            >
              <Text style={styles.providerButtonText}>
                {t('Verify with Google')}
              </Text>
            </Pressable>

            <Text style={styles.bodyText}>{t('Or enter your password:')}</Text>
            <TextInput
              style={styles.input}
              accessibilityLabel={t('Password')}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              placeholder={t('Password')}
              placeholderTextColor={colors.textSecondary}
              autoCapitalize="none"
              autoCorrect={false}
            />
            {error && <Text style={styles.errorText}>{error}</Text>}
            <Pressable
              accessibilityRole="button"
              onPress={onNextFromReauth}
              style={styles.button}
            >
              <Text style={styles.buttonText}>{t('Verify with Password')}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.back()}
              style={styles.buttonSecondary}
            >
              <Text style={styles.buttonSecondaryText}>{t('Cancel')}</Text>
            </Pressable>
          </View>
        )}

        {step === 'FINAL_CONFIRM' && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {t('Final Confirmation')}
            </Text>
            <Text style={styles.bodyText}>
              {t(
                'Are you sure you want to permanently delete your account? This action cannot be undone.',
              )}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={executeDeletion}
              style={[styles.button, styles.destructiveButton]}
              testID="delete-account-confirm-action"
            >
              <Text style={styles.buttonText}>{t('Delete Account')}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.back()}
              style={styles.buttonSecondary}
            >
              <Text style={styles.buttonSecondaryText}>{t('Cancel')}</Text>
            </Pressable>
          </View>
        )}

        {step === 'PROCESSING' && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {t('Processing')}
            </Text>
            <Text style={styles.bodyText}>{t('Deleting your account...')}</Text>
          </View>
        )}

        {step === 'COMPLETED' && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {t('Account Deleted')}
            </Text>
            <Text style={styles.bodyText}>
              {deletionState === 'DELETED'
                ? t('Your account has been successfully deleted.')
                : t(
                    'Your account deletion is processing. You have been securely signed out.',
                  )}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.replace('/')}
              style={styles.button}
            >
              <Text style={styles.buttonText}>{t('Return Home')}</Text>
            </Pressable>
          </View>
        )}
      </View>
      <LegalModal
        documentId={legalDocument}
        onClose={() => setLegalDocument(null)}
      />
    </Screen>
  );
}

const styles = createThemedStyleSheet({
  container: {
    gap: spacing.lg,
    paddingVertical: spacing.md,
  },
  card: {
    ...sharedStyles.card,
    gap: spacing.lg,
    padding: spacing.lg,
  },
  title: {
    ...typography.sectionTitle,
    color: colors.text,
  },
  bodyText: {
    ...typography.body,
    color: colors.textSecondary,
  },
  errorText: {
    ...typography.body,
    color: colors.negative,
    textAlign: 'center',
  },
  destructiveButton: {
    backgroundColor: colors.negative,
  },
  textButton: {
    minHeight: touchTarget,
    padding: spacing.sm,
    justifyContent: 'center',
    alignItems: 'center',
  },
  textButtonText: {
    ...typography.body,
    color: colors.interactiveTextAccent,
  },
  button: {
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.md,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: {
    ...typography.body,
    fontWeight: '600',
    color: colors.onBrand,
  },
  providerButton: {
    backgroundColor: colors.surfaceRaised,
    borderColor: colors.border,
    borderWidth: 1,
  },
  providerButtonText: {
    ...typography.body,
    color: colors.text,
    fontWeight: '600',
  },
  buttonSecondary: {
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.md,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonSecondaryText: {
    ...typography.body,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.inputBackground,
    padding: spacing.md,
    borderRadius: radii.md,
    ...typography.body,
    color: colors.text,
  },
  legalLinks: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    justifyContent: 'center',
  },
});
