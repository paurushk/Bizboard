import { useEffect, useRef, useState } from 'react';
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
import { getErrorMessage } from '@/api/client';
import { HelpHint } from '@/pages/help/HelpHint';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import {
  getCompany,
  updateCompany,
  verifyCompanyGstin,
  verifyCompanyPan,
  verifyCompanyUdyam,
} from '@/api/resources';
import { BranchGstinsPanel } from '@/pages/settings/BranchGstinsPanel';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import type { NegativeStockPolicy, RegistrationType } from '@/types/domain';
import { isValidGstin } from '@/utils/gst';
import { canManageGst } from '@/utils/permissions';

interface GstForm {
  gstin: string;
  pan: string;
  udyam: string;
  state: string;
  registrationType: RegistrationType;
  negativeStockPolicy: NegativeStockPolicy;
  valuationBusinessDateOrder: boolean;
  recomputeTaxOnComplete: boolean;
  assumeLocalStateForBlankParty: boolean;
  einvoiceEnabled: boolean;
  ewayEnabled: boolean;
  ewayThresholdAmount: string;
  aatoTurnover: string;
  gspProvider: string;
  gspClientId: string;
  gspClientSecret: string;
  gspUsername: string;
  clearGspCredentials: boolean;
}

export function GstSettingsPage() {
  useLocale();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  // F3-014: no refetch-and-reset on window focus — it wipes unsaved edits.
  const query = useQuery({
    queryKey: ['company'],
    queryFn: getCompany,
    refetchOnWindowFocus: false,
  });
  const { control, handleSubmit, reset, watch, formState, setError, clearErrors } = useForm<GstForm>({
    defaultValues: {
      gstin: '',
      pan: '',
      udyam: '',
      state: '',
      registrationType: 'REGULAR',
      negativeStockPolicy: 'BLOCK',
      valuationBusinessDateOrder: false,
      recomputeTaxOnComplete: false,
      assumeLocalStateForBlankParty: true,
      einvoiceEnabled: false,
      ewayEnabled: false,
      ewayThresholdAmount: '50000',
      aatoTurnover: '',
      gspProvider: '',
      gspClientId: '',
      gspClientSecret: '',
      gspUsername: '',
      clearGspCredentials: false,
    },
  });

  const gstSeededRef = useRef(false);
  useEffect(() => {
    if (query.data && !gstSeededRef.current) {
      gstSeededRef.current = true;
      const d = query.data;
      reset({
        gstin: d.gstin ?? '',
        pan: d.pan ?? '',
        udyam: d.udyam ?? '',
        state: d.state ?? '',
        registrationType: d.registrationType ?? 'REGULAR',
        negativeStockPolicy: d.negativeStockPolicy ?? 'BLOCK',
        valuationBusinessDateOrder: !!d.valuationBusinessDateOrder,
        recomputeTaxOnComplete: !!d.recomputeTaxOnComplete,
        assumeLocalStateForBlankParty: !!d.assumeLocalStateForBlankParty,
        einvoiceEnabled: !!d.einvoiceEnabled,
        ewayEnabled: !!d.ewayEnabled,
        ewayThresholdAmount: String(d.ewayThresholdAmount ?? '50000'),
        aatoTurnover: String(d.aatoTurnover ?? ''),
        gspProvider: String(d.gspProvider ?? ''),
        gspClientId: '',
        gspClientSecret: '',
        gspUsername: '',
        clearGspCredentials: false,
      });
    }
  }, [query.data, reset]);

  const mutation = useMutation({
    mutationFn: (values: GstForm) => {
      const gstin = (values.gstin ?? '').trim().toUpperCase();
      if (gstin && !isValidGstin(gstin)) {
        setError('gstin', { message: 'Enter a valid 15-character GSTIN.' });
        throw new Error('Enter a valid 15-character GSTIN.');
      }
      const payload: Record<string, unknown> = {
        // These are CharField(blank=True) without null=True on the backend —
        // sending null instead of '' 400s with "This field may not be null."
        gstin,
        pan: (values.pan ?? '').trim().toUpperCase(),
        udyam: (values.udyam ?? '').trim().toUpperCase(),
        state: values.state ?? '',
        registrationType: values.registrationType,
        negativeStockPolicy: values.negativeStockPolicy,
        valuationBusinessDateOrder: values.valuationBusinessDateOrder,
        recomputeTaxOnComplete: values.recomputeTaxOnComplete,
        assumeLocalStateForBlankParty: values.assumeLocalStateForBlankParty,
        einvoice_enabled: values.einvoiceEnabled,
        eway_enabled: values.ewayEnabled,
        eway_threshold_amount: values.ewayThresholdAmount || '50000',
        aato_turnover: values.aatoTurnover || null,
        gsp_provider: values.gspProvider || '',
      };
      if (values.clearGspCredentials) {
        payload.clear_gsp_credentials = true;
      } else {
        const creds: Record<string, string> = {};
        if (values.gspClientId?.trim()) creds.client_id = values.gspClientId.trim();
        if (values.gspClientSecret?.trim()) creds.client_secret = values.gspClientSecret.trim();
        if (values.gspUsername?.trim()) creds.username = values.gspUsername.trim();
        if (Object.keys(creds).length) payload.gsp_credentials = creds;
      }
      return updateCompany(payload as never);
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['company'] });
      void queryClient.invalidateQueries({ queryKey: ['company-gstins'] });
      // F3-015: clear the dirty flag post-save (see UnsavedChangesGuard below).
      reset(variables);
    },
  });
  // F3-073: dismissable "saved" banner; reappears on the next save because
  // mutation.submittedAt advances with every mutate() call.
  const [savedAck, setSavedAck] = useState(0);
  const [gstConfirmed, setGstConfirmed] = useState(false);
  const [needsGstConfirm, setNeedsGstConfirm] = useState(false);

  const verifyMutation = useMutation({
    mutationFn: async () => {
      const gstin = (query.data?.gstin ?? '').trim();
      if (!gstin) throw new Error('Add and save a GSTIN first.');
      return verifyCompanyGstin();
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['company'] }),
  });
  const panVerifyMutation = useMutation({
    mutationFn: verifyCompanyPan,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['company'] }),
  });
  const udyamVerifyMutation = useMutation({
    mutationFn: verifyCompanyUdyam,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['company'] }),
  });

  if (!canManageGst(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        message={getErrorMessage(query.error)}
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const company = query.data;

  return (
    <Stack
      spacing={2}
      component="form"
      onSubmit={handleSubmit((values) => {
        // F3-049: registration type and negative-stock policy are high-impact
        // flips — spell out the consequence before saving the change.
        const prev = query.data;
        if (prev && values.registrationType !== prev.registrationType) {
          if (
            !window.confirm(
              t('gst.confirmRegistrationChange', {
                type: values.registrationType,
              }),
            )
          ) {
            return;
          }
        }
        if (prev && values.negativeStockPolicy !== prev.negativeStockPolicy) {
          if (
            !window.confirm(
              t('gst.confirmNegativeStockChange', {
                policy: values.negativeStockPolicy,
              }),
            )
          ) {
            return;
          }
        }
        const typed = (values.gstin ?? '').trim().toUpperCase();
        const saved = (prev?.gstin ?? '').trim().toUpperCase();
        // Only a new or changed GSTIN needs the confirmation. An unregistered business, or any
        // other setting, saves without it. A blocked save says why instead of doing nothing.
        if (typed && typed !== saved && !gstConfirmed) {
          setNeedsGstConfirm(true);
          return;
        }
        setNeedsGstConfirm(false);
        mutation.mutate(values);
      })}
    >
      <UnsavedChangesGuard when={formState.isDirty} />
      <PageTitle>{t('nav.gst')}</PageTitle>
      {mutation.isSuccess && mutation.submittedAt !== savedAck ? (
        <Alert severity="success" onClose={() => setSavedAck(mutation.submittedAt)}>
          {t('gst.settingsSaved')}
        </Alert>
      ) : null}
      {mutation.isError ? <HelpErrorAlert error={mutation.error} /> : null}
      {verifyMutation.isSuccess ? (
        <Alert severity="info">
          {t('gst.verifyStatus', {
            status: verifyMutation.data?.status ?? t('gst.verified'),
            name: verifyMutation.data?.tradeName || t('gst.active'),
          })}
        </Alert>
      ) : null}
      {verifyMutation.isError ? (
        <HelpErrorAlert error={verifyMutation.error} />
      ) : null}
      <Paper sx={{ p: 3, maxWidth: 640 }}>
        <Stack spacing={2}>
          <Typography variant="h6" fontWeight={600}>
            1. Basic GST Setup
          </Typography>
          <Controller
            name="gstin"
            control={control}
            render={({ field }) => (
              <HelpHint intent="add-gstin" slot="gstin">
                <TextField
                  label={t('gstSettings.primaryGstin')}
                  placeholder="07AAAAA0000A1Z5"
                  error={Boolean(formState.errors.gstin)}
                  helperText={
                    formState.errors.gstin?.message ||
                    String(company?.gstinVerificationStatus ?? 'Leave blank if unregistered / composite')
                  }
                  {...field}
                  onChange={(e) => {
                    field.onChange(e);
                    if (formState.errors.gstin) {
                      clearErrors('gstin');
                    }
                  }}
                />
              </HelpHint>
            )}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={verifyMutation.isPending || !watch('gstin')}
            onClick={() => verifyMutation.mutate()}
          >
            {t('sweep2.verifyGstin')}
          </Button>
          <Controller
            name="pan"
            control={control}
            render={({ field }) => (
              <TextField
                label={t('gstSettings.pan')}
                placeholder="ABCDE1234F"
                helperText={String(company?.panVerificationStatus ?? 'Optional — format check only until a live PAN provider is certified')}
                {...field}
              />
            )}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={panVerifyMutation.isPending || !watch('pan')}
            onClick={() => panVerifyMutation.mutate()}
          >
            {t('sweep2.verifyPan')}
          </Button>
          {panVerifyMutation.isError ? (
            <HelpErrorAlert error={panVerifyMutation.error} />
          ) : null}
          <Controller
            name="udyam"
            control={control}
            render={({ field }) => (
              <TextField
                label={t('gstSettings.udyam')}
                placeholder="UDYAM-KR-00-0000000"
                helperText={String(company?.udyamVerificationStatus ?? 'Optional — format check only until a live UDYAM provider is certified')}
                {...field}
              />
            )}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={udyamVerifyMutation.isPending || !watch('udyam')}
            onClick={() => udyamVerifyMutation.mutate()}
          >
            {t('sweep2.verifyUdyam')}
          </Button>
          {udyamVerifyMutation.isError ? (
            <HelpErrorAlert error={udyamVerifyMutation.error} />
          ) : null}
          <Controller
            name="state"
            control={control}
            render={({ field }) => <StateSelect value={field.value ?? ''} onChange={field.onChange} />}
          />
          <Controller
            name="registrationType"
            control={control}
            render={({ field }) => (
              <HelpHint intent="registration-type" slot="registration-type-settings">
                <TextField select label={t('gstSettings.registrationType')} {...field} value={field.value ?? 'REGULAR'}>
                  <MenuItem value="REGULAR">{t('gstSettings.regular')}</MenuItem>
                  <MenuItem value="COMPOSITION">{t('gstSettings.composition')}</MenuItem>
                  <MenuItem value="UNREGISTERED">{t('gstSettings.unregistered')}</MenuItem>
                </TextField>
              </HelpHint>
            )}
          />
          <Controller
            name="negativeStockPolicy"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label={t('gstSettings.stockPolicy')}
                helperText={t('gstSettings.stockPolicyHint')}
                {...field}
              >
                <MenuItem value="BLOCK">{t('gstSettings.blockBilling')}</MenuItem>
                <MenuItem value="WARN">{t('gstSettings.allowWarn')}</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="valuationBusinessDateOrder"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label={t('settings.valuationDateOrder')}
              />
            )}
          />
          <Typography variant="caption" color="text.secondary">
            {t('settings.valuationDateOrderHelp')}
          </Typography>
          <Controller
            name="recomputeTaxOnComplete"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label={t('settings.recomputeTaxOnComplete')}
              />
            )}
          />
          <Typography variant="caption" color="text.secondary">
            {t('settings.recomputeTaxOnCompleteHelp')}
          </Typography>
          <Controller
            name="assumeLocalStateForBlankParty"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label={t('gst.assumeLocalState')}
              />
            )}
          />
        </Stack>
      </Paper>

      <Paper sx={{ p: 3, maxWidth: 640 }}>
        <Stack spacing={2}>
          <Typography variant="h6" fontWeight={600}>
            2. e-Invoice, e-Way & Portal Sync (Optional)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Configure statutory e-Invoice and automated e-Way bill generation if your business turnover exceeds statutory thresholds.
          </Typography>
          <Controller
            name="aatoTurnover"
            control={control}
            render={({ field }) => (
              <TextField
                label={t('gstSettings.turnover')}
                placeholder={t('sweep.turnoverExample')}
                helperText={t('sweep.turnoverHelp')}
                {...field}
              />
            )}
          />
          <Controller
            name="einvoiceEnabled"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label={t('gstSettings.einvoice')}
              />
            )}
          />
          <Controller
            name="ewayEnabled"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label={t('gstSettings.eway')}
              />
            )}
          />
          <Controller
            name="ewayThresholdAmount"
            control={control}
            render={({ field }) => (
              <TextField
                label={t('gstSettings.ewayThreshold')}
                helperText={t('gstSettings.ewayThresholdHint')}
                {...field}
              />
            )}
          />
          <Typography variant="subtitle1" fontWeight={600} sx={{ pt: 1 }}>
            {t('gstSettings.gspTitle')}
          </Typography>
          <Alert severity="info">
            {t('gstSettings.gspWriteOnly')}{' '}
            {company?.gspCredentialsConfigured ? t('gstSettings.gspActive') : t('gstSettings.gspNone')}
          </Alert>
          <Controller
            name="gspProvider"
            control={control}
            render={({ field }) => (
              <TextField select label={t('gstSettings.gspProvider')} {...field}>
                <MenuItem value="">{t('gstSettings.gspManual')}</MenuItem>
                <MenuItem value="sandbox">{t('gstSettings.gspSandbox')}</MenuItem>
                <MenuItem value="cleartax">{t('gstSettings.gspCleartax')}</MenuItem>
                <MenuItem value="mastergst">{t('gstSettings.gspMaster')}</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="gspClientId"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label={t('gstSettings.clientId')}
                autoComplete="off"
                name="gsp_client_id"
                inputProps={{ autoComplete: 'off' }}
              />
            )}
          />
          <Controller
            name="gspClientSecret"
            control={control}
            render={({ field }) => (
              <TextField
                  {...field}
                  label={t('gstSettings.clientSecret')}
                  type="password"
                  autoComplete="new-password"
                  name="gsp_client_secret"
                  inputProps={{ autoComplete: 'new-password' }}
                />
            )}
          />
          <Controller
            name="gspUsername"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label={t('gstSettings.portalUsername')}
                autoComplete="off"
                name="gsp_portal_username"
                inputProps={{ autoComplete: 'off' }}
              />
            )}
          />
          <FormControlLabel
            control={<Checkbox checked={gstConfirmed} onChange={(_, checked) => setGstConfirmed(checked)} />}
            label={t('cog.gstConfirm')}
          />
          {needsGstConfirm && !gstConfirmed ? (
            <Alert severity="warning">{t('cog.gstConfirm')}</Alert>
          ) : null}
          <Button type="submit" variant="contained" size="large" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>

      <BranchGstinsPanel />
    </Stack>
  );
}
