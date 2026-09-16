const fallbackApiBaseUrl = 'http://localhost:8000';

export function resolveApiBaseUrl(
  isDevelopment: boolean,
  configuredValue: string | undefined,
): string | null {
  const configured = configuredValue?.trim();
  if (configured) return configured;
  return isDevelopment ? fallbackApiBaseUrl : null;
}

export function isDevelopmentPreviewEnabled(
  isDevelopment: boolean,
  configuredValue: string | undefined,
): boolean {
  return isDevelopment && configuredValue?.trim().toLowerCase() === 'true';
}

export const config = {
  apiBaseUrl: resolveApiBaseUrl(__DEV__, process.env.EXPO_PUBLIC_API_BASE_URL),
  developmentPreviewEnabled: isDevelopmentPreviewEnabled(
    __DEV__,
    process.env.EXPO_PUBLIC_ENABLE_MOCK_DATA,
  ),
} as const;
