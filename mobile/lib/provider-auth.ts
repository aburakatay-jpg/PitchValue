import * as AppleAuthentication from 'expo-apple-authentication';
import { GoogleSignin } from '@react-native-google-signin/google-signin';

export type ProviderCredential = {
  type: 'AUTHORIZATION_CODE' | 'ACCESS_TOKEN' | 'REFRESH_TOKEN';
  value: string;
};

/**
 * Maps Apple authentication response to a valid revocation credential.
 * @param response An Apple authentication response.
 */
export function mapAppleRevocationCredential(
  response: AppleAuthentication.AppleAuthenticationCredential,
): ProviderCredential | null {
  // identityToken MUST NEVER be used as a revocation credential.
  if (response.authorizationCode) {
    return {
      type: 'AUTHORIZATION_CODE',
      value: response.authorizationCode,
    };
  }
  return null;
}

/**
 * Maps Google authentication response to a valid revocation credential.
 * @param response A Google authentication response.
 */
export function mapGoogleRevocationCredential(
  response: any,
): ProviderCredential | null {
  // ID token MUST NEVER be used as a revocation credential.
  if (response?.data?.accessToken) {
    return {
      type: 'ACCESS_TOKEN',
      value: response.data.accessToken,
    };
  }
  if (response?.data?.serverAuthCode) {
    return {
      type: 'AUTHORIZATION_CODE',
      value: response.data.serverAuthCode,
    };
  }
  return null;
}

export type ProviderAuthResult = {
  authProof: string | null;
  revocationCredential: ProviderCredential | null;
};

/**
 * Acquires a revocation credential for Apple.
 */
export async function acquireAppleRevocationCredential(): Promise<ProviderAuthResult | null> {
  try {
    const isAvailable = await AppleAuthentication.isAvailableAsync();
    if (!isAvailable) {
      return null;
    }
    const credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
    });
    return {
      authProof: credential.identityToken,
      revocationCredential: mapAppleRevocationCredential(credential),
    };
  } catch (e: any) {
    if (e.code === 'ERR_CANCELED') {
      throw new Error('CANCELED');
    }
    return null;
  }
}

let isGoogleConfigured = false;

function ensureGoogleConfigured() {
  if (!isGoogleConfigured) {
    GoogleSignin.configure({
      webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID,
      iosClientId: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID,
      offlineAccess: true, // Needed for serverAuthCode
    });
    isGoogleConfigured = true;
  }
}

/**
 * Acquires a revocation credential for Google.
 */
export async function acquireGoogleRevocationCredential(): Promise<ProviderAuthResult | null> {
  try {
    ensureGoogleConfigured();
    await GoogleSignin.hasPlayServices();
    const credential = await GoogleSignin.signIn();
    // We get accessToken differently in v16 or using getTokens()
    const tokens = await GoogleSignin.getTokens();
    const mockResponse = {
      data: {
        accessToken: tokens.accessToken,
        serverAuthCode: credential.data?.serverAuthCode,
      }
    };
    return {
      authProof: credential.data?.idToken ?? null,
      revocationCredential: mapGoogleRevocationCredential(mockResponse),
    };
  } catch (e: any) {
    if (e.code === 'SIGN_IN_CANCELLED' || e.code === '12501') {
      throw new Error('CANCELED');
    }
    return null;
  }
}
