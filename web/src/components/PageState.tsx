import type { ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

export function LoadingState({ label }: { label?: string }) {
  return (
    <Stack alignItems="center" justifyContent="center" spacing={2} sx={{ py: 8 }}>
      <CircularProgress size={36} />
      <Typography color="text.secondary">{label ?? t('common.loading')}</Typography>
    </Stack>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Box
      sx={{
        py: 6,
        px: 3,
        textAlign: 'center',
        border: '1px dashed',
        borderColor: 'divider',
        borderRadius: 2,
        background:
          'radial-gradient(circle at top, rgba(15,118,110,0.06), transparent 55%)',
      }}
    >
      <Typography variant="h6" gutterBottom>
        {title ?? t('common.empty')}
      </Typography>
      {description ? (
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      ) : null}
      {action}
    </Box>
  );
}

export function ErrorState({
  message,
  onRetry,
  error,
}: {
  message?: string;
  onRetry?: () => void;
  error?: unknown;
}) {
  return (
    <HelpErrorAlert
      message={message ?? t('common.error')}
      error={error}
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        ) : undefined
      }
    />
  );
}
