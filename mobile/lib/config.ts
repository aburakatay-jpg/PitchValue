const fallbackApiBaseUrl = 'http://localhost:8000';

export function isDevelopmentPreviewEnabled(
  isDevelopment: boolean,
  configuredValue: string | undefined,
): boolean {
  return isDevelopment && configuredValue?.trim().toLowerCase() === 'true';
}

export const config = {
  apiBaseUrl:
    process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || fallbackApiBaseUrl,
  developmentPreviewEnabled: isDevelopmentPreviewEnabled(
    __DEV__,
    process.env.EXPO_PUBLIC_ENABLE_MOCK_DATA,
  ),
} as const;
