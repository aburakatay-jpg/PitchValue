import {
  StyleSheet,
  type ImageStyle,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

export type ResolvedAppearance = 'dark' | 'light';

export type ThemeColors = Readonly<{
  background: string;
  surface: string;
  surfaceElevated: string;
  border: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  brandPrimary: string;
  brandSecondary: string;
  accent: string;
  positive: string;
  warning: string;
  negative: string;
  inputBackground: string;
  tabBarBackground: string;
  headerBackground: string;
  overlay: string;
  onBrand: string;
  controlSelected: string;
  controlSelectedText: string;
  controlSelectedAccent: string;
  segmentedSelectedBackground: string;
  segmentedSelectedText: string;
  appearanceSelectedBackground: string;
  appearanceSelectedText: string;
  authPrimaryBackground: string;
  authPrimaryText: string;
  interactiveTextAccent: string;
  transparent: string;
  // Compatibility aliases keep existing semantic call sites focused.
  primary: string;
  secondary: string;
  surfaceRaised: string;
  text: string;
}>;

export const darkColors: ThemeColors = {
  background: '#08111F',
  surface: '#111D2E',
  surfaceElevated: '#17263A',
  border: '#25364C',
  textPrimary: '#F4F7FB',
  textSecondary: '#95A5BA',
  textMuted: '#74869C',
  brandPrimary: '#4169E1',
  brandSecondary: '#7696F5',
  accent: '#F2B84B',
  positive: '#2DBE8C',
  warning: '#E8A83E',
  negative: '#DE6170',
  inputBackground: '#08111F',
  tabBarBackground: '#111D2E',
  headerBackground: '#111D2E',
  overlay: 'rgba(0, 0, 0, 0.62)',
  onBrand: '#F4F7FB',
  controlSelected: '#4169E1',
  controlSelectedText: '#F4F7FB',
  controlSelectedAccent: 'rgba(65, 105, 225, 1)',
  segmentedSelectedBackground: 'rgba(65, 105, 225, 1)',
  segmentedSelectedText: '#F4F7FB',
  appearanceSelectedBackground: 'rgba(65, 105, 225, 1)',
  appearanceSelectedText: '#F4F7FB',
  authPrimaryBackground: 'rgba(65, 105, 225, 1)',
  authPrimaryText: '#F4F7FB',
  // Kept visually equivalent to the established Dark Mode secondary blue,
  // but unique so the Light Mode semantic mapping remains unambiguous.
  interactiveTextAccent: 'rgba(118, 150, 245, 1)',
  transparent: 'transparent',
  primary: '#4169E1',
  secondary: '#7696F5',
  surfaceRaised: '#17263A',
  text: '#F4F7FB',
};

export const lightColors: ThemeColors = {
  background: '#F3F6FA',
  surface: '#FFFFFF',
  surfaceElevated: '#E8EEF6',
  border: '#C7D2E0',
  textPrimary: '#0B1728',
  textSecondary: '#506279',
  textMuted: '#6B7D91',
  brandPrimary: '#4169E1',
  brandSecondary: '#3158C9',
  accent: '#966300',
  positive: '#087A59',
  warning: '#966000',
  negative: '#B4233D',
  inputBackground: '#FFFFFF',
  tabBarBackground: '#FFFFFF',
  headerBackground: '#FFFFFF',
  overlay: 'rgba(8, 17, 31, 0.42)',
  onBrand: '#FFFFFF',
  controlSelected: '#E1E8F1',
  controlSelectedText: '#0B1728',
  controlSelectedAccent: '#F2B84B',
  segmentedSelectedBackground: '#F2B84B',
  segmentedSelectedText: '#0B1728',
  appearanceSelectedBackground: '#F2B84B',
  appearanceSelectedText: '#0B1728',
  authPrimaryBackground: '#F2B84B',
  authPrimaryText: '#0B1728',
  // Accessible amber foreground for interactive text on the Light surface.
  // #966300 has a 4.75:1 contrast ratio against #F3F6FA.
  interactiveTextAccent: '#966300',
  transparent: 'transparent',
  primary: '#4169E1',
  secondary: '#3158C9',
  surfaceRaised: '#E8EEF6',
  text: '#0B1728',
};

const palettes: Readonly<Record<ResolvedAppearance, ThemeColors>> = {
  dark: darkColors,
  light: lightColors,
};

let activeAppearance: ResolvedAppearance = 'dark';

export function setActiveAppearance(appearance: ResolvedAppearance) {
  activeAppearance = appearance;
}

export function getThemeColors(appearance: ResolvedAppearance) {
  return palettes[appearance];
}

export const colors = new Proxy(darkColors, {
  get(_target, property: keyof ThemeColors) {
    return palettes[activeAppearance][property];
  },
}) as ThemeColors;

type NamedStyle = ViewStyle | TextStyle | ImageStyle;
type NamedStyles = Record<string, NamedStyle>;

const darkToLight = new Map<string, string>(
  Object.keys(darkColors).map((key) => [
    darkColors[key as keyof ThemeColors],
    lightColors[key as keyof ThemeColors],
  ]),
);

function lightStyleValue(value: unknown): unknown {
  if (typeof value === 'string') return darkToLight.get(value) ?? value;
  if (Array.isArray(value)) return value.map(lightStyleValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [
        key,
        lightStyleValue(nested),
      ]),
    );
  }
  return value;
}

export function createThemedStyleSheet<T extends NamedStyles>(styles: T): T {
  const dark = StyleSheet.create(styles) as T;
  const light = StyleSheet.create(lightStyleValue(styles) as T) as T;
  return new Proxy(dark, {
    get(_target, property: string) {
      return (activeAppearance === 'light' ? light : dark)[property];
    },
  });
}

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radii = { sm: 8, md: 14, lg: 20, pill: 999 } as const;
export const typeScale = {
  caption: 13,
  body: 16,
  title: 22,
  hero: 32,
} as const;
export const typography = {
  pageTitle: { fontSize: typeScale.hero, lineHeight: 38, fontWeight: '800' },
  sectionTitle: {
    fontSize: typeScale.title,
    lineHeight: 28,
    fontWeight: '700',
  },
  teamName: { fontSize: 18, lineHeight: 24, fontWeight: '700' },
  competition: {
    fontSize: typeScale.caption,
    lineHeight: 18,
    fontWeight: '600',
  },
  featured: { fontSize: typeScale.title, lineHeight: 28, fontWeight: '800' },
  metric: { fontSize: 18, lineHeight: 24, fontWeight: '800' },
  body: { fontSize: typeScale.body, lineHeight: 24, fontWeight: '400' },
  metadata: { fontSize: 14, lineHeight: 20, fontWeight: '400' },
  caption: { fontSize: typeScale.caption, lineHeight: 18, fontWeight: '600' },
} as const;
export const touchTarget = 48;

export const theme = {
  colors,
  spacing,
  radii,
  typeScale,
  typography,
  touchTarget,
} as const;
export type Theme = typeof theme;
