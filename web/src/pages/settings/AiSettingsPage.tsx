import { useEffect } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { getErrorMessage } from '@/api/client';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DisclaimerBanner, PageHeader } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type AiForm = {
  aiFeaturesEnabled: boolean;
  dailySummaryEmailEnabled: boolean;
  aiMonthlyTokenBudget: string;
  openingCashBalance: string;
  openingCashAsOf: string;
};

export function AiSettingsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const { control, handleSubmit, reset } = useForm<AiForm>({
    defaultValues: {
      aiFeaturesEnabled: false,
      dailySummaryEmailEnabled: false,
      aiMonthlyTokenBudget: '',
      openingCashBalance: '',
      openingCashAsOf: '',
    },
  });

  useEffect(() => {
    if (!query.data) return;
    reset({
      // BB-000756: fail-closed — only ON when explicitly true (model default is False).
      aiFeaturesEnabled: query.data.aiFeaturesEnabled === true,
      dailySummaryEmailEnabled: !!query.data.dailySummaryEmailEnabled,
      aiMonthlyTokenBudget:
        query.data.aiMonthlyTokenBudget != null ? String(query.data.aiMonthlyTokenBudget) : '',
      openingCashBalance:
        query.data.openingCashBalance != null ? String(query.data.openingCashBalance) : '',
      openingCashAsOf: query.data.openingCashAsOf ?? '',
    });
  }, [query.data, reset]);

  const mutation = useMutation({
    mutationFn: (values: AiForm) =>
      updateCompany({
        aiFeaturesEnabled: values.aiFeaturesEnabled,
        dailySummaryEmailEnabled: values.dailySummaryEmailEnabled,
        aiMonthlyTokenBudget: values.aiMonthlyTokenBudget
          ? Number(values.aiMonthlyTokenBudget)
          : null,
        openingCashBalance: values.openingCashBalance || null,
        openingCashAsOf: values.openingCashAsOf || null,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['company'] }),
  });

  if (!canManageUsers(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  return (
    <Stack
      spacing={2}
      component="form"
      onSubmit={handleSubmit((v) => mutation.mutate(v))}
      sx={{ maxWidth: 640 }}
    >
      <PageHeader title={t('nav.aiSettings')} subtitle={t('insights.settingsSubtitle')} />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {mutation.isSuccess ? <Alert severity="success">{t('insights.settingsSaved')}</Alert> : null}
      {mutation.isError ? <HelpErrorAlert error={mutation.error} /> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Controller
            name="aiFeaturesEnabled"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={
                  <Switch checked={!!field.value} onChange={(_, c) => field.onChange(c)} />
                }
                label={t('insights.enableAi')}
              />
            )}
          />
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
          <Controller
            name="aiMonthlyTokenBudget"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label={t('insights.tokenBudget')}
                size="small"
                type="number"
                helperText={t('insights.tokenBudgetHelp')}
              />
            )}
          />
          <Controller
            name="openingCashBalance"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label={t('insights.openingCash')}
                size="small"
                helperText={t('insights.openingCashHelp')}
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
