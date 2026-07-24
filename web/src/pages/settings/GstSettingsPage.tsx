import { useEffect } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { t } from '@/i18n';
import type { NegativeStockPolicy, RegistrationType } from '@/types/domain';
import { isValidGstin } from '@/utils/gst';
import { canManageGst } from '@/utils/permissions';

interface GstForm {
  gstin: string;
  state: string;
  registrationType: RegistrationType;
  negativeStockPolicy: NegativeStockPolicy;
  assumeLocalStateForBlankParty: boolean;
}

export function GstSettingsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const { control, handleSubmit, reset, formState } = useForm<GstForm>();

  useEffect(() => {
    if (query.data) {
      reset({
        gstin: query.data.gstin ?? '',
        state: query.data.state ?? '',
        registrationType: query.data.registrationType ?? 'REGULAR',
        negativeStockPolicy: query.data.negativeStockPolicy ?? 'BLOCK',
        assumeLocalStateForBlankParty: !!query.data.assumeLocalStateForBlankParty,
      });
    }
  }, [query.data, reset]);

  const mutation = useMutation({
    mutationFn: (values: GstForm) => updateCompany(values),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['company'] }),
  });

  if (!canManageGst(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />;
  }

  return (
    <Stack
      spacing={2}
      component="form"
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
    >
      <Typography variant="h4">{t('nav.gst')}</Typography>
      {mutation.isSuccess ? <Alert severity="success">GST settings saved</Alert> : null}
      <Paper sx={{ p: 2, maxWidth: 560 }}>
        <Stack spacing={2}>
          <Controller
            name="gstin"
            control={control}
            rules={{
              validate: (v) => !v || isValidGstin(v) || 'Invalid GSTIN format',
            }}
            render={({ field }) => (
              <TextField
                label="GSTIN"
                error={Boolean(formState.errors.gstin)}
                helperText={formState.errors.gstin?.message}
                {...field}
              />
            )}
          />
          <Controller
            name="state"
            control={control}
            render={({ field }) => <TextField label="State" {...field} />}
          />
          <Controller
            name="registrationType"
            control={control}
            render={({ field }) => (
              <TextField select label="Registration type" {...field}>
                <MenuItem value="REGULAR">Regular</MenuItem>
                <MenuItem value="COMPOSITION">Composition</MenuItem>
                <MenuItem value="UNREGISTERED">Unregistered</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="negativeStockPolicy"
            control={control}
            render={({ field }) => (
              <TextField select label="Negative stock policy" {...field}>
                <MenuItem value="WARN">Warn</MenuItem>
                <MenuItem value="BLOCK">Block</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="assumeLocalStateForBlankParty"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={!!field.value}
                    onChange={(e) => field.onChange(e.target.checked)}
                  />
                }
                label="Assume local (intra-state) when party state/GSTIN is blank"
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
