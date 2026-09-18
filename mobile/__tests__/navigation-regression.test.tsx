import React from 'react';

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

describe('Navigation Regression', () => {
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
  });
});
