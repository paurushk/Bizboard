import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listUserSessions, revokeUserSession } from '@/api/auth';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t, useLocale } from '@/i18n';

const KEY = ['user-sessions'];

/**
 * WP-ID3: the devices this user is signed in on. Signing one out stops it refreshing its session;
 * an email goes out when a sign-in comes from a device and network not seen for 90 days.
 */
export function SignedInDevicesPanel() {
  useLocale();
  const qc = useQueryClient();
  const sessions = useQuery({ queryKey: KEY, queryFn: listUserSessions });
  const revoke = useMutation({
    mutationFn: revokeUserSession,
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
  const rows = sessions.data ?? [];
  return (
    <Paper sx={{ p: 2 }}>
      <Stack spacing={1}>
        <Typography variant="h6">{t('signedInDevices.title')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('signedInDevices.help')}
        </Typography>
        {sessions.isError ? <HelpErrorAlert error={sessions.error} /> : null}
        {revoke.isError ? <HelpErrorAlert error={revoke.error} /> : null}
        {sessions.isSuccess && rows.length === 0 ? (
          <Typography color="text.secondary">{t('signedInDevices.none')}</Typography>
        ) : null}
        {rows.map((row) => (
          <Stack key={row.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body2">
              {t('signedInDevices.line', {
                device: row.device,
                network: row.network || t('signedInDevices.unknownNetwork'),
                lastUsed: new Date(row.lastUsedAt).toLocaleString(),
              })}
            </Typography>
            {row.current ? (
              <Chip size="small" label={t('signedInDevices.thisDevice')} />
            ) : (
              <Button
                size="small"
                disabled={revoke.isPending}
                aria-label={t('signedInDevices.signOutLabel', { device: row.device })}
                onClick={() => revoke.mutate(row.id)}
              >
                {t('signedInDevices.signOut')}
              </Button>
            )}
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
