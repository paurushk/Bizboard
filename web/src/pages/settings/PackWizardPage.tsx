import { useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { confirmPack, getPackWizard, proposePack } from '@/api/osPlan';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { fetchFeatureFlags } from '@/config/featureFlags';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const emptyAnswers = {
  what_you_sell: '',
  how_you_sell: '',
  deliver: '',
  gst_registered: '',
};

export function PackWizardPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['pack-wizard'], queryFn: getPackWizard });
  const [answers, setAnswers] = useState(emptyAnswers);
  const [proposed, setProposed] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [skipped, setSkipped] = useState<string[]>([]);
  const loaded = query.data;
  useEffect(() => {
    if (!query.data) return;
    setAnswers({
      what_you_sell: query.data.answers.what_you_sell || '',
      how_you_sell: query.data.answers.how_you_sell || '',
      deliver: query.data.answers.deliver || '',
      gst_registered: query.data.answers.gst_registered || '',
    });
    if (query.data.proposedPack) setProposed(query.data.proposedPack);
  }, [query.data]);

  const propose = useMutation({
    mutationFn: () => proposePack(answers),
    onSuccess: (result) => {
      setProposed(result.proposedPack);
      setSaved(false);
      setError(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const apply = useMutation({
    mutationFn: () => confirmPack(answers),
    onSuccess: async (result) => {
      setSaved(true);
      setSkipped(result.skippedFlags ?? []);
      setError(null);
      await fetchFeatureFlags(true);
      void qc.invalidateQueries({ queryKey: ['pack-wizard'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const current = proposed || loaded?.proposedPack || '';
  const flags = current && loaded ? loaded.packs[current] ?? [] : [];

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.packWizard')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.packHelp')}</Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      {loaded ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <TextField
              label={t('osPlan.whatYouSell')}
              value={answers.what_you_sell}
              onChange={(e) => setAnswers((prev) => ({ ...prev, what_you_sell: e.target.value }))}
            />
            <TextField
              select
              label={t('osPlan.howYouSell')}
              value={answers.how_you_sell}
              onChange={(e) => setAnswers((prev) => ({ ...prev, how_you_sell: e.target.value }))}
            >
              <MenuItem value="counter">{t('osPlan.counter')}</MenuItem>
              <MenuItem value="field">{t('osPlan.field')}</MenuItem>
            </TextField>
            <TextField
              select
              label={t('osPlan.deliver')}
              value={answers.deliver}
              onChange={(e) => setAnswers((prev) => ({ ...prev, deliver: e.target.value }))}
            >
              <MenuItem value="yes">{t('common.yes')}</MenuItem>
              <MenuItem value="no">{t('common.no')}</MenuItem>
            </TextField>
            <TextField
              select
              label={t('osPlan.gstRegistered')}
              value={answers.gst_registered}
              onChange={(e) => setAnswers((prev) => ({ ...prev, gst_registered: e.target.value }))}
            >
              <MenuItem value="yes">{t('common.yes')}</MenuItem>
              <MenuItem value="no">{t('common.no')}</MenuItem>
            </TextField>
            <Stack direction="row" spacing={1}>
              <Button variant="outlined" disabled={propose.isPending} onClick={() => propose.mutate()}>
                {t('osPlan.seePack')}
              </Button>
              <Button variant="contained" disabled={!current || apply.isPending} onClick={() => apply.mutate()}>
                {t('osPlan.applyPack')}
              </Button>
            </Stack>
            {current ? (
              <Typography variant="body2">
                {t('osPlan.proposedPack', { name: current })}
                {flags.length ? ` — ${flags.join(', ')}` : ''}
              </Typography>
            ) : null}
            {loaded.appliedPack ? (
              <Typography variant="caption" color="text.secondary">
                {t('osPlan.appliedPack', { name: loaded.appliedPack })}
              </Typography>
            ) : null}
            {saved ? <Typography variant="body2">{t('osPlan.packSaved')}</Typography> : null}
            {skipped.length ? <Typography variant="body2">{t('osPlan.packSkipped', { names: skipped.join(', ') })}</Typography> : null}
            {loaded.heldPacks.length ? (
              <Typography variant="caption" color="text.secondary">
                {t('osPlan.heldPacks', { names: loaded.heldPacks.join(', ') })}
              </Typography>
            ) : null}
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
