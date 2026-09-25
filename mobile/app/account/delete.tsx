import { useRouter, type Href } from 'expo-router';
import { useState, useCallback, useMemo } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  Platform,
} from 'react-native';
import { SymbolView, type SFSymbol } from 'expo-symbols';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Screen, sharedStyles, stackScreenEdges } from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { initiateAccountDeletion } from '@/lib/product-api';
import { acquireAppleRevocationCredential, acquireGoogleRevocationCredential } from '@/lib/provider-auth';
import { colors, spacing, touchTarget, typography, createThemedStyleSheet } from '@/theme/tokens';
import type { AccountDeletionResponse } from '@/types/product-services';
import * as SecureStore from 'expo-secure-store';

export default function DeleteAccountScreen() {
  const router = useRouter();
  const { t } = useLanguage();
  const session = useProductSession();
  const entitlement = useEntitlement();
  
  const [step, setStep] = useState<
    'CONSEQUENCES' | 'WARNING' | 'REAUTH' | 'FINAL_CONFIRM' | 'PROCESSING' | 'COMPLETED'
  >('CONSEQUENCES');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [deletionState, setDeletionState] = useState<string | null>(null);

  const isGuest = session.state === 'GUEST';

  const hasSubscription = 
    entitlement.state === 'PREMIUM_ACTIVE' || entitlement.state === 'PREMIUM_TRIAL';

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
      
      const payloadProof = isGuest ? null : (authProof || password);
      
      const response = await initiateAccountDeletion(
        session.accessToken,
        payloadProof,
        providerCred,
        new AbortController().signal
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
      } else if (response.deletion_state === 'FAILED_RETRYABLE' || response.deletion_state === 'CREDENTIAL_REQUIRED') {
        setStep('REAUTH');
        setError(t('Additional authorization required or temporary failure.'));
      }
    } catch (e: any) {
      setStep('REAUTH');
      setError(e?.message || t('Deletion failed'));
      setPassword('');
      setAuthProof(null);
      setProviderCred(null);
    }
  };

  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <ScrollView contentContainerStyle={styles.container}>
        {step === 'CONSEQUENCES' && (
          <View style={styles.card}>
            <Text style={styles.title}>{t('Delete Account')}</Text>
            <Text style={styles.bodyText}>
              {t('Deleting your account is permanent. It will remove your profile, preferences, My Bets, and all saved selections from this device.')}
            </Text>
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
            <Text style={styles.title}>{t('Active Subscription')}</Text>
            <Text style={styles.bodyText}>
              {t('Deleting your PitchValue account does not automatically cancel your App Store or Google Play subscription. You must manage your billing separately.')}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={openSubscriptionManagement}
              style={styles.buttonSecondary}
            >
              <Text style={styles.buttonSecondaryText}>{t('Manage Subscription')}</Text>
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
            <Text style={styles.title}>{t('Security Confirmation')}</Text>
            <Text style={styles.bodyText}>
              {t('Please verify your identity to confirm this action.')}
            </Text>
            
            <Pressable
              accessibilityRole="button"
              onPress={async () => {
                setError(null);
                try {
                  const result = await acquireAppleRevocationCredential();
                  if (result && result.authProof) {
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
              style={[styles.button, { backgroundColor: '#000', marginBottom: 12 }]}
            >
              <Text style={{ color: '#fff', fontWeight: '600' }}>{t('Verify with Apple')}</Text>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={async () => {
                setError(null);
                try {
                  const result = await acquireGoogleRevocationCredential();
                  if (result && result.authProof) {
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
              style={[styles.button, { backgroundColor: '#4285F4', marginBottom: 24 }]}
            >
              <Text style={{ color: '#fff', fontWeight: '600' }}>{t('Verify with Google')}</Text>
            </Pressable>

            <Text style={styles.bodyText}>{t('Or enter your password:')}</Text>
            <TextInput
              style={styles.input}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              placeholder={t('Password')}
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
            <Text style={styles.title}>{t('Final Confirmation')}</Text>
            <Text style={styles.bodyText}>
              {t('Are you sure you want to permanently delete your account? This action cannot be undone.')}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={executeDeletion}
              style={[styles.button, styles.destructiveButton]}
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
            <Text style={styles.title}>{t('Processing')}</Text>
            <Text style={styles.bodyText}>{t('Deleting your account...')}</Text>
          </View>
        )}

        {step === 'COMPLETED' && (
          <View style={styles.card}>
            <Text style={styles.title}>{t('Account Deleted')}</Text>
            <Text style={styles.bodyText}>
              {deletionState === 'DELETED' 
                ? t('Your account has been successfully deleted.')
                : t('Your account deletion is processing. You have been securely signed out.')}
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
      </ScrollView>
    </Screen>
  );
}

const styles = createThemedStyleSheet({
  container: {
    padding: spacing.md,
    gap: spacing.md,
  },
  card: {
    ...sharedStyles.card,
    gap: spacing.md,
    padding: spacing.md,
  },
  title: {
    ...typography.pageTitle,
    color: colors.text,
    textAlign: 'center',
  },
  bodyText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
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
    padding: spacing.sm,
    alignItems: 'center',
  },
  textButtonText: {
    ...typography.body,
    color: colors.interactiveTextAccent,
  },
  button: {
    padding: spacing.md,
    borderRadius: 8,
    backgroundColor: colors.primary,
    alignItems: 'center',
  },
  buttonText: {
    ...typography.body,
    fontWeight: '600',
    color: colors.text,
  },
  buttonSecondary: {
    padding: spacing.md,
    borderRadius: 8,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
  },
  buttonSecondaryText: {
    ...typography.body,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    borderRadius: 8,
    ...typography.body,
    color: colors.text,
  },
});
