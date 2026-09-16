import { useRouter } from 'expo-router';

import { EmailAuthShell } from '@/components/AuthShell';
import { useProductSession } from '@/features/session/ProductSessionContext';

export default function EmailAuthScreen() {
  const router = useRouter();
  const session = useProductSession();
  const complete = async (
    action: (email: string, password: string) => Promise<void>,
    email: string,
    password: string,
  ) => {
    await action(email, password);
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/today');
  };
  return (
    <EmailAuthShell
      onSignIn={(email, password) =>
        complete(session.signInEmail, email, password)
      }
      onSignUp={(email, password) =>
        complete(session.signUpEmail, email, password)
      }
    />
  );
}
