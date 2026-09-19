import { useRouter } from 'expo-router';

import { EmailAuthShell } from '@/components/AuthShell';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { confirmEmailVerification } from '@/lib/product-api';

export default function EmailAuthScreen() {
  const router = useRouter();
  const session = useProductSession();

  const handleSignIn = async (email: string, password: string) => {
    await session.signInEmail(email, password);
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/today');
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
    <EmailAuthShell
      onSignIn={handleSignIn}
      onSignUp={handleSignUp}
      onVerify={handleVerify}
    />
  );
}
