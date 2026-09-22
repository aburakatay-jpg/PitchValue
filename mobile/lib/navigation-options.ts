import type { ThemeColors } from '@/theme/tokens';

export function createNativeHeaderOptions(
  colors: Pick<ThemeColors, 'background' | 'headerBackground' | 'textPrimary'>,
) {
  return {
    contentStyle: { backgroundColor: colors.background },
    headerStyle: { backgroundColor: colors.headerBackground },
    headerTintColor: colors.textPrimary,
  };
}

export const signInScreenOptions = {
  title: '',
  headerBackTitle: '',
  headerBackButtonDisplayMode: 'minimal' as const,
};

export const registrationScreenOptions = signInScreenOptions;
