const fallbackApiBaseUrl = 'http://localhost:8000';

export const config = {
  apiBaseUrl:
    process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || fallbackApiBaseUrl,
} as const;
