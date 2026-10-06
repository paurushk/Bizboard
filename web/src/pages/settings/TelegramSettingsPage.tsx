import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getTelegramStatus, requestTelegramLink, unlinkTelegram } from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

export function TelegramSettingsPage() {
  const qc = useQueryClient();
  const [deepLink, setDeepLink] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['telegram-status'],
    queryFn: getTelegramStatus,
    // Poll while a link is pending so the page picks up the /start handshake
    // without the user needing to refresh.
    refetchInterval: (q) => (deepLink && !q.state.data?.linked ? 3000 : false),
  });

  const linkMutation = useMutation({
    mutationFn: requestTelegramLink,
    onSuccess: (result) => {
      setDeepLink(result.deepLink);
      window.open(result.deepLink, '_blank', 'noopener,noreferrer');
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: unlinkTelegram,
    onSuccess: () => {
      setDeepLink(null);
      void qc.invalidateQueries({ queryKey: ['telegram-status'] });
    },
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const status = query.data;
  const linked = !!status?.linked;

  return (
    <Stack spacing={2} sx={{ maxWidth: 640 }}>
      <PageTitle>{t('nav.telegram')}</PageTitle>
      <Typography color="text.secondary">{t('integrations.telegramIntro')}</Typography>

      {!status?.enabled ? (
        <Alert severity="warning">{t('integrations.telegramClosed')}</Alert>
      ) : null}

      {linkMutation.isError ? <HelpErrorAlert error={linkMutation.error} /> : null}
      {unlinkMutation.isError ? <HelpErrorAlert error={unlinkMutation.error} /> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="subtitle1">{t('integrations.telegramStatus')}</Typography>
            <Chip
              size="small"
              label={linked ? t('integrations.telegramConnected') : t('integrations.telegramNotConnected')}
              color={linked ? 'success' : 'default'}
            />
          </Stack>

          {linked ? (
            <Button
              variant="outlined"
              color="error"
              disabled={unlinkMutation.isPending}
              onClick={() => unlinkMutation.mutate()}
              sx={{ alignSelf: 'flex-start' }}
            >
              {t('integrations.telegramDisconnect')}
            </Button>
          ) : (
            <Stack spacing={1} alignItems="flex-start">
              <Button
                variant="contained"
                disabled={!status?.enabled || linkMutation.isPending}
                onClick={() => linkMutation.mutate()}
              >
                {t('integrations.telegramConnect')}
              </Button>
              {deepLink ? (
                <Typography variant="body2" color="text.secondary">
                  {t('integrations.telegramOpened')}{' '}
                  <a href={deepLink} target="_blank" rel="noopener noreferrer">
                    {t('integrations.telegramOpenAgain')}
                  </a>
                </Typography>
              ) : null}
            </Stack>
          )}
        </Stack>
      </Paper>
    </Stack>
  );
}
