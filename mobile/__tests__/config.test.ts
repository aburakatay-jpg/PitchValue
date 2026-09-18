import { resolveApiBaseUrl } from '../lib/config';

describe('resolveApiBaseUrl', () => {
  it('uses explicit EXPO_PUBLIC_API_BASE_URL over everything else', () => {
    expect(
      resolveApiBaseUrl(
        true,
        'https://staging.example.com',
        '192.168.1.108:8081',
      ),
    ).toBe('https://staging.example.com');
    expect(
      resolveApiBaseUrl(
        false,
        'https://api.pitchvalue.com',
        '192.168.1.108:8081',
      ),
    ).toBe('https://api.pitchvalue.com');
  });

  it('falls back to Expo LAN hostUri in development when configuredValue is absent', () => {
    expect(resolveApiBaseUrl(true, undefined, '192.168.1.108:8081')).toBe(
      'http://192.168.1.108:8000',
    );
  });

  it('falls back to localhost in development if hostUri is malformed or missing', () => {
    expect(resolveApiBaseUrl(true, undefined, undefined)).toBe(
      'http://localhost:8000',
    );
    expect(resolveApiBaseUrl(true, undefined, '')).toBe(
      'http://localhost:8000',
    );
  });

  it('rejects Expo hostUri fallback and localhost in production', () => {
    expect(
      resolveApiBaseUrl(false, undefined, '192.168.1.108:8081'),
    ).toBeNull();
    expect(resolveApiBaseUrl(false, undefined, undefined)).toBeNull();
  });
});
