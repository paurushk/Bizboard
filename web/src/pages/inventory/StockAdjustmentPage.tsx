import { useEffect, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Navigate, useSearchParams } from 'react-router-dom';
import { fefoLot } from '@/pages/inventory/fefo';
import { getErrorMessage, isDefinitiveRejection, newIdempotencyKey } from '@/api/client';
import { createStockAdjustment, getProduct, listBatches, listStock, listWarehouses } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { canAdjustInventory } from '@/utils/permissions';
import { formatMoney } from '@/utils/money';
import { adjustmentValue, currentRecordedQty, parseAdjustQty } from '@/pages/inventory/adjustmentHelpers';

import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';

interface FormValues {
  product: number | '';
  adjustmentType: 'ADD' | 'REDUCE';
  quantity: string;
  date: string;
  reasonPreset: string;
  customReason: string;
  warehouse: number | '';
  batch: number | '';
  batchNo: string;
}

const PRESET_REASONS = [
  { value: 'Damaged / Defective Goods', code: 'DAMAGED', labelKey: 'adjustments.reasons.damaged' },
  { value: 'Physical Count Discrepancy', code: 'COUNT_DIFFERENCE', labelKey: 'adjustments.reasons.discrepancy' },
  { value: 'Theft / Lost Inventory', code: 'THEFT_LOSS', labelKey: 'adjustments.reasons.theft' },
  { value: 'Opening Stock Correction', code: 'OPENING_CORRECTION', labelKey: 'adjustments.reasons.opening' },
  { value: 'Other Reason', code: 'OTHER', labelKey: 'adjustments.reasons.other' },
];

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export function StockAdjustmentPage() {
  const { ask, dialog } = useConfirmPrompt();
  const { user } = useAuth();
  const [notice, setNotice] = useState<{ severity: 'success' | 'info' | 'warning'; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const productSearch = useProductSearch({ selected: selectedProduct, cf: cfFilters });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  // INV-IDR-10: only the chosen item's balances, not the whole catalogue.
  const stockQuery = useQuery({
    queryKey: ['stock', 'adjust', selectedProduct?.id],
    queryFn: () => listStock({ productIds: [Number(selectedProduct?.id)] }),
    enabled: Boolean(selectedProduct?.id),
  });
  const [searchParams] = useSearchParams();
  const { control, handleSubmit, reset, setValue } = useForm<FormValues>({
    defaultValues: {
      product: '',
      adjustmentType: 'ADD',
      quantity: '1',
      date: todayIso(),
      reasonPreset: 'Physical Count Discrepancy',
      customReason: '',
      warehouse: '',
      batch: '',
      batchNo: '',
    },
  });
  const selectedWarehouseId = useWatch({ control, name: 'warehouse' });
  const adjustmentType = useWatch({ control, name: 'adjustmentType' });
  const selectedBatchId = useWatch({ control, name: 'batch' });
  const enteredBatchNo = useWatch({ control, name: 'batchNo' });
  // A reduction can only take from lots that have stock in the chosen godown.
  const lotWarehouse = adjustmentType === 'REDUCE' && selectedWarehouseId !== '' ? Number(selectedWarehouseId) : undefined;
  const batchesQuery = useQuery({
    queryKey: ['batches', selectedProduct?.id, lotWarehouse ?? null],
    queryFn: () => listBatches(selectedProduct?.id, lotWarehouse),
    enabled: Boolean(selectedProduct?.trackBatch),
  });
  // Default a reduction to the lot that expires first (the user can still choose another).
  const firstLot = adjustmentType === 'REDUCE' ? fefoLot(batchesQuery.data ?? []) : null;
  useEffect(() => {
    if (firstLot && selectedBatchId === '' && !String(enteredBatchNo ?? '').trim()) setValue('batch', firstLot.id);
  }, [firstLot, selectedBatchId, enteredBatchNo, setValue]);

  const warehouseSeeded = useRef(false);
  // Opened from a Current stock row: ?product=&warehouse=&type=
  const prefilled = useRef(false);
  useEffect(() => {
    if (prefilled.current) return;
    const productId = Number(searchParams.get('product'));
    if (!productId) return;
    prefilled.current = true;
    const warehouse = Number(searchParams.get('warehouse'));
    if (warehouse) {
      setValue('warehouse', warehouse);
      warehouseSeeded.current = true;
    }
    if (searchParams.get('type') === 'REDUCE') setValue('adjustmentType', 'REDUCE');
    void getProduct(productId).then((product) => {
      setSelectedProduct(product);
      setValue('product', product.id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const enteredQty = parseAdjustQty(String(useWatch({ control, name: 'quantity' }) ?? '')) ?? 0;
  const reasonPreset = useWatch({ control, name: 'reasonPreset' });

  // The balance this adjustment acts on: the chosen lot, or every lot of the item in the godown.
  const currentRecordedQtyNum = selectedProduct
    ? currentRecordedQty(
        stockQuery.data ?? [],
        selectedProduct.id,
        selectedWarehouseId === '' ? null : Number(selectedWarehouseId),
        selectedBatchId === '' ? null : Number(selectedBatchId),
        (id) => batchesQuery.data?.find((lot) => Number(lot.id) === id)?.batchNo,
      )
    : 0;
  // F3-064: show the resulting balance live and warn when it would go negative.
  const projectedQty =
    currentRecordedQtyNum + (adjustmentType === 'ADD' ? enteredQty : -enteredQty);
  const movementValue = selectedProduct ? adjustmentValue(enteredQty, selectedProduct.purchasePrice) : 0;

  // One key per form fill: a retry after a lost response is the same adjustment, not a second one.
  const idempotencyKey = useRef(newIdempotencyKey());

  useEffect(() => {
    // F3-014: seed the default godown ONCE — re-forcing it whenever
    // warehouses.data re-resolves discards a manually chosen warehouse.
    if (warehouseSeeded.current) return;
    const defaultWarehouse = warehouses.data?.find((warehouse) => warehouse.isDefault);
    if (defaultWarehouse) {
      setValue('warehouse', defaultWarehouse.id);
      warehouseSeeded.current = true;
    }
  }, [warehouses.data, setValue]);

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const mult = values.adjustmentType === 'ADD' ? 1 : -1;
      const finalDelta = mult * (parseAdjustQty(values.quantity) ?? 0);
      const reasonText =
        values.reasonPreset === 'Other Reason' && values.customReason.trim()
          ? values.customReason.trim()
          : values.reasonPreset;

      return createStockAdjustment({
        product: Number(values.product),
        quantity: finalDelta,
        reason: reasonText,
        reasonCode: PRESET_REASONS.find((r) => r.value === values.reasonPreset)?.code,
        warehouse: values.warehouse ? Number(values.warehouse) : undefined,
        batch: values.batch ? Number(values.batch) : undefined,
        batchNo: values.batchNo.trim() || undefined,
        date: values.date || undefined,
      }, { idempotencyKey: idempotencyKey.current });
    },
    onSuccess: (result) => {
      idempotencyKey.current = newIdempotencyKey();
      if (result.status === 'PENDING') {
        // Nothing has moved yet: a second approver has to accept it first.
        setNotice({ severity: 'info', text: t('adjustments.pendingApproval') });
      } else if (result.warnings?.length) {
        setNotice({ severity: 'warning', text: `${t('adjustments.recorded')} ${result.warnings.join(' ')}` });
      } else {
        setNotice({ severity: 'success', text: t('adjustments.recorded') });
      }
      setError(null);
      setSelectedProduct(null);
      productSearch.setProductQuery('');
      void stockQuery.refetch();
      reset({
        product: '',
        adjustmentType: 'ADD',
        quantity: '1',
        date: todayIso(),
        reasonPreset: 'Physical Count Discrepancy',
        customReason: '',
        warehouse: warehouses.data?.find((w) => w.isDefault)?.id ?? '',
        batch: '',
        batchNo: '',
      });
    },
    onError: (err) => {
      // INV-IDR-01: a refusal means nothing posted. The corrected form is a new request and needs
      // a new key; reusing the old one replays the refusal (or is rejected as a different body).
      // A lost response keeps the key, so a retry cannot post the adjustment twice.
      if (isDefinitiveRejection(err)) idempotencyKey.current = newIdempotencyKey();
      setError(getErrorMessage(err));
    },
  });

  if (!canAdjustInventory(user)) {
    return <Navigate to="/inventory/stock" replace />;
  }

  return (
    <Stack
      spacing={2}
      component="form"
      noValidate
      onSubmit={handleSubmit(async (values) => {
        // F3-064: a REDUCE (shrinkage / theft / write-off) is destructive and
        // irreversible without a counter-adjustment — confirm it, and spell out
        // a resulting negative balance.
        if (values.adjustmentType === 'REDUCE') {
          const q = parseAdjustQty(values.quantity) ?? 0;
          const after = currentRecordedQtyNum - q;
          const warn =
            after < 0
              ? t('inventory.adjustReduceNegative', { qty: String(q), after: String(after) })
              : t('inventory.adjustReduceConfirm', { qty: String(q), before: String(currentRecordedQtyNum), after: String(after) });
          if (!(await ask([warn]))) return;
        }
        mutation.mutate(values);
      })}
    >
      <PageTitle>{t('nav.stockAdjustment')}</PageTitle>
      {notice ? (
        <Alert severity={notice.severity} onClose={() => setNotice(null)}>
          {notice.text}
        </Alert>
      ) : null}
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
                  if (reason === 'input' || reason === 'clear' || reason === 'reset') productSearch.setProductQuery(v);
                }}
                getOptionLabel={(o) => `${o.name} (${o.sku})`}
                value={selectedProduct}
                onChange={(_, v) => {
                  setSelectedProduct(v);
                  field.onChange(v?.id ?? '');
                  setValue('batch', '');
                  setValue('batchNo', '');
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
            <Alert
              severity={enteredQty > 0 && projectedQty < 0 ? 'warning' : 'info'}
              sx={{ py: 0.5 }}
            >
              {t('adjustments.currentRecordedBalance')}:{' '}
              <strong>
                {currentRecordedQtyNum} {selectedProduct.unitName || 'units'}
              </strong>
              {enteredQty > 0 ? (
                <>
                  {' → '}
                  <strong>{projectedQty}</strong>
                  {projectedQty < 0 ? ' (would go negative)' : ''}
                  {movementValue > 0 ? ` · ${t('adjustments.value')} ${formatMoney(movementValue)}` : ''}
                </>
              ) : null}
            </Alert>
          ) : null}

          {selectedProduct?.trackBatch ? (
            <Stack spacing={1.5}>
              <Controller
                name="batch"
                control={control}
                rules={{
                  validate: (v, values) => {
                    if (!selectedProduct?.trackBatch) return true;
                    if (values.adjustmentType === 'REDUCE') {
                      return Boolean(v) || t('adjustments.reduceNeedsExisting');
                    }
                    return (
                      Boolean(v) ||
                      Boolean(values.batchNo.trim()) ||
                      t('adjustments.requireBatch')
                    );
                  },
                }}
                render={({ field, fieldState }) => (
                  <TextField
                    select
                    label={t('adjustments.existingBatch')}
                    value={field.value === '' ? '' : String(field.value)}
                    onChange={(e) => {
                      const next = e.target.value === '' ? '' : Number(e.target.value);
                      field.onChange(next);
                      if (next !== '') setValue('batchNo', '');
                    }}
                    error={Boolean(fieldState.error)}
                    helperText={fieldState.error?.message || t('adjustments.requireBatch')}
                  >
                    <MenuItem value="">
                      {adjustmentType === 'REDUCE'
                        ? t('adjustments.reduceNeedsExisting')
                        : t('adjustments.newBatchBelow')}
                    </MenuItem>
                    {(batchesQuery.data ?? []).map((lot) => (
                      <MenuItem key={lot.id} value={String(lot.id)}>
                        {lot.batchNo}
                        {lot.expiryDate ? ` · exp ${lot.expiryDate}` : ''}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
              {adjustmentType === 'ADD' ? (
              <Controller
                name="batchNo"
                control={control}
                render={({ field }) => (
                  <TextField
                    label={t('adjustments.newBatchNo')}
                    value={field.value}
                    onChange={(e) => {
                      field.onChange(e.target.value);
                      if (e.target.value.trim()) setValue('batch', '');
                    }}
                    helperText={t('adjustments.newBatchHint')}
                    disabled={Boolean(selectedBatchId)}
                  />
                )}
              />
              ) : null}
            </Stack>
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
                  onChange={(_, val) => {
                    if (!val) return;
                    field.onChange(val);
                    if (val === 'REDUCE') setValue('batchNo', '');
                  }}
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
            rules={{ validate: (v) => parseAdjustQty(String(v)) !== null || t('adjustments.qtyInvalid') }}
            render={({ field, fieldState }) => (
              <TextField
                type="number"
                inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
                label={
                  adjustmentType === 'ADD'
                    ? t('adjustments.qtyToAdd')
                    : t('adjustments.qtyToReduce')
                }
                error={Boolean(fieldState.error)}
                helperText={fieldState.error?.message}
                {...field}
              />
            )}
          />

          <Controller
            name="date"
            control={control}
            render={({ field }) => (
              <TextField
                type="date"
                label={t('adjustments.date')}
                InputLabelProps={{ shrink: true }}
                inputProps={{ max: todayIso() }}
                {...field}
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

          <Typography variant="caption" color="text.secondary">
            {t('adjustments.returnHint')}
          </Typography>

          {reasonPreset === 'Other Reason' ? (
            <Controller
              name="customReason"
              control={control}
              rules={{ required: true }}
              render={({ field }) => (
                <TextField required label={t('sweep.customReason')} {...field} />
              )}
            />
          ) : null}

          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
      {dialog}
    </Stack>
  );
}
