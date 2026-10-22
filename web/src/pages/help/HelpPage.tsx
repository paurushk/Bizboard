import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import { Link as RouterLink } from 'react-router-dom';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';
import { t } from '@/i18n';
import { HelpPageV0 } from './HelpPageV0';
import { HelpPageV2 } from './HelpPageV2';

export function HelpPage() {
  useFeatureFlagEpoch();
  return (
    <>
      {/* WP-PO3: a person to ask, on every plan, whichever help version is on. */}
      <Box sx={{ px: { xs: 2, sm: 3 }, pt: 2 }}>
        <Button component={RouterLink} to="/help/contact" variant="outlined" size="small">
          {t('platformSupport.link')}
        </Button>
      </Box>
      {isHelpV2Enabled() ? <HelpPageV2 /> : <HelpPageV0 />}
    </>
  );
}
