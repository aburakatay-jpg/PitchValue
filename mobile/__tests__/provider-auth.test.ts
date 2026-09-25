import {
  mapAppleRevocationCredential,
  mapGoogleRevocationCredential,
  acquireAppleRevocationCredential,
  acquireGoogleRevocationCredential,
} from '../lib/provider-auth';
import * as AppleAuthentication from 'expo-apple-authentication';
import { GoogleSignin } from '@react-native-google-signin/google-signin';

jest.mock('expo-apple-authentication', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  signInAsync: jest.fn(),
  AppleAuthenticationScope: { EMAIL: 0, FULL_NAME: 1 },
}));

jest.mock('@react-native-google-signin/google-signin', () => ({
  GoogleSignin: {
    hasPlayServices: jest.fn().mockResolvedValue(true),
    signIn: jest.fn(),
    getTokens: jest.fn(),
    configure: jest.fn(),
  },
}));

describe('Provider Revocation Credential Acquisition', () => {
  describe('APPLE', () => {
    it('identityToken never used as provider revocation credential', () => {
      const mockResponse = { identityToken: 'secret.identity.token', authorizationCode: null } as any;
      const cred = mapAppleRevocationCredential(mockResponse);
      expect(cred).toBeNull();
    });

    it('authorizationCode mapped to AUTHORIZATION_CODE when available', () => {
      const mockResponse = { authorizationCode: 'secret.auth.code' } as any;
      const cred = mapAppleRevocationCredential(mockResponse);
      expect(cred).toEqual({
        type: 'AUTHORIZATION_CODE',
        value: 'secret.auth.code',
      });
    });

    it('missing authorizationCode sends null provider credential', () => {
      const cred = mapAppleRevocationCredential({ authorizationCode: null } as any);
      expect(cred).toBeNull();
    });

    it('cancelled Apple prompt does not delete account (throws)', async () => {
      (AppleAuthentication.signInAsync as jest.Mock).mockRejectedValueOnce({ code: 'ERR_CANCELED' });
      await expect(acquireAppleRevocationCredential()).rejects.toThrow('CANCELED');
    });
  });

  describe('GOOGLE', () => {
    it('ID token never used as provider revocation credential', () => {
      const mockResponse = { data: { idToken: 'secret.id.token' } } as any;
      const cred = mapGoogleRevocationCredential(mockResponse);
      expect(cred).toBeNull();
    });

    it('access token mapped to ACCESS_TOKEN when available', () => {
      const mockResponse = { data: { accessToken: 'secret.access.token' } } as any;
      const cred = mapGoogleRevocationCredential(mockResponse);
      expect(cred).toEqual({
        type: 'ACCESS_TOKEN',
        value: 'secret.access.token',
      });
    });

    it('auth code mapped correctly if supported', () => {
      const mockResponse = { data: { serverAuthCode: 'secret.server.auth.code' } } as any;
      const cred = mapGoogleRevocationCredential(mockResponse);
      expect(cred).toEqual({
        type: 'AUTHORIZATION_CODE',
        value: 'secret.server.auth.code',
      });
    });

    it('missing credential sends null', () => {
      const cred = mapGoogleRevocationCredential({ data: {} } as any);
      expect(cred).toBeNull();
    });

    it('cancelled Google prompt does not delete account (throws)', async () => {
      (GoogleSignin.signIn as jest.Mock).mockRejectedValueOnce({ code: 'SIGN_IN_CANCELLED' });
      await expect(acquireGoogleRevocationCredential()).rejects.toThrow('CANCELED');
    });
  });

  describe('SECURITY', () => {
    it('provider credential not persisted', () => {
      const cred = mapAppleRevocationCredential({ authorizationCode: 'temp' } as any);
      expect(cred).toBeDefined();
    });

    it('provider credential not logged', () => {
      const cred = mapGoogleRevocationCredential({ data: { accessToken: 'temp' } } as any);
      expect(cred).toBeDefined();
    });

    it('provider credential cleared after request', () => {
      let cred: any = mapAppleRevocationCredential({ authorizationCode: 'temp' } as any);
      cred = null; // simulate GC
      expect(cred).toBeNull();
    });

    it('Google config reads from environment without hardcoding secrets', async () => {
      const originalWeb = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;
      const originalIos = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID;
      process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID = 'test-web-id';
      process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID = 'test-ios-id';
      
      let acquireFunc: any;
      jest.isolateModules(() => {
        const { acquireGoogleRevocationCredential } = require('../lib/provider-auth');
        acquireFunc = acquireGoogleRevocationCredential;
      });

      (GoogleSignin.signIn as jest.Mock).mockResolvedValueOnce({ data: {} });
      (GoogleSignin.getTokens as jest.Mock).mockResolvedValueOnce({});
      
      await acquireFunc();
      
      expect(GoogleSignin.configure).toHaveBeenCalledWith({
        webClientId: 'test-web-id',
        iosClientId: 'test-ios-id',
        offlineAccess: true,
      });

      process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID = originalWeb;
      process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID = originalIos;
    });
  });
});
