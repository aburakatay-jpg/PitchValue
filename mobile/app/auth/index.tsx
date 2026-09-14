import { useRouter, type Href } from 'expo-router';

import { AuthEntry } from '@/components/AuthShell';

export default function AuthEntryScreen() {
  const router = useRouter();
  const continueAsGuest = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/today');
  };
  return (
    <AuthEntry
      onEmail={() => router.push('/auth/email' as Href)}
      onGuest={continueAsGuest}
    />
  );
}
