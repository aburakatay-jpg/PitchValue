export const colors = {
  primary: '#4169E1',
  secondary: '#7696F5',
  accent: '#F2B84B',
  background: '#08111F',
  surface: '#111D2E',
  surfaceRaised: '#17263A',
  positive: '#2DBE8C',
  warning: '#E8A83E',
  negative: '#DE6170',
  text: '#F4F7FB',
  textSecondary: '#95A5BA',
  border: '#25364C',
  transparent: 'transparent',
} as const;

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radii = { sm: 8, md: 14, lg: 20, pill: 999 } as const;
export const typeScale = {
  caption: 13,
  body: 16,
  title: 22,
  hero: 32,
} as const;
export const touchTarget = 48;

export const theme = {
  colors,
  spacing,
  radii,
  typeScale,
  touchTarget,
} as const;
export type Theme = typeof theme;
