import { AiView } from '@/components/Assistant';
import { usePublicResource } from '@/hooks/use-public-resource';
import { getExplorePredictions } from '@/lib/public-api';

export function AiScreen() {
  const resource = usePublicResource(getExplorePredictions);
  return <AiView {...resource} onRefresh={() => void resource.refresh()} />;
}

export default AiScreen;
