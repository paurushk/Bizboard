import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { Navigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { createStockAdjustment, listProducts } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { canAdjustInventory } from '@/utils/permissions';

interface FormValues {
  product: number | '';
  quantity: number;
  reason: string;
}

export function StockAdjustmentPage() {
  const { user } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const products = useQuery({ queryKey: ['products'], queryFn: () => listProducts() });
  const { control, handleSubmit, reset } = useForm<FormValues>({
    defaultValues: { product: '', quantity: 0, reason: '' },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      createStockAdjustment({
        product: Number(values.product),
        quantity: values.quantity,
        reason: values.reason,
      }),
    onSuccess: () => {
      setMessage('Stock adjustment recorded');
      setError(null);
      reset({ product: '', quantity: 0, reason: '' });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!canAdjustInventory(user)) {
    return <Navigate to="/inventory/stock" replace />;
  }

  return (
    <Stack
      spacing={2}
      component="form"
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
    >
      <Typography variant="h4">{t('nav.stockAdjustment')}</Typography>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Paper sx={{ p: 2, maxWidth: 520 }}>
        <Stack spacing={2}>
          <Controller
            name="product"
            control={control}
            rules={{ required: true }}
            render={({ field }) => (
              <Autocomplete<Product>
                options={products.data ?? []}
                getOptionLabel={(o) => `${o.name} (${o.sku})`}
                value={(products.data ?? []).find((p) => p.id === field.value) ?? null}
                onChange={(_, v) => field.onChange(v?.id ?? '')}
                renderInput={(params) => (
                  <TextField {...params} required label={t('nav.products')} />
                )}
              />
            )}
          />
          <Controller
            name="quantity"
            control={control}
            rules={{ validate: (v) => v !== 0 }}
            render={({ field }) => (
              <TextField
                type="number"
                label="Quantity delta (+/−)"
                helperText="Positive increases stock; negative decreases"
                {...field}
                onChange={(e) => field.onChange(Number(e.target.value))}
              />
            )}
          />
          <Controller
            name="reason"
            control={control}
            rules={{ required: true }}
            render={({ field }) => <TextField required label="Reason" {...field} />}
          />
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
