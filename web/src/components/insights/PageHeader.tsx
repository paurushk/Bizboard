import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';
import { PageTitle } from '@/contextHelp';

export function PageHeader({
  title,
  subtitle,
  actions,
  controls,
  helpPage,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  controls?: ReactNode;
  /** Catalog id; omit to resolve from the current route. */
  helpPage?: string;
}) {
  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      justifyContent="space-between"
      alignItems={{ xs: 'stretch', sm: 'center' }}
      spacing={1.5}
      flexWrap="wrap"
      useFlexGap
    >
      <Stack spacing={0.25}>
        <PageTitle page={helpPage}>{title}</PageTitle>
        {subtitle ? (
          <Typography variant="body2" color="text.secondary">
            {subtitle}
          </Typography>
        ) : null}
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        {controls}
        {actions}
      </Stack>
    </Stack>
  );
}
