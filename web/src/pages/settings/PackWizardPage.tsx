import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { confirmPack, getPackWizard, proposePack, setNavScope, type PackPreview } from '@/api/osPlan';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { fetchFeatureFlags } from '@/config/featureFlags';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { settingsErrorText } from '@/utils/settingsErrors';

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
  // The preview belongs to the answers it was made for; changing an answer invalidates it.
  const [preview, setPreview] = useState<PackPreview | null>(null);
  const [previewFor, setPreviewFor] = useState('');
  const loaded = query.data;
  // Fill the form from the saved answers each time they load.
  const [seenData, setSeenData] = useState<typeof query.data>(undefined);
  if (query.data && query.data !== seenData) {
    setSeenData(query.data);
    setAnswers({
      what_you_sell: query.data.answers.what_you_sell || '',
      how_you_sell: query.data.answers.how_you_sell || '',
      deliver: query.data.answers.deliver || '',
      gst_registered: query.data.answers.gst_registered || '',
    });
    if (query.data.proposedPack) setProposed(query.data.proposedPack);
  }

  const propose = useMutation({
    mutationFn: () => proposePack(answers),
    onSuccess: (result) => {
      setProposed(result.proposedPack);
      setPreview(result.preview ?? null);
      setPreviewFor(JSON.stringify(answers));
      setSaved(false);
      setError(null);
    },
    onError: (err) => setError(settingsErrorText(err)),
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
    onError: (err) => setError(settingsErrorText(err)),
  });

  const current = proposed || loaded?.proposedPack || '';
  const previewFresh = preview !== null && previewFor === JSON.stringify(answers);
  const flags = current && loaded ? loaded.packs[current] ?? [] : [];

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.packWizard')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.packHelp')}</Typography>
      <Stack direction="row" spacing={1}>
        <Button
          variant={isRuntimeFlagEnabled('NAV_PACK_DEFAULT') ? 'outlined' : 'contained'}
          onClick={() => void setNavScope(true).then(() => fetchFeatureFlags(true))}
        >
          {t('osPlan.showAllFeatures')}
        </Button>
        <Button
          variant={isRuntimeFlagEnabled('NAV_PACK_DEFAULT') ? 'contained' : 'outlined'}
          onClick={() => void setNavScope(false).then(() => fetchFeatureFlags(true))}
        >
          {t('osPlan.showPackNav')}
        </Button>
      </Stack>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={settingsErrorText(query.error)} error={query.error} onRetry={() => void query.refetch()} />
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
              <Button
                variant="contained"
                disabled={!current || !previewFresh || apply.isPending}
                onClick={() => apply.mutate()}
              >
                {t('osPlan.applyPack')}
              </Button>
            </Stack>
            {!preview ? (
              <Typography variant="caption" color="text.secondary">{t('packPreview.seeFirst')}</Typography>
            ) : !previewFresh ? (
              <Alert severity="info">{t('packPreview.changed')}</Alert>
            ) : null}
            {preview && previewFresh ? (
              <Stack spacing={1} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
                <Typography variant="subtitle2">{t('packPreview.title')}</Typography>
                <Typography variant="caption" color="text.secondary">{t('packPreview.onlyOn')}</Typography>
                {preview.wouldEnable.length === 0 ? (
                  <Typography variant="body2">{t('packPreview.nothing')}</Typography>
                ) : null}
                {([
                  ['wouldEnable', preview.wouldEnable],
                  ['alreadyOn', preview.alreadyOn],
                  ['keptAsSet', preview.keptAsSet],
                  ['unavailable', preview.unavailable],
                ] as const).map(([key, names]) =>
                  names.length ? (
                    <Typography key={key} variant="body2">
                      <strong>{t(`packPreview.${key}`)}:</strong> {names.join(', ')}
                    </Typography>
                  ) : null,
                )}
              </Stack>
            ) : null}
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
