import { createNativeHeaderOptions } from '@/lib/navigation-options';
import { darkColors, lightColors } from '@/theme/tokens';

describe('native header theme options', () => {
  it('uses the resolved Light palette directly for native header presentation', () => {
    expect(createNativeHeaderOptions(lightColors)).toEqual({
      contentStyle: { backgroundColor: lightColors.background },
      headerStyle: { backgroundColor: lightColors.headerBackground },
      headerTintColor: lightColors.textPrimary,
    });
  });

  it('uses the resolved Dark palette directly without relying on global tokens', () => {
    expect(createNativeHeaderOptions(darkColors)).toEqual({
      contentStyle: { backgroundColor: darkColors.background },
      headerStyle: { backgroundColor: darkColors.headerBackground },
      headerTintColor: darkColors.textPrimary,
    });
  });
});
