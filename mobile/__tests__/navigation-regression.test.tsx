import React from 'react';
import { Image, StyleSheet } from 'react-native';

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
import { darkColors, lightColors, setActiveAppearance } from '@/theme/tokens';

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
    expect(names).toEqual(['today', 'explore', 'ai', 'bets']);
    const pve = screenProps.find((screen: any) => screen.name === 'ai');
    expect(pve.options.title).toBe('PvE');
  });

  it.each([
    ['light', lightColors],
    ['dark', darkColors],
  ] as const)(
    'uses the approved PvE image and semantic %s tab tints',
    (appearance, palette) => {
      setActiveAppearance(appearance);
      const layout = TabLayout();
      const screens = layout.props.children;
      const screenProps = Array.isArray(screens)
        ? screens.map((screen: any) => screen.props)
        : [screens.props];
      const pve = screenProps.find((screen: any) => screen.name === 'ai');
      for (const focused of [true, false]) {
        const icon = pve.options.tabBarIcon({ focused });
        const renderedIcon = icon.type(icon.props);
        const children = React.Children.toArray(renderedIcon.props.children);
        const [image] = children;
        expect(children).toHaveLength(1);
        expect((image as any).type).toBe(Image);
        expect((image as any).props.source).toBe(
          require('../assets/icons/pve-icon.png'),
        );
        expect((image as any).props.accessible).toBe(false);
        expect(StyleSheet.flatten((image as any).props.style).tintColor).toBe(
          focused ? palette.interactiveTextAccent : palette.textSecondary,
        );
        expect(StyleSheet.flatten(renderedIcon.props.style)).toMatchObject({
          height: 32,
        });
        expect(
          StyleSheet.flatten(renderedIcon.props.style).backgroundColor,
        ).toBeUndefined();
      }
      expect(layout.props.screenOptions.tabBarActiveTintColor).toBe(
        palette.interactiveTextAccent,
      );
      expect(layout.props.screenOptions.tabBarInactiveTintColor).toBe(
        palette.textSecondary,
      );
    },
  );

  it('keeps the Today, Explore, and My Bets symbol definitions', () => {
    const screens = TabLayout().props.children;
    const screenProps = Array.isArray(screens)
      ? screens.map((screen: any) => screen.props)
      : [screens.props];
    const expected = [
      ['today', 'calendar'],
      ['explore', 'magnifyingglass'],
      ['bets', 'list.clipboard'],
    ];
    for (const [route, name] of expected) {
      const screen = screenProps.find((entry: any) => entry.name === route);
      const icon = screen.options.tabBarIcon({ focused: false });
      const container = icon.type(icon.props);
      const [symbol] = React.Children.toArray(container.props.children);
      expect((symbol as any).props.name).toBe(name);
      expect((symbol as any).props.size).toBe(24);
    }
  });
});
