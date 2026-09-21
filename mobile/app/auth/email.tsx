import { Alert } from 'react-native';
import { useRouter } from 'expo-router';

import { CreateAccountShell } from '@/components/AuthShell';
import { useLanguage } from '@/features/language/LanguageContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { confirmEmailVerification } from '@/lib/product-api';

export default function EmailAuthScreen() {
  const router = useRouter();
  const session = useProductSession();
  const { t } = useLanguage();

  const returnToSignIn = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/auth');
  };

  const handleSignUp = async (
    email: string,
    password: string,
    countryCode: string,
    ageAcknowledged: boolean,
  ) => {
    return session.signUpEmail(email, password, countryCode, ageAcknowledged);
  };

  const handleVerify = async (token: string) => {
    await confirmEmailVerification(token, new AbortController().signal);
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/today');
  };

  return (
    <CreateAccountShell
      onOpenPrivacy={() =>
        Alert.alert(
          t('Privacy Policy'),
          t('Final legal content is not yet available.'),
        )
      }
      onOpenTerms={() =>
        Alert.alert(
          t('Terms of Use'),
          t('Final legal content is not yet available.'),
        )
      }
      onSignIn={returnToSignIn}
      onSignUp={handleSignUp}
      onVerify={handleVerify}
    />
  );
}
