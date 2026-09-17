import mockAsyncStorage from '@react-native-async-storage/async-storage/jest/async-storage-mock';

jest.mock('@react-native-async-storage/async-storage', () => mockAsyncStorage);

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue(null),
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useLocalSearchParams: () => ({}),
  Link: 'Link',
  Tabs: Object.assign(() => null, { Screen: () => null }),
  Stack: Object.assign(() => null, { Screen: () => null }),
}));

jest.mock('@testing-library/react-native', () => {
  const actual = jest.requireActual('@testing-library/react-native');
  const React = require('react');
  const { LanguageProvider } = jest.requireActual(
    '@/features/language/LanguageContext',
  );
  return {
    ...actual,
    render: (ui: any, options: any) => {
      return actual.render(ui, {
        wrapper: ({ children }: any) =>
          React.createElement(LanguageProvider, null, children),
        ...options,
      });
    },
  };
});
