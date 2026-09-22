import React from 'react';
import { StyleSheet } from 'react-native';

jest.mock('@/features/language/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string) => key,
    language: 'en',
    setLanguage: jest.fn(),
  }),
}));

jest.mock('expo-router', () => {
  const React = require('react');
  return {
    Tabs: Object.assign(() => null, {
      Screen: () => null,
    }),
    useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
    useLocalSearchParams: () => ({}),
  };
});

jest.mock('expo-symbols', () => {
  const React = require('react');
  return {
    SymbolView: () => null,
  };
});

import TabLayout from '@/app/(tabs)/_layout';
import { lightColors, setActiveAppearance } from '@/theme/tokens';

describe('Navigation Regression', () => {
  afterEach(() => setActiveAppearance('dark'));

  it('renders exactly four canonical bottom tabs without profile', () => {
    const layout = TabLayout();
    const screens = layout.props.children;

    expect(screens).toBeDefined();

    const screenProps = Array.isArray(screens)
      ? screens.map((s: any) => s.props)
      : [screens.props];

    // Ensure exactly 4 tabs are rendered
    expect(screenProps.length).toBe(4);

    const names = screenProps.map((p: any) => p.name);
    expect(names).toContain('today');
    expect(names).toContain('explore');
    expect(names).toContain('ai');
    expect(names).toContain('bets');
    expect(names).not.toContain('profile'); // Fail if profile is accidentally re-added to bottom tabs
    const pve = screenProps.find((screen: any) => screen.name === 'ai');
    expect(pve.options.title).toBe('PvE');
  });

  it('keeps the old selected-tab structure with only the Light interaction color changed', () => {
    setActiveAppearance('light');
    const layout = TabLayout();
    const screens = layout.props.children;
    const screenProps = Array.isArray(screens)
      ? screens.map((screen: any) => screen.props)
      : [screens.props];
    const pve = screenProps.find((screen: any) => screen.name === 'ai');
    const icon = pve.options.tabBarIcon({ focused: true });
    const renderedIcon = icon.type(icon.props);
    const children = React.Children.toArray(renderedIcon.props.children);
    const [symbol] = children;

    expect(symbol).toBeTruthy();
    expect(
      StyleSheet.flatten(renderedIcon.props.style).backgroundColor,
    ).toBeUndefined();
    expect(children).toHaveLength(1);
    expect((symbol as any).props.tintColor).toBe(
      lightColors.interactiveTextAccent,
    );
    expect(layout.props.screenOptions.tabBarActiveTintColor).toBe(
      lightColors.interactiveTextAccent,
    );
    expect(layout.props.screenOptions.tabBarInactiveTintColor).toBe(
      lightColors.textSecondary,
    );
  });
});
