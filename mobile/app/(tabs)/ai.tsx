import { AiView } from '@/components/Assistant';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { usePublicResource } from '@/hooks/use-public-resource';
import { hasPremiumAccess } from '@/lib/entitlement';
import { getExplorePredictions } from '@/lib/public-api';

export function AiScreen() {
  const entitlement = useEntitlement();
  const resource = usePublicResource(getExplorePredictions);
  return (
    <AiView
      {...resource}
      onOpenPremium={entitlement.openPaywall}
      onRefresh={() => void resource.refresh()}
      premiumAccess={hasPremiumAccess(entitlement.state)}
    />
  );
}

export default AiScreen;
