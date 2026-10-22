import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  grantSupportAccess,
  listSupportAccessGrants,
  revokeSupportAccess,
  type PlatformTicket,
} from '@/api/platformSupport';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

const HOURS = [24, 48, 72];
const KEY = ['support-access-grants'];

/**
 * WP-ID4 (owner): let Bizboard support look at this company's data for one open request —
 * read-only, for at most 72 hours, ended at any time. Lists every page support opened.
 */
export function SupportAccessPanel({ tickets }: { tickets: PlatformTicket[] }) {
  const qc = useQueryClient();
  const grants = useQuery({ queryKey: KEY, queryFn: listSupportAccessGrants });
  const open = tickets.filter((row) => row.status !== 'RESOLVED');
  const [ticketId, setTicketId] = useState<number | ''>('');
  const [hours, setHours] = useState(72);
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const refresh = () => void qc.invalidateQueries({ queryKey: KEY });
  const grant = useMutation({
    mutationFn: () => grantSupportAccess({ ticketId: Number(ticketId), hours, password, code }),
    onSuccess: () => {
      setPassword('');
      setCode('');
      refresh();
    },
  });
  const revoke = useMutation({ mutationFn: revokeSupportAccess, onSuccess: refresh });
  const rows = grants.data ?? [];

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6" component="h2">
          {t('supportAccess.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('supportAccess.help')}
        </Typography>
        {open.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('supportAccess.needRequest')}
          </Typography>
        ) : (
          <Stack spacing={1.5}>
            <TextField
              select
              label={t('supportAccess.request')}
              value={ticketId}
              onChange={(e) => setTicketId(Number(e.target.value))}
            >
              {open.map((row) => (
                <MenuItem key={row.id} value={row.id}>
                  {`#${row.id} ${row.subject}`}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('supportAccess.howLong')}
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              {HOURS.map((h) => (
                <MenuItem key={h} value={h}>
                  {t('supportAccess.hours', { hours: String(h) })}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              type="password"
              label={t('supportAccess.password')}
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
            />
            <TextField label={t('supportAccess.code')} value={code} onChange={(e) => setCode(e.target.value)} />
            {grant.isError ? <HelpErrorAlert error={grant.error} /> : null}
            <Button
              variant="contained"
              sx={{ alignSelf: 'flex-start' }}
              disabled={!ticketId || !password || grant.isPending}
              onClick={() => grant.mutate()}
            >
              {t('supportAccess.allow')}
            </Button>
          </Stack>
        )}
        {revoke.isError ? <HelpErrorAlert error={revoke.error} /> : null}
        {rows.map((row) => (
          <Stack key={row.id} spacing={0.5}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="body2">
                {t(row.live ? 'supportAccess.liveLine' : 'supportAccess.endedLine', {
                  id: String(row.ticketId),
                  until: new Date(row.expiresAt).toLocaleString(),
                })}
              </Typography>
              {row.live ? (
                <Button size="small" color="error" disabled={revoke.isPending} onClick={() => revoke.mutate(row.id)}>
                  {t('supportAccess.end')}
                </Button>
              ) : null}
            </Stack>
            {row.views.map((v) => (
              <Typography key={`${v.at}-${v.section}`} variant="caption" color="text.secondary">
                {t('supportAccess.viewLine', {
                  at: new Date(v.at).toLocaleString(),
                  who: v.staffEmail || t('supportAccess.supportTeam'),
                  section: v.section,
                })}
              </Typography>
            ))}
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}

/** WP-ID4: every member sees, on every screen, while support can view the company's data. */
export function SupportAccessBanner() {
  const grants = useQuery({
    queryKey: KEY,
    queryFn: listSupportAccessGrants,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const live = (Array.isArray(grants.data) ? grants.data : []).find((row) => row.live);
  if (!live) return null;
  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      {t('supportAccess.banner', { until: new Date(live.expiresAt).toLocaleString() })}
    </Alert>
  );
}
