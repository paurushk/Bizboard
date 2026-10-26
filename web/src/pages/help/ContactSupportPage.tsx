import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  getNpsDue,
  listPlatformTickets,
  NPS_DUE_QUERY_KEY,
  openPlatformTicket,
  sendSatisfaction,
  type SupportSeverity,
} from '@/api/platformSupport';
import { useAuth } from '@/auth/AuthContext';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { SupportAccessPanel } from '@/components/support/SupportAccessPanel';
import { t } from '@/i18n';

const SEVERITIES: SupportSeverity[] = ['P2', 'P1', 'P0', 'P3'];

/**
 * WP-PO3: ask Bizboard for help, and see earlier requests. Open to every member on every plan.
 * The request carries the Support ID, the screen and recent error codes — not what you typed
 * into forms.
 */
export function ContactSupportPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const tickets = useQuery({ queryKey: ['platform-tickets', user?.companyId], queryFn: listPlatformTickets });
  // BB-136: rate a resolved request 1-5 when the company has the survey on.
  const survey = useQuery({ queryKey: NPS_DUE_QUERY_KEY, queryFn: getNpsDue, staleTime: 30 * 60_000, retry: false });
  const rate = useMutation({
    mutationFn: (input: { id: number; score: number }) =>
      sendSatisfaction({ kind: 'CSAT', score: input.score, platformTicket: input.id }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['platform-tickets'] }),
  });
  // WP-GR1a: "Ask support to switch on Tally import" lands here with ?topic=tally-import.
  const [params] = useSearchParams();
  const topic = params.get('topic') === 'tally-import' ? 'tally-import-request' : '';
  const [subject, setSubject] = useState(topic ? t('platformSupport.tallySubject') : '');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState<SupportSeverity>(topic ? 'P3' : 'P2');
  const send = useMutation({
    mutationFn: () => openPlatformTicket({ subject, description, severity, tag: topic }),
    onSuccess: () => {
      setSubject('');
      setDescription('');
      void qc.invalidateQueries({ queryKey: ['platform-tickets'] });
    },
  });

  return (
    <Stack spacing={2} sx={{ p: { xs: 2, sm: 3 }, maxWidth: 720 }}>
      <Typography variant="h5" component="h1">
        {t('platformSupport.title')}
      </Typography>
      <Paper sx={{ p: 3 }}>
        <Stack spacing={1.5}>
          <TextField
            label={t('platformSupport.subject')}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            inputProps={{ maxLength: 200 }}
          />
          <TextField
            label={t('platformSupport.description')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            multiline
            minRows={3}
          />
          <TextField
            select
            label={t('platformSupport.severity')}
            value={severity}
            onChange={(e) => setSeverity(e.target.value as SupportSeverity)}
            sx={{ maxWidth: 360 }}
          >
            {SEVERITIES.map((s) => (
              <MenuItem key={s} value={s}>
                {t(`platformSupport.sev.${s}`)}
              </MenuItem>
            ))}
          </TextField>
          <Typography variant="body2" color="text.secondary">
            {t('platformSupport.attachNote')}
          </Typography>
          {send.isError ? <HelpErrorAlert error={send.error} /> : null}
          {send.isSuccess ? <Alert severity="success">{t('platformSupport.sent')}</Alert> : null}
          <Button
            variant="contained"
            sx={{ alignSelf: 'flex-start' }}
            disabled={subject.trim().length < 3 || send.isPending}
            onClick={() => send.mutate()}
          >
            {t('platformSupport.send')}
          </Button>
        </Stack>
      </Paper>
      <Typography variant="h6" component="h2">
        {t('platformSupport.myRequests')}
      </Typography>
      {(tickets.data ?? []).length === 0 && tickets.isSuccess ? (
        <Typography color="text.secondary">{t('platformSupport.none')}</Typography>
      ) : null}
      {(tickets.data ?? []).map((row) => (
        <Stack key={row.id} spacing={0.5}>
          <Typography variant="body2">
            {t('platformSupport.line', {
              id: String(row.id),
              subject: row.subject,
              status: t(`platformSupport.status.${row.status}`),
            })}
          </Typography>
          {survey.data?.enabled && row.status === 'RESOLVED' ? (
            row.satisfactionScore != null ? (
              <Typography variant="caption" color="text.secondary">
                {t('survey.csatRated', { n: String(row.satisfactionScore) })}
              </Typography>
            ) : (
              <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" role="group" aria-label={t('survey.csatQuestion')}>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
                  {t('survey.csatQuestion')}
                </Typography>
                {[1, 2, 3, 4, 5].map((n) => (
                  <Button
                    key={n}
                    size="small"
                    variant="outlined"
                    disabled={rate.isPending}
                    aria-label={t('survey.csatScore', { n: String(n) })}
                    onClick={() => rate.mutate({ id: row.id, score: n })}
                    sx={{ minWidth: 36, minHeight: 36, px: 0 }}
                  >
                    {n}
                  </Button>
                ))}
              </Stack>
            )
          ) : null}
        </Stack>
      ))}
      {rate.isError ? <Typography variant="caption" color="error">{t('survey.failed')}</Typography> : null}
      {user?.role === 'OWNER' ? <SupportAccessPanel tickets={tickets.data ?? []} /> : null}
    </Stack>
  );
}
