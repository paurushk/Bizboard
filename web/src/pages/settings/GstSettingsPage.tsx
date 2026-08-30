import { useEffect, useState } from 'react';
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
import {
  createCompanyGstin,
  getCompany,
  listCompanyGstins,
  updateCompany,
  updateCompanyGstin,
  verifyCompanyGstin,
  verifyCompanyPan,
  verifyCompanyUdyam,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { t } from '@/i18n';
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
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const gstinsQuery = useQuery({ queryKey: ['company-gstins'], queryFn: listCompanyGstins });
  const [branchGstin, setBranchGstin] = useState('');
  const [branchState, setBranchState] = useState('');
  const [branchName, setBranchName] = useState('');
  const { control, handleSubmit, reset, watch, formState, setError, clearErrors } = useForm<GstForm>({
    defaultValues: {
      gstin: '',
      pan: '',
      udyam: '',
      state: '',
      registrationType: 'UNREGISTERED',
      negativeStockPolicy: 'BLOCK',
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

  useEffect(() => {
    if (query.data) {
      const d = query.data;
      reset({
        gstin: d.gstin ?? '',
        pan: d.pan ?? '',
        udyam: d.udyam ?? '',
        state: d.state ?? '',
        registrationType: d.registrationType ?? 'REGULAR',
        negativeStockPolicy: d.negativeStockPolicy ?? 'BLOCK',
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
        gstin: gstin || null,
        pan: (values.pan ?? '').trim().toUpperCase() || null,
        udyam: (values.udyam ?? '').trim().toUpperCase() || null,
        state: values.state || null,
        registrationType: values.registrationType,
        negativeStockPolicy: values.negativeStockPolicy,
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['company'] });
      void queryClient.invalidateQueries({ queryKey: ['company-gstins'] });
    },
  });

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
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
    >
      <Typography variant="h4">{t('nav.gst')}</Typography>
      {mutation.isSuccess ? <Alert severity="success">GST settings saved</Alert> : null}
      {mutation.isError ? <HelpErrorAlert error={mutation.error} /> : null}
      {verifyMutation.isSuccess ? (
        <Alert severity="info">
          GSTIN status: {verifyMutation.data?.status ?? 'Verified'} (
          {verifyMutation.data?.tradeName || 'Active'})
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
                  label="Primary GSTIN (15 characters)"
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
            Verify GSTIN with Portal
          </Button>
          <Controller
            name="pan"
            control={control}
            render={({ field }) => (
              <TextField
                label="PAN"
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
            Verify PAN
          </Button>
          {panVerifyMutation.isError ? (
            <HelpErrorAlert error={panVerifyMutation.error} />
          ) : null}
          <Controller
            name="udyam"
            control={control}
            render={({ field }) => (
              <TextField
                label="UDYAM"
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
            Verify UDYAM
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
                <TextField select label="GST Registration Type" {...field} value={field.value ?? 'UNREGISTERED'}>
                  <MenuItem value="REGULAR">Regular Taxpayer (Issues Tax Invoices with CGST/SGST/IGST)</MenuItem>
                  <MenuItem value="COMPOSITION">Composition Scheme (Issues Bill of Supply without Tax)</MenuItem>
                  <MenuItem value="UNREGISTERED">Unregistered / Exempt Business</MenuItem>
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
                label="Out-of-Stock Billing Policy"
                helperText="Choose whether to block billing or allow billing with a warning when stock is zero"
                {...field}
              >
                <MenuItem value="BLOCK">Block Billing (Strict: Prevent selling items with 0 stock)</MenuItem>
                <MenuItem value="WARN">Allow & Warn (Flexible: Allow counter staff to bill anyway)</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="assumeLocalStateForBlankParty"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label="Default walk-in retail customers to local state (Intra-state CGST+SGST)"
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
                label="Annual Business Turnover (₹)"
                placeholder="e.g. 50000000"
                helperText="Statutory threshold indicator. Leave blank if annual turnover is below ₹5 Crores."
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
                label="e-Invoice enabled (Mandatory for B2B turnover > ₹5 Crores)"
              />
            )}
          />
          <Controller
            name="ewayEnabled"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(_, c) => field.onChange(c)} />}
                label="e-Way Bill generation enabled"
              />
            )}
          />
          <Controller
            name="ewayThresholdAmount"
            control={control}
            render={({ field }) => (
              <TextField
                label="e-Way Threshold Amount (₹)"
                helperText="Consignment value above which e-Way bill is required (Default: ₹50,000)"
                {...field}
              />
            )}
          />
          <Typography variant="subtitle1" fontWeight={600} sx={{ pt: 1 }}>
            GSP Portal Credentials (Direct Govt Filing)
          </Typography>
          <Alert severity="info">
            Credentials are write-only and encrypted.
            {company?.gspCredentialsConfigured
              ? ' GSP credentials are currently active.'
              : ' No GSP credentials configured yet.'}
          </Alert>
          <Controller
            name="gspProvider"
            control={control}
            render={({ field }) => (
              <TextField select label="GSP Provider" {...field}>
                <MenuItem value="">None / Manual Filing</MenuItem>
                <MenuItem value="sandbox">Sandbox / Test Demo Portal</MenuItem>
                <MenuItem value="cleartax">ClearTax GSP</MenuItem>
                <MenuItem value="mastergst">MasterGST GSP</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="gspClientId"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label="Client ID"
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
                  label="Client Secret"
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
                label="Portal Username"
                autoComplete="off"
                name="gsp_portal_username"
                inputProps={{ autoComplete: 'off' }}
              />
            )}
          />
          <Button type="submit" variant="contained" size="large" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2, maxWidth: 640 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Additional Branch GSTINs</Typography>
          {(gstinsQuery.data ?? []).map((row) => (
            <Stack
              key={row.id}
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}
            >
              <Typography>
                {row.gstin} {row.legal_name ? `(${row.legal_name})` : ''}
                {(row.isActive === false || row.is_active === false) ? ' — inactive' : ''}
              </Typography>
              <Button
                size="small"
                onClick={() => {
                  void updateCompanyGstin(row.id, {
                    is_active: !(row.isActive !== false && row.is_active !== false),
                  }).then(() => queryClient.invalidateQueries({ queryKey: ['company-gstins'] }));
                }}
              >
                {(row.isActive === false || row.is_active === false) ? 'Activate' : 'Deactivate'}
              </Button>
            </Stack>
          ))}
          <TextField
            label="Branch GSTIN"
            value={branchGstin}
            onChange={(e) => setBranchGstin(e.target.value.toUpperCase())}
          />
          <TextField label="Branch Business Name" value={branchName} onChange={(e) => setBranchName(e.target.value)} />
          <StateSelect value={branchState} onChange={(val) => setBranchState(val)} label="Branch State" />
          <Button
            variant="outlined"
            disabled={!isValidGstin(branchGstin)}
            onClick={() => {
              void createCompanyGstin({
                gstin: branchGstin,
                legal_name: branchName,
                state: branchState,
                is_primary: false,
                is_active: true,
              }).then(() => {
                setBranchGstin('');
                setBranchName('');
                setBranchState('');
                void queryClient.invalidateQueries({ queryKey: ['company-gstins'] });
              });
            }}
          >
            Add Branch GSTIN
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
