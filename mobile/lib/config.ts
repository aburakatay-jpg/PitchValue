import Constants from 'expo-constants';

export function resolveApiBaseUrl(
  isDevelopment: boolean,
  configuredValue: string | undefined,
  hostUri?: string | undefined,
): string | null {
  const configured = configuredValue?.trim();
  if (configured) return configured;
  if (!isDevelopment) return null;

  const debuggerHost = hostUri?.split(':')[0];
  return debuggerHost ? `http://${debuggerHost}:8000` : 'http://localhost:8000';
}

export function isDevelopmentPreviewEnabled(
  isDevelopment: boolean,
  configuredValue: string | undefined,
): boolean {
  return isDevelopment && configuredValue?.trim().toLowerCase() === 'true';
}

export const config = {
  apiBaseUrl: resolveApiBaseUrl(
    __DEV__,
    process.env.EXPO_PUBLIC_API_BASE_URL,
    Constants.expoConfig?.hostUri,
  ),
  developmentPreviewEnabled: isDevelopmentPreviewEnabled(
    __DEV__,
    process.env.EXPO_PUBLIC_ENABLE_MOCK_DATA,
  ),
} as const;
