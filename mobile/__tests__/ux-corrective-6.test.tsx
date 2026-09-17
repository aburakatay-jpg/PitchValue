import { render, waitFor, fireEvent } from '@testing-library/react-native';
import React from 'react';

import { AiView } from '@/components/Assistant';
import { MyBetsView } from '@/components/MyBets';
import {
  LanguageProvider,
  useLanguage,
} from '@/features/language/LanguageContext';
import { EntitlementProvider } from '@/features/entitlement/EntitlementContext';

function TrWrapper({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <ForceTr />
      <EntitlementProvider>{children}</EntitlementProvider>
    </LanguageProvider>
  );
}

function ForceTr() {
  const { setLanguage } = useLanguage();
  React.useEffect(() => {
    setLanguage('tr');
  }, [setLanguage]);
  return null;
}

const baseAiProps = {
  availability: {
    couponBuilderEndpoint: 'SUPPORTED',
    publicPredictionPool: 'SUPPORTED',
  } as const,
  onPick: jest.fn(),
  onExplanation: jest.fn(),
  onAsk: jest.fn(),
  onCoupon: jest.fn(),
  isPremium: false,
  data: null,
  error: null,
  initialLoading: false,
  refreshing: false,
  onRefresh: jest.fn(),
  onOpenPremium: jest.fn(),
  onOpenMatch: jest.fn(),
  premiumAccess: {
    isPremium: false,
    entitlement: null,
  } as any,
};

describe('UX Corrective 6 - Turkish Runtime Fix', () => {
  describe('AI Tab', () => {
    it('renders Turkish copy and rejects English fallbacks', async () => {
      const view = await render(
        <TrWrapper>
          <AiView {...baseAiProps} />
        </TrWrapper>,
      );

      await waitFor(() => {
        expect(view.getByText('Günün En İyi Değeri')).toBeTruthy();
      });

      expect(view.getByText('Kupon Oluşturucu')).toBeTruthy();
      expect(view.getByText('Analizi Açıkla')).toBeTruthy();
      expect(view.getByText("PitchValue'a Sor")).toBeTruthy();
      expect(
        view.getByText(
          'Uygun yayınlanmış analizleri 1-4 seçim halinde düzenleyin.',
        ),
      ).toBeTruthy();

      expect(view.queryByText('Today’s Best Value')).toBeNull();
      expect(view.queryByText('Explain a Pick')).toBeNull();
      expect(view.queryByText('Ask PitchValue')).toBeNull();
      expect(view.queryByText('Coupon Builder')).toBeNull();

      fireEvent.press(
        view.getByRole('button', { name: 'Günün En İyi Değeri' }),
      );
      await waitFor(() => {
        expect(
          view.getByText('Şu anda uygun değer sinyali bulunmuyor'),
        ).toBeTruthy();
        expect(
          view.queryByText('No eligible value signals available right now'),
        ).toBeNull();
      });

      fireEvent.press(view.getByRole('button', { name: 'Kupon Oluşturucu' }));
      await waitFor(() => {
        expect(view.getByText('Temkinli')).toBeTruthy();
        expect(view.getByText('Dengeli')).toBeTruthy();
        expect(view.getByText('Cesur')).toBeTruthy();
        expect(view.queryByText('Safe')).toBeNull();
        expect(view.queryByText('Balanced')).toBeNull();
        expect(view.queryByText('Bold')).toBeNull();
      });
    });
  });

  describe('My Bets Tab', () => {
    it('renders Turkish copy and rejects English fallbacks', async () => {
      const view = await render(
        <TrWrapper>
          <MyBetsView accessToken={null} />
        </TrWrapper>,
      );

      await waitFor(() => {
        expect(view.getByText('Aktif')).toBeTruthy();
      });

      expect(view.getByText('Geçmiş')).toBeTruthy();
      expect(view.getByText('Performans')).toBeTruthy();

      expect(view.queryByText('My Bets')).toBeNull();
      expect(view.queryByText('History')).toBeNull();
      expect(view.queryByText('Performance')).toBeNull();

      expect(
        view.getByText('Takip edilen seçimler kullanılamıyor'),
      ).toBeTruthy();
      expect(view.queryByText('Tracked selections unavailable')).toBeNull();

      fireEvent.press(view.getByRole('tab', { name: 'Geçmiş' }));
      await waitFor(() => {
        expect(view.getByText('Geçmiş kullanılamıyor')).toBeTruthy();
        expect(view.queryByText('History unavailable')).toBeNull();
      });

      fireEvent.press(view.getByRole('tab', { name: 'Performans' }));
      await waitFor(() => {
        expect(view.getByText('Performans kullanılamıyor')).toBeTruthy();
        expect(view.queryByText('Performance unavailable')).toBeNull();
      });
    });
  });
});
