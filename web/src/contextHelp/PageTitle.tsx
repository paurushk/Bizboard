import type { ElementType, ReactNode } from 'react';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme, TypographyProps } from '@mui/material/styles';
import { ContextHelp } from './ContextHelp';

/**
 * Page heading plus the contextual Help (`?`) icon.
 * Pass `page` to pin a catalog id; otherwise the current route is used.
 */
export function PageTitle({
  children,
  page,
  variant = 'h4',
  component = 'h1',
  sx,
}: {
  children: ReactNode;
  page?: string;
  variant?: TypographyProps['variant'];
  component?: ElementType;
  sx?: SxProps<Theme>;
}) {
  return (
    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ minWidth: 0 }}>
      <Typography variant={variant} component={component} sx={sx}>
        {children}
      </Typography>
      <ContextHelp page={page} />
    </Stack>
  );
}
