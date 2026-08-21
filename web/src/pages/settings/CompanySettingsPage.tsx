import { useEffect } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { Controller, useForm } from 'react-hook-form';
import { Link as RouterLink } from 'react-router-dom';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { LoadingState, ErrorState } from '@/components/PageState';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import type { Company } from '@/types/domain';
import { isValidIfsc, isValidPincode, isValidUpiVpa } from '@/utils/gst';
import { canManageUsers } from '@/utils/permissions';

import { StateSelect } from '@/components/StateSelect';

type CompanyForm = Pick<
  Company,
  | 'name'
  | 'legalName'
  | 'address'
  | 'city'
  | 'state'
  | 'pincode'
  | 'phone'
  | 'email'
  | 'upiId'
  | 'bankName'
  | 'bankAccount'
  | 'bankIfsc'
>;

export function CompanySettingsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const { control, handleSubmit, reset } = useForm<CompanyForm>();

  useEffect(() => {
    if (query.data) {
      reset({
        name: query.data.name,
        legalName: query.data.legalName ?? '',
        address: query.data.address ?? '',
        city: query.data.city ?? '',
        state: query.data.state ?? '',
        pincode: query.data.pincode ?? '',
        phone: query.data.phone ?? '',
        email: query.data.email ?? '',
        upiId: query.data.upiId ?? '',
        bankName: query.data.bankName ?? '',
        bankAccount: query.data.bankAccount ?? '',
        bankIfsc: query.data.bankIfsc ?? '',
      });
    }
  }, [query.data, reset]);

  const mutation = useMutation({
    mutationFn: (values: CompanyForm) => {
      const pin = (values.pincode ?? '').trim();
      if (pin && !isValidPincode(pin)) {
        throw new Error('PIN code must be exactly 6 digits.');
      }
      const ifsc = (values.bankIfsc ?? '').trim().toUpperCase();
      if (ifsc && !isValidIfsc(ifsc)) {
        throw new Error('Enter a valid IFSC (e.g. HDFC0001234).');
      }
      const upi = (values.upiId ?? '').trim();
      if (upi && !isValidUpiVpa(upi)) {
        throw new Error('Enter a valid UPI ID (e.g. shopname@oksbi).');
      }
      return updateCompany({
        ...values,
        pincode: pin || values.pincode,
        bankIfsc: ifsc || values.bankIfsc,
        upiId: upi || values.upiId,
      });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['company'] }),
  });

  if (!canManageUsers(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  }

  return (
    <Stack
      spacing={2}
      component="form"
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
    >
      <Typography variant="h4">{t('nav.company')}</Typography>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip
          component={RouterLink}
          to="/settings/gst"
          clickable
          variant="outlined"
          color={query.data?.gstin ? 'success' : 'warning'}
          label={
            query.data?.gstin
              ? `GSTIN ${query.data.gstin}${
                  query.data.gstinVerificationStatus
                    ? ` · ${query.data.gstinVerificationStatus}`
                    : ''
                }`
              : 'GSTIN not set — open GST settings'
          }
        />
      </Stack>
      {mutation.isSuccess ? <Alert severity="success">Company settings saved</Alert> : null}
      {mutation.isError ? <Alert severity="error">{getErrorMessage(mutation.error)}</Alert> : null}
      <Paper sx={{ p: 3, maxWidth: 640 }}>
        <Stack spacing={2}>
          <Typography variant="h6" fontWeight={600}>
            1. Shop & Address Details
          </Typography>
          <Controller
            name="name"
            control={control}
            render={({ field }) => (
              <TextField label="Trade / Shop Display Name" {...field} value={field.value ?? ''} required />
            )}
          />
          <Controller
            name="legalName"
            control={control}
            render={({ field }) => (
              <TextField label="Legal Business Name (as on GST/PAN)" {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="address"
            control={control}
            render={({ field }) => (
              <TextField label="Shop / Billing Address" multiline minRows={2} {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="city"
            control={control}
            render={({ field }) => (
              <TextField label="City" {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="state"
            control={control}
            render={({ field }) => (
              <StateSelect value={field.value ?? ''} onChange={field.onChange} />
            )}
          />
          <Controller
            name="pincode"
            control={control}
            render={({ field }) => (
              <TextField label="PIN Code (6 digits)" {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="phone"
            control={control}
            render={({ field }) => (
              <TextField label={t('common.phone')} {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="email"
            control={control}
            render={({ field }) => (
              <TextField label={t('common.email')} {...field} value={field.value ?? ''} />
            )}
          />
        </Stack>
      </Paper>

      <Paper sx={{ p: 3, maxWidth: 640 }} id="bank-section">
        <Stack spacing={2}>
          <Typography variant="h6" fontWeight={600}>
            2. Bank Account & UPI QR (Printed on Bills)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            These payment details will appear on your printed A4/Thermal bills so customers can pay directly to your account.
          </Typography>
          <Controller
            name="upiId"
            control={control}
            render={({ field }) => (
              <TextField
                label="UPI ID / VPA (e.g. yourshop@oksbi)"
                helperText="Generates automatic dynamic QR code on bills"
                {...field}
                value={field.value ?? ''}
              />
            )}
          />
          <Controller
            name="bankName"
            control={control}
            render={({ field }) => (
              <TextField label="Bank Name (e.g. State Bank of India)" {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="bankAccount"
            control={control}
            render={({ field }) => (
              <TextField label="Bank Account Number" {...field} value={field.value ?? ''} />
            )}
          />
          <Controller
            name="bankIfsc"
            control={control}
            render={({ field }) => (
              <TextField label="Bank IFSC Code (e.g. SBIN0001234)" {...field} value={field.value ?? ''} />
            )}
          />
          <Button type="submit" variant="contained" size="large" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
