import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { Navigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { createStockAdjustment, listStock, listWarehouses } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { canAdjustInventory } from '@/utils/permissions';
import { toNumber } from '@/utils/money';

import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

interface FormValues {
  product: number | '';
  adjustmentType: 'ADD' | 'REDUCE';
  quantity: number;
  reasonPreset: string;
  customReason: string;
  warehouse: number | '';
}

const PRESET_REASONS = [
  { value: 'Damaged / Defective Goods', labelKey: 'adjustments.reasons.damaged' },
  { value: 'Physical Count Discrepancy', labelKey: 'adjustments.reasons.discrepancy' },
  { value: 'Theft / Lost Inventory', labelKey: 'adjustments.reasons.theft' },
  { value: 'Opening Stock Correction', labelKey: 'adjustments.reasons.opening' },
  { value: 'Customer Return / Exchange', labelKey: 'adjustments.reasons.customerReturn' },
  { value: 'Other Reason', labelKey: 'adjustments.reasons.other' },
];

export function StockAdjustmentPage() {
  const { user } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const productSearch = useProductSearch({ selected: selectedProduct, cf: cfFilters });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const stockQuery = useQuery({ queryKey: ['stock'], queryFn: () => listStock() });
  const { control, handleSubmit, reset, setValue, watch } = useForm<FormValues>({
    defaultValues: {
      product: '',
      adjustmentType: 'ADD',
      quantity: 1,
      reasonPreset: 'Physical Count Discrepancy',
      customReason: '',
      warehouse: '',
    },
  });
  const selectedWarehouseId = watch('warehouse');
  const adjustmentType = watch('adjustmentType');
  const reasonPreset = watch('reasonPreset');

  const currentStockEntry = selectedProduct
    ? (stockQuery.data ?? []).find(
        (s) =>
          Number(s.product) === Number(selectedProduct.id) &&
          (!selectedWarehouseId || Number(s.warehouse) === Number(selectedWarehouseId)),
      )
    : null;
  const currentRecordedQty = currentStockEntry ? toNumber(currentStockEntry.onHand) : 0;

  useEffect(() => {
    const defaultWarehouse = warehouses.data?.find((warehouse) => warehouse.isDefault);
    if (defaultWarehouse) setValue('warehouse', defaultWarehouse.id);
  }, [warehouses.data, setValue]);

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const mult = values.adjustmentType === 'ADD' ? 1 : -1;
      const finalDelta = mult * Math.abs(Number(values.quantity));
      const reasonText =
        values.reasonPreset === 'Other Reason' && values.customReason.trim()
          ? values.customReason.trim()
          : values.reasonPreset;

      return createStockAdjustment({
        product: Number(values.product),
        quantity: finalDelta,
        reason: reasonText,
        warehouse: values.warehouse ? Number(values.warehouse) : undefined,
      });
    },
    onSuccess: () => {
      setMessage('Stock adjustment recorded successfully');
      setError(null);
      setSelectedProduct(null);
      productSearch.setProductQuery('');
      void stockQuery.refetch();
      reset({
        product: '',
        adjustmentType: 'ADD',
        quantity: 1,
        reasonPreset: 'Physical Count Discrepancy',
        customReason: '',
        warehouse: warehouses.data?.find((w) => w.isDefault)?.id ?? '',
      });
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
      noValidate
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
    >
      <Typography variant="h4">{t('nav.stockAdjustment')}</Typography>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      <Paper sx={{ p: 2.5, maxWidth: 540 }}>
        <Stack spacing={2.5}>
          <Controller
            name="product"
            control={control}
            rules={{ required: 'Select a product' }}
            render={({ field, fieldState }) => (
              <Stack spacing={1}>
                <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
                <Autocomplete<Product>
                options={productSearch.options}
                loading={productSearch.isFetching}
                filterOptions={(opts) => opts}
                inputValue={productSearch.productQuery}
                onInputChange={(_, v, reason) => {
                  if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
                }}
                getOptionLabel={(o) => `${o.name} (${o.sku})`}
                value={selectedProduct}
                onChange={(_, v) => {
                  setSelectedProduct(v);
                  field.onChange(v?.id ?? '');
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t('nav.products')}
                    error={Boolean(fieldState.error)}
                    helperText={fieldState.error?.message || productSearch.helperText}
                  />
                )}
              />
              </Stack>
            )}
          />
          <Controller
            name="warehouse"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label={t('nav.warehouses')}
                value={field.value === '' ? '' : String(field.value)}
                onChange={(e) => field.onChange(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {(warehouses.data ?? []).filter((w) => w.isActive !== false).map((w) => (
                  <MenuItem key={w.id} value={String(w.id)}>
                    {w.name}
                    {w.isDefault ? ' (default)' : ''}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
          {selectedProduct ? (
            <Alert severity="info" sx={{ py: 0.5 }}>
              {t('adjustments.currentRecordedBalance')}:{' '}
              <strong>
                {currentRecordedQty} {selectedProduct.unitName || 'units'}
              </strong>
            </Alert>
          ) : null}

          <Stack spacing={1}>
            <Typography variant="subtitle2" color="text.secondary">
              {t('adjustments.adjustmentType')}
            </Typography>
            <Controller
              name="adjustmentType"
              control={control}
              render={({ field }) => (
                <ToggleButtonGroup
                  value={field.value}
                  exclusive
                  fullWidth
                  onChange={(_, val) => val && field.onChange(val)}
                  color="primary"
                >
                  <ToggleButton value="ADD" color="success">
                    {t('adjustments.addStock')}
                  </ToggleButton>
                  <ToggleButton value="REDUCE" color="error">
                    {t('adjustments.reduceStock')}
                  </ToggleButton>
                </ToggleButtonGroup>
              )}
            />
          </Stack>

          <Controller
            name="quantity"
            control={control}
            rules={{ validate: (v) => v > 0 }}
            render={({ field }) => (
              <TextField
                type="number"
                inputProps={{ min: 1 }}
                label={
                  adjustmentType === 'ADD'
                    ? t('adjustments.qtyToAdd')
                    : t('adjustments.qtyToReduce')
                }
                {...field}
                onChange={(e) => field.onChange(Math.max(1, Number(e.target.value)))}
              />
            )}
          />

          <Controller
            name="reasonPreset"
            control={control}
            rules={{ required: true }}
            render={({ field }) => (
              <TextField select label={t('adjustments.reasonSelect')} {...field}>
                {PRESET_REASONS.map((r) => (
                  <MenuItem key={r.value} value={r.value}>
                    {t(r.labelKey)}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />

          {reasonPreset === 'Other Reason' ? (
            <Controller
              name="customReason"
              control={control}
              rules={{ required: true }}
              render={({ field }) => (
                <TextField required label="Specify Custom Reason" {...field} />
              )}
            />
          ) : null}

          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
