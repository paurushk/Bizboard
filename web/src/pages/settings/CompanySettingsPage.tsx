import { useEffect } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { Controller, useForm } from 'react-hook-form';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { LoadingState, ErrorState } from '@/components/PageState';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import type { Company } from '@/types/domain';
import { canManageUsers } from '@/utils/permissions';

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
    mutationFn: updateCompany,
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
      {mutation.isSuccess ? <Alert severity="success">Company saved</Alert> : null}
      {mutation.isError ? <Alert severity="error">{getErrorMessage(mutation.error)}</Alert> : null}
      <Paper sx={{ p: 2, maxWidth: 640 }}>
        <Stack spacing={2}>
          {(
            [
              ['name', 'Trade / display name'],
              ['legalName', 'Legal name'],
              ['address', 'Address'],
              ['city', 'City'],
              ['state', 'State'],
              ['pincode', 'PIN'],
              ['phone', 'Phone'],
              ['email', 'Email'],
              ['upiId', 'UPI ID'],
              ['bankName', 'Bank name'],
              ['bankAccount', 'Account number'],
              ['bankIfsc', 'IFSC'],
            ] as const
          ).map(([name, label]) => (
            <Controller
              key={name}
              name={name}
              control={control}
              render={({ field }) => (
                <TextField label={label} {...field} value={field.value ?? ''} />
              )}
            />
          ))}
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
