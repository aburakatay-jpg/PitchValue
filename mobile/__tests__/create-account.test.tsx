import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import AsyncStorage from '@react-native-async-storage/async-storage';

import { CreateAccountShell } from '@/components/AuthShell';
import {
  registrationCountries,
  type RegistrationCountry,
} from '@/components/CountrySelector';
import { registrationScreenOptions } from '@/lib/navigation-options';
import { ProductServiceError } from '@/lib/product-api';

const countryValues = ['GB', 'DE', 'FR', 'ES', 'PT', 'NL', 'IT', 'TR', 'OTHER'];
const countryLabels = [
  'United Kingdom',
  'Germany',
  'France',
  'Spain',
  'Portugal',
  'Netherlands',
  'Italy',
  'Türkiye',
  'Other',
];

async function renderRegistration(
  overrides: Partial<React.ComponentProps<typeof CreateAccountShell>> = {},
) {
  return render(
    <CreateAccountShell
      onSignIn={jest.fn()}
      onSignUp={jest.fn().mockResolvedValue({ deliveryState: 'SENT' })}
      {...overrides}
    />,
  );
}

async function completeRequiredForm(
  view: Awaited<ReturnType<typeof renderRegistration>>,
  country: RegistrationCountry = registrationCountries[0]!,
) {
  await fireEvent.changeText(view.getByLabelText('Email'), 'user@example.com');
  await fireEvent.changeText(
    view.getByLabelText('Password'),
    'SecurePassword1!',
  );
  await fireEvent.press(view.getByTestId('country-selector'));
  await fireEvent.press(view.getByTestId(`country-option-${country.value}`));
  await fireEvent.press(view.getByTestId('age-acknowledgement'));
  await fireEvent.press(view.getByTestId('terms-acknowledgement'));
  await fireEvent.press(view.getByTestId('risk-acknowledgement'));
}

describe('Create Account experience', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  afterEach(async () => {
    await AsyncStorage.clear();
  });

  it('is a dedicated registration screen without auth-mode tabs or confirmation password', async () => {
    const view = await renderRegistration();
    expect(await view.findByText('Create your account')).toBeTruthy();
    expect(view.getByLabelText('Email')).toBeTruthy();
    expect(view.getByLabelText('Password')).toBeTruthy();
    expect(view.queryByText('Confirm Password')).toBeNull();
    expect(view.queryByText('Country Code (2 letters)')).toBeNull();
    expect(view.queryByText('Sign Up')).toBeNull();
    expect(view.queryByText('Premium')).toBeNull();
    expect(view.queryByText(/trial/i)).toBeNull();
    expect(registrationScreenOptions).toEqual({
      title: '',
      headerBackTitle: '',
      headerBackButtonDisplayMode: 'minimal',
    });
  });

  it('uses mobile field semantics and the same inline eye control as Sign In', async () => {
    const view = await renderRegistration();
    const email = view.getByLabelText('Email');
    const password = view.getByLabelText('Password');
    expect(email).toHaveProp('keyboardType', 'email-address');
    expect(email).toHaveProp('autoCapitalize', 'none');
    expect(email).toHaveProp('returnKeyType', 'next');
    expect(password).toHaveProp('autoComplete', 'new-password');
    expect(password).toHaveProp('secureTextEntry', true);
    expect(view.queryByText('Show password')).toBeNull();
    await fireEvent.press(view.getByLabelText('Show password'));
    expect(password).toHaveProp('secureTextEntry', false);
    expect(view.getByLabelText('Hide password')).toBeTruthy();
  });

  it('offers all nine countries in exact product order without showing ISO codes', async () => {
    expect(registrationCountries.map(({ value }) => value)).toEqual(
      countryValues,
    );
    expect(registrationCountries.map(({ label }) => label)).toEqual(
      countryLabels,
    );
    const view = await renderRegistration();
    expect(view.getByText('Country / Region')).toBeTruthy();
    await fireEvent.press(view.getByTestId('country-selector'));
    const tree = JSON.stringify(view.toJSON());
    let previousPosition = -1;
    for (const [index, value] of countryValues.entries()) {
      const option = view.getByTestId(`country-option-${value}`);
      expect(option).toBeTruthy();
      const position = tree.indexOf(`country-option-${value}`);
      expect(position).toBeGreaterThan(previousPosition);
      previousPosition = position;
      expect(countryLabels[index]).toBeDefined();
    }
  });

  it('keeps required acknowledgements unchecked and Privacy informational only', async () => {
    const view = await renderRegistration();
    for (const label of [
      'I am 18 years of age or older.',
      'I accept the Terms of Use.',
      'I understand that betting involves a risk of financial loss.',
    ]) {
      expect(view.getByRole('checkbox', { name: label })).toHaveProp(
        'accessibilityState',
        { checked: false },
      );
    }
    expect(view.getByRole('link', { name: 'Privacy Policy' })).toBeTruthy();
    expect(view.queryByRole('checkbox', { name: /Privacy Policy/ })).toBeNull();
  });

  it('uses wrapping legal rows without fixed-height clipping', async () => {
    const view = await renderRegistration();
    for (const testID of [
      'age-acknowledgement',
      'terms-acknowledgement',
      'risk-acknowledgement',
    ]) {
      const style = StyleSheet.flatten(view.getByTestId(testID).props.style);
      expect(style.minHeight).toBeGreaterThanOrEqual(44);
      expect(style.height).toBeUndefined();
    }
  });

  it('enables Create Account only after valid fields and all required acknowledgements', async () => {
    const onSignUp = jest.fn().mockResolvedValue({ deliveryState: 'SENT' });
    const view = await renderRegistration({ onSignUp });
    const cta = view.getByTestId('create-account-primary');
    expect(cta).toBeDisabled();
    await completeRequiredForm(view);
    expect(cta).toBeEnabled();
    await fireEvent.press(cta);
    expect(onSignUp).toHaveBeenCalledWith(
      'user@example.com',
      'SecurePassword1!',
      'GB',
      true,
    );
  });

  it('does not invent an unsupported backend country code for Other', async () => {
    const onSignUp = jest.fn();
    const view = await renderRegistration({ onSignUp });
    await completeRequiredForm(view, registrationCountries[8]);
    expect(view.getByTestId('create-account-primary')).toBeDisabled();
    expect(
      view.getByText('Registration for other regions is not available yet.'),
    ).toBeTruthy();
    expect(onSignUp).not.toHaveBeenCalled();
  });

  it('keeps Sign In as a text link and sanitizes registration failures', async () => {
    const onSignIn = jest.fn();
    const view = await renderRegistration({
      onSignIn,
      onSignUp: jest
        .fn()
        .mockRejectedValue(new ProductServiceError('CONFLICT')),
    });
    await fireEvent.press(view.getByRole('link', { name: 'Sign In' }));
    expect(onSignIn).toHaveBeenCalledTimes(1);
    await completeRequiredForm(view);
    await fireEvent.press(view.getByTestId('create-account-primary'));
    expect(
      await view.findByText('An account already exists for this email.'),
    ).toBeTruthy();
  });

  it('renders the complete registration experience in Turkish', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await renderRegistration();
    for (const label of [
      'Hesabınızı oluşturun',
      'E-posta',
      'Şifre',
      'Ülke / Bölge',
      '18 yaş veya üzerindeyim.',
      'Bahis faaliyetlerinin finansal kayıp riski taşıdığını anlıyorum.',
      'Hesap Oluştur',
      'Zaten hesabınız var mı?',
      'Giriş Yap',
    ]) {
      expect(await view.findByText(label)).toBeTruthy();
    }
    expect(
      view.getByRole('checkbox', {
        name: "Kullanım Koşulları'nı kabul ediyorum.",
      }),
    ).toBeTruthy();
    await fireEvent.press(view.getByTestId('country-selector'));
    const turkishCountries = [
      'Birleşik Krallık',
      'Almanya',
      'Fransa',
      'İspanya',
      'Portekiz',
      'Hollanda',
      'İtalya',
      'Türkiye',
      'Diğer',
    ];
    for (const [index, label] of turkishCountries.entries()) {
      expect(
        view.getByTestId(`country-option-${countryValues[index]}`).props
          .accessibilityLabel,
      ).toContain(label);
    }
  });
});
