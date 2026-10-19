import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import FormControlLabel from '@mui/material/FormControlLabel';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DisclaimerBanner, PageHeader } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { settingsErrorText } from '@/utils/settingsErrors';

// Bill scan on/off and the monthly limit are Bizboard-controlled (the server ignores them from the
// owner), so they are shown, not edited, and are never sent.
type AiForm = {
  dailySummaryEmailEnabled: boolean;
  openingCashBalance: string;
  openingCashAsOf: string;
};

export function AiSettingsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const { control, handleSubmit, reset, formState: { isDirty } } = useForm<AiForm>({
    defaultValues: {
      dailySummaryEmailEnabled: false,
      openingCashBalance: '',
      openingCashAsOf: '',
    },
  });

  useEffect(() => {
    if (!query.data) return;
    reset({
      dailySummaryEmailEnabled: !!query.data.dailySummaryEmailEnabled,
      openingCashBalance:
        query.data.openingCashBalance != null ? String(query.data.openingCashBalance) : '',
      openingCashAsOf: query.data.openingCashAsOf ?? '',
    });
  }, [query.data, reset]);

  const mutation = useMutation({
    mutationFn: (values: AiForm) => {
      const balance = values.openingCashBalance.trim();
      const asOf = values.openingCashAsOf.trim();
      if ((balance === '') !== (asOf === '')) throw new Error(t('aiPage.cashNeedsBoth'));
      if (balance !== '' && Number.isNaN(Number(balance))) throw new Error(t('aiPage.cashNotNumber'));
      return updateCompany({
        dailySummaryEmailEnabled: values.dailySummaryEmailEnabled,
        openingCashBalance: balance || null,
        openingCashAsOf: asOf || null,
      });
    },
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: ['company'] });
      // F3-015: clear the dirty flag post-save (see UnsavedChangesGuard below).
      reset(variables);
    },
  });
  // F3-073: dismissable "saved" banner; reappears on the next save because
  // mutation.submittedAt advances with every mutate() call.
  const [savedAck, setSavedAck] = useState(0);

  if (!canManageUsers(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={settingsErrorText(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  return (
    <Stack
      spacing={2}
      component="form"
      onSubmit={handleSubmit((v) => mutation.mutate(v))}
      sx={{ maxWidth: 640 }}
    >
      <UnsavedChangesGuard when={isDirty} />
      <PageHeader title={t('nav.aiSettings')} subtitle={t('insights.settingsSubtitle')} />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {mutation.isSuccess && mutation.submittedAt !== savedAck ? (
        <Alert severity="success" onClose={() => setSavedAck(mutation.submittedAt)}>
          {t('insights.settingsSaved')}
        </Alert>
      ) : null}
      {mutation.isError ? <HelpErrorAlert error={mutation.error} /> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography variant="subtitle2">{t('aiPage.statusTitle')}</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip
                size="small"
                color={query.data?.aiFeaturesEnabled === true ? 'success' : 'default'}
                label={query.data?.aiFeaturesEnabled === true ? t('aiPage.statusOn') : t('aiPage.statusOff')}
              />
              <Typography variant="body2" color="text.secondary">
                {t('aiPage.budget')}:{' '}
                {query.data?.aiMonthlyTokenBudget != null ? String(query.data.aiMonthlyTokenBudget) : t('aiPage.budgetDefault')}
              </Typography>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {t('aiPage.statusHelp')} {t('aiPage.budgetHelp')}
            </Typography>
          </Stack>
          <Controller
            name="dailySummaryEmailEnabled"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={
                  <Switch checked={!!field.value} onChange={(_, c) => field.onChange(c)} />
                }
                label={t('insights.dailyEmail')}
              />
            )}
          />
          <Typography variant="caption" color="text.secondary">
            {t('aiPage.emailHelp')}
          </Typography>
          <Typography variant="subtitle2" sx={{ pt: 1 }}>
            {t('aiPage.cashTitle')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('aiPage.cashHelp')}
          </Typography>
          <Controller
            name="openingCashBalance"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label={t('insights.openingCash')}
                size="small"
              />
            )}
          />
          <Controller
            name="openingCashAsOf"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label={t('insights.openingCashAsOf')}
                size="small"
                type="date"
                InputLabelProps={{ shrink: true }}
              />
            )}
          />
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
