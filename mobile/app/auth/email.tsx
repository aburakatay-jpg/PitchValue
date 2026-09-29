import { useRouter } from 'expo-router';
import { useState } from 'react';

import { CreateAccountShell } from '@/components/AuthShell';
import { LegalModal } from '@/components/LegalModal';
import { useProductSession } from '@/features/session/ProductSessionContext';
import {
  confirmEmailVerification,
  resendEmailVerification,
} from '@/lib/product-api';
import type { LegalDocumentId } from '@/legal/content';

export default function EmailAuthScreen() {
  const router = useRouter();
  const session = useProductSession();
  const [legalDocument, setLegalDocument] = useState<LegalDocumentId | null>(
    null,
  );

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
    await session.refreshUser();
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/today');
  };

  const handleResend = async () => {
    if (!session.accessToken) throw new Error('Unauthenticated');
    const result = await resendEmailVerification(
      session.accessToken,
      new AbortController().signal,
    );
    return { deliveryState: result.delivery_state };
  };

  return (
    <>
      <CreateAccountShell
        onOpenAge={() => setLegalDocument('age')}
        onOpenPrivacy={() => setLegalDocument('privacy')}
        onOpenTerms={() => setLegalDocument('terms')}
        onSignIn={returnToSignIn}
        onSignUp={handleSignUp}
        onVerify={handleVerify}
        unverifiedSession={session.state === 'UNVERIFIED'}
        onResend={handleResend}
      />
      <LegalModal
        documentId={legalDocument}
        onClose={() => setLegalDocument(null)}
      />
    </>
  );
}
