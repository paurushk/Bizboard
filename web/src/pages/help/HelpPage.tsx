import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';
import { HelpPageV0 } from './HelpPageV0';
import { HelpPageV2 } from './HelpPageV2';

export function HelpPage() {
  useFeatureFlagEpoch();
  if (isHelpV2Enabled()) return <HelpPageV2 />;
  return <HelpPageV0 />;
}
