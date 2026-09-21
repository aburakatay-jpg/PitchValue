import { useRouter, type Href } from 'expo-router';

import { SignInShell } from '@/components/AuthShell';
import { useProductSession } from '@/features/session/ProductSessionContext';

export default function AuthEntryScreen() {
  const router = useRouter();
  const session = useProductSession();

  const handleSignIn = async (email: string, password: string) => {
    await session.signInEmail(email, password);
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/today');
  };

  return (
    <SignInShell
      onCreateAccount={() => router.push('/auth/email' as Href)}
      onSignIn={handleSignIn}
    />
  );
}
