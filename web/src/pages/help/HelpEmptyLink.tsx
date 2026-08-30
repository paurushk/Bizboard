import type { ReactNode } from 'react';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';

/** Empty-state deep link. Hidden when helpV2 is off. */
export function HelpEmptyLink({
  intent,
  children,
}: {
  intent: string;
  children?: ReactNode;
}) {
  useFeatureFlagEpoch();
  const link = isHelpV2Enabled() ? (
    <Link
      component={RouterLink}
      to={`/help?intent=${encodeURIComponent(intent)}&source=empty`}
      variant="body2"
    >
      {t('help.emptyLink')}
    </Link>
  ) : null;
  if (!children && !link) return null;
  return (
    <Stack spacing={1} alignItems="center">
      {children}
      {link}
    </Stack>
  );
}
