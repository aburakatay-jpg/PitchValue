export type ProviderCredential = {
  type: 'AUTHORIZATION_CODE' | 'ACCESS_TOKEN' | 'REFRESH_TOKEN';
  value: string;
};

/**
 * Maps Apple authentication response to a valid revocation credential.
 * @param response A mock object representing an Apple authentication response.
 */
export function mapAppleRevocationCredential(
  response: any,
): ProviderCredential | null {
  // identityToken MUST NEVER be used as a revocation credential.
  if (response?.authorizationCode) {
    return {
      type: 'AUTHORIZATION_CODE',
      value: response.authorizationCode,
    };
  }
  return null;
}

/**
 * Maps Google authentication response to a valid revocation credential.
 * @param response A mock object representing a Google authentication response.
 */
export function mapGoogleRevocationCredential(
  response: any,
): ProviderCredential | null {
  // ID token MUST NEVER be used as a revocation credential.
  if (response?.accessToken) {
    return {
      type: 'ACCESS_TOKEN',
      value: response.accessToken,
    };
  }
  if (response?.serverAuthCode) {
    return {
      type: 'AUTHORIZATION_CODE',
      value: response.serverAuthCode,
    };
  }
  return null;
}

/**
 * Acquires a revocation credential for Apple.
 * Currently missing native dependency: expo-apple-authentication
 */
export async function acquireAppleRevocationCredential(): Promise<ProviderCredential | null> {
  return null;
}

/**
 * Acquires a revocation credential for Google.
 * Currently missing native dependency: @react-native-google-signin/google-signin
 */
export async function acquireGoogleRevocationCredential(): Promise<ProviderCredential | null> {
  return null;
}
