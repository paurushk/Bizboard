import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getNpsDue, NPS_DUE_QUERY_KEY, sendSatisfaction } from '@/api/platformSupport';
import { t } from '@/i18n';

const SCORES = Array.from({ length: 11 }, (_, n) => n);

/**
 * BB-136 (D-08): an occasional "would you recommend us" card. The server decides when it is due
 * (ENABLE_SATISFACTION_SURVEY on, member for 14+ days, not asked in 90 days). It never blocks the
 * page: it sits in a corner, and "Not now" counts as asked.
 */
export function NpsPrompt() {
  const qc = useQueryClient();
  const due = useQuery({ queryKey: NPS_DUE_QUERY_KEY, queryFn: getNpsDue, staleTime: 30 * 60_000, retry: false });
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [done, setDone] = useState<'sent' | 'hidden' | null>(null);
  const send = useMutation({
    mutationFn: (value: number | null) => sendSatisfaction({ kind: 'NPS', score: value, comment: value === null ? '' : comment }),
    onSuccess: (_, value) => {
      setDone(value === null ? 'hidden' : 'sent');
      void qc.invalidateQueries({ queryKey: NPS_DUE_QUERY_KEY });
    },
  });

  if (done === 'hidden' || (!due.data?.due && done !== 'sent')) return null;

  return (
    <Paper
      role="region"
      aria-label={t('survey.npsTitle')}
      elevation={6}
      sx={{
        position: 'fixed',
        zIndex: (theme) => theme.zIndex.snackbar,
        right: { xs: 8, sm: 24 },
        left: { xs: 8, sm: 'auto' },
        bottom: { xs: 8, sm: 24 },
        maxWidth: { sm: 440 },
        p: 2,
      }}
    >
      {done === 'sent' ? (
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography variant="body2">{t('survey.thanks')}</Typography>
          <Button size="small" onClick={() => setDone('hidden')}>{t('survey.close')}</Button>
        </Stack>
      ) : (
        <Stack spacing={1.5}>
          <Typography variant="subtitle2" component="h2">{t('survey.npsTitle')}</Typography>
          <Typography variant="body2" id="nps-question">{t('survey.npsQuestion')}</Typography>
          <Box role="group" aria-labelledby="nps-question" sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {SCORES.map((n) => (
              <Button
                key={n}
                size="small"
                variant={score === n ? 'contained' : 'outlined'}
                aria-pressed={score === n}
                aria-label={t('survey.score', { n: String(n) })}
                onClick={() => setScore(n)}
                sx={{ minWidth: 36, minHeight: 36, px: 0 }}
              >
                {n}
              </Button>
            ))}
          </Box>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">{t('survey.npsLow')}</Typography>
            <Typography variant="caption" color="text.secondary">{t('survey.npsHigh')}</Typography>
          </Stack>
          {score !== null ? (
            <TextField
              size="small"
              multiline
              minRows={2}
              label={t('survey.commentLabel')}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              inputProps={{ maxLength: 2000 }}
            />
          ) : null}
          {send.isError ? <Typography variant="caption" color="error">{t('survey.failed')}</Typography> : null}
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" disabled={send.isPending} onClick={() => send.mutate(null)}>
              {t('survey.notNow')}
            </Button>
            <Button
              size="small"
              variant="contained"
              disabled={score === null || send.isPending}
              onClick={() => send.mutate(score)}
            >
              {t('survey.send')}
            </Button>
          </Stack>
        </Stack>
      )}
    </Paper>
  );
}
