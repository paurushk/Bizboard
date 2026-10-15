import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import type { RecurringSchedule } from '@/api/legacy/sales';
import * as api from '@/api/resources';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import type { Customer, Product } from '@/types/domain';
import {
  CADENCE_OPTIONS,
  STOP_STAGE_OPTIONS,
  buildPayload,
  emptyForm,
  formFromSchedule,
  formIsValid,
  isValidLine,
  newLine,
  templateItems,
  type LineDraft,
  type ScheduleForm,
} from './recurringHelpers';

function productLabel(p: Product): string {
  return p.sku ? `${p.name} · ${p.sku}` : p.name;
}

function LineRow({
  line,
  disabled,
  canRemove,
  cf,
  onChange,
  onRemove,
}: {
  line: LineDraft;
  cf?: Record<string, string[]>;
  disabled: boolean;
  canRemove: boolean;
  onChange: (patch: Partial<LineDraft>) => void;
  onRemove: () => void;
}) {
  const search = useProductSearch({ selected: line.product, cf });
  // Editing: the template stores only product ids, so fetch the one to show its name.
  const loaded = useQuery({
    queryKey: ['product', line.productId],
    queryFn: () => api.getProduct(Number(line.productId)),
    enabled: Boolean(line.productId) && !line.product,
  });
  useEffect(() => {
    if (loaded.data && !line.product) onChange({ product: loaded.data });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded.data]);
  const priceBad = line.price !== '' && Number(line.price) < 0;
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'flex-start' }}>
      <Autocomplete
        size="small"
        fullWidth
        disabled={disabled}
        options={search.options}
        loading={search.isFetching}
        value={line.product}
        filterOptions={(x) => x}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        getOptionLabel={productLabel}
        onInputChange={(_, value, reason) => {
          if (reason === 'input') search.setProductQuery(value);
        }}
        onChange={(_, option) => onChange({ product: option, productId: option?.id ?? null })}
        renderInput={(params) => (
          <TextField {...params} label={t('common.product')} helperText={search.helperText} />
        )}
      />
      <TextField
        size="small"
        type="number"
        label={t('common.qty')}
        value={line.qty}
        disabled={disabled}
        onChange={(e) => onChange({ qty: e.target.value })}
        inputProps={{ min: 0.001, step: 'any', inputMode: 'decimal' }}
        error={line.qty !== '' && !(Number(line.qty) > 0)}
        sx={{ width: { sm: 100 } }}
      />
      <TextField
        size="small"
        type="number"
        label={t('billing.priceShort')}
        value={line.price}
        disabled={disabled}
        placeholder={line.product ? String(line.product.sellingPrice ?? '') : undefined}
        onChange={(e) => onChange({ price: e.target.value })}
        inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
        error={priceBad}
        sx={{ width: { sm: 120 } }}
      />
      {canRemove && !disabled ? (
        <Button size="small" color="inherit" onClick={onRemove}>
          {t('recurring.removeLine')}
        </Button>
      ) : null}
    </Stack>
  );
}

export function RecurringScheduleDrawer({
  open,
  schedule,
  onClose,
  onSaved,
}: {
  open: boolean;
  schedule: RecurringSchedule | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 560 } } }}>
      {/* The form mounts on open, so it starts from the schedule being edited every time. */}
      <ScheduleFormBody schedule={schedule} onClose={onClose} onSaved={onSaved} />
    </Drawer>
  );
}

function ScheduleFormBody({
  schedule,
  onClose,
  onSaved,
}: {
  schedule: RecurringSchedule | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const managed = Boolean(schedule?.managedByContract);
  const [form, setForm] = useState<ScheduleForm>(() => (schedule ? formFromSchedule(schedule) : emptyForm()));
  const [customer, setCustomer] = useState<Customer | null>(() =>
    schedule ? ({ id: schedule.customer, name: schedule.customerName } as Customer) : null,
  );
  const [error, setError] = useState<string | null>(null);
  const cfFilters = useProductCfFilters();

  const customerSearch = useCustomerSearch({ activeOnly: true, selected: customer });
  const patch = (next: Partial<ScheduleForm>) => setForm((prev) => ({ ...prev, ...next }));
  const patchLine = (key: string, change: Partial<LineDraft>) =>
    setForm((prev) => ({
      ...prev,
      lines: prev.lines.map((l) => (l.key === key ? { ...l, ...change } : l)),
    }));

  const save = useMutation({
    mutationFn: () => {
      const payload = buildPayload(form, schedule);
      return schedule
        ? api.updateRecurringSchedule(schedule.id, payload)
        : api.createRecurringSchedule(payload);
    },
    onSuccess: () => {
      setError(null);
      onSaved();
    },
    onError: (err) => setError(getErrorMessage(err) || t('recurring.saveFailed')),
  });

  // Same engine as the invoice editor, so the figure matches what a run will create.
  const previewBody = useMemo(
    () => ({
      customer: form.customerId,
      companyGstin: schedule?.companyGstin ?? undefined,
      items: templateItems(form.lines),
      additionalCharges: Number(form.additionalCharges || 0),
      invoiceDiscount: Number(form.invoiceDiscount || 0),
      invoiceDiscountMode: schedule?.invoiceDiscountMode,
      priceMode: schedule?.priceMode,
    }),
    [form.customerId, form.lines, form.additionalCharges, form.invoiceDiscount, schedule],
  );
  const previewJson = JSON.stringify(previewBody);
  const debouncedPreview = useDebouncedValue(previewJson, 400);
  const canPreview = Boolean(form.customerId) && form.lines.some(isValidLine);
  // Wait for typing to settle: until then the debounced body is the previous one.
  const previewSettled = debouncedPreview === previewJson;
  const preview = useQuery({
    queryKey: ['recurring-preview', debouncedPreview],
    queryFn: () => api.previewSalesTotals(JSON.parse(debouncedPreview) as Record<string, unknown>),
    enabled: canPreview && previewSettled,
    retry: false,
  });

  const valid = formIsValid(form);
  const invoiceStage = form.stopStage === 'INVOICE';
  const money = (n: number | undefined) =>
    (n ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <>
      <Box component="form" onSubmit={(e) => { e.preventDefault(); if (valid && !save.isPending) save.mutate(); }} sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>
        <Typography variant="h6" component="h2">
          {schedule ? t('recurring.editSchedule') : t('recurring.newSchedule')}
        </Typography>
        {managed ? (
          <Alert severity="info">{t('recurring.managedByContractHelp')}</Alert>
        ) : null}
        {error ? <Alert severity="error">{error}</Alert> : null}

        <Stack spacing={1.5}>
          <Autocomplete
            size="small"
            disabled={managed}
            options={customerSearch.options}
            loading={customerSearch.isFetching}
            value={customer}
            filterOptions={(x) => x}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            getOptionLabel={(c) => (c.gstin ? `${c.name} (${c.gstin})` : c.name)}
            onInputChange={(_, value, reason) => {
              if (reason === 'input') customerSearch.setQuery(value);
            }}
            onChange={(_, option) => {
              setCustomer(option);
              patch({ customerId: option?.id ?? null });
            }}
            renderInput={(params) => <TextField {...params} label={t('recurring.customerPicker')} />}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <TextField select size="small" fullWidth disabled={managed} label={t('recurring.cadence')} value={form.cadence} onChange={(e) => patch({ cadence: e.target.value })}>
              {CADENCE_OPTIONS.map((c) => (
                <MenuItem key={c.value} value={c.value}>{t(c.labelKey)}</MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              fullWidth
              required
              disabled={managed}
              type="datetime-local"
              label={t('recurring.nextRun')}
              InputLabelProps={{ shrink: true }}
              value={form.nextRunAt}
              onChange={(e) => patch({ nextRunAt: e.target.value })}
            />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <TextField
              size="small"
              fullWidth
              disabled={managed}
              type="date"
              label={t('recurring.endDate')}
              InputLabelProps={{ shrink: true }}
              value={form.endDate}
              onChange={(e) => patch({ endDate: e.target.value })}
            />
            <TextField
              size="small"
              fullWidth
              disabled={managed}
              type="number"
              label={t('recurring.maxRuns')}
              helperText={t('recurring.maxRunsHelp')}
              value={form.maxRuns}
              onChange={(e) => patch({ maxRuns: e.target.value })}
              inputProps={{ min: 1, step: 1 }}
              error={form.maxRuns !== '' && !(Number(form.maxRuns) >= 1)}
            />
          </Stack>
          <TextField select size="small" disabled={managed} label={t('recurring.stopStage')} value={form.stopStage} onChange={(e) => patch({ stopStage: e.target.value })}>
            {STOP_STAGE_OPTIONS.map((s) => (
              <MenuItem key={s.value} value={s.value}>{t(s.labelKey)}</MenuItem>
            ))}
          </TextField>
          {invoiceStage ? (
            <Box>
              <FormControlLabel
                control={<Checkbox checked={form.autoComplete} onChange={(e) => patch({ autoComplete: e.target.checked })} />}
                label={t('recurring.autoComplete')}
              />
              <Typography variant="caption" color="text.secondary" display="block">
                {t('recurring.autoCompleteHelp')}
              </Typography>
              {form.autoComplete ? (
                <Alert severity="warning" sx={{ mt: 1 }}>{t('recurring.einvoiceWarning')}</Alert>
              ) : null}
            </Box>
          ) : null}
        </Stack>

        <Divider />
        <Typography variant="subtitle2" component="h3">{t('recurring.lines')}</Typography>
        {!managed ? cfFilters.filterBar : null}
        <Stack spacing={1.5}>
          {form.lines.map((line) => (
            <LineRow
              key={line.key}
              line={line}
              disabled={managed}
              canRemove={form.lines.length > 1}
              cf={cfFilters.cfFilters}
              onChange={(change) => patchLine(line.key, change)}
              onRemove={() => patch({ lines: form.lines.filter((l) => l.key !== line.key) })}
            />
          ))}
          {!managed ? (
            <Box>
              <Button size="small" onClick={() => patch({ lines: [...form.lines, newLine()] })}>
                {t('recurring.addLine')}
              </Button>
            </Box>
          ) : null}
          {!form.lines.some(isValidLine) ? (
            <Typography variant="caption" color="text.secondary">{t('recurring.needLine')}</Typography>
          ) : null}
        </Stack>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <TextField size="small" fullWidth disabled={managed} type="number" label={t('recurring.additionalCharges')} value={form.additionalCharges} onChange={(e) => patch({ additionalCharges: e.target.value })} inputProps={{ min: 0, step: 'any' }} />
          <TextField size="small" fullWidth disabled={managed} type="number" label={t('recurring.invoiceDiscount')} value={form.invoiceDiscount} onChange={(e) => patch({ invoiceDiscount: e.target.value })} inputProps={{ min: 0, step: 'any' }} />
        </Stack>
        <TextField size="small" multiline minRows={2} label={t('recurring.notes')} value={form.notes} onChange={(e) => patch({ notes: e.target.value })} />

        <Paper variant="outlined" sx={{ p: 1.5 }} aria-live="polite">
          <Typography variant="subtitle2" component="h3" gutterBottom>{t('recurring.previewTitle')}</Typography>
          {!canPreview ? (
            <Typography variant="body2" color="text.secondary">{t('recurring.previewUnavailable')}</Typography>
          ) : preview.isError ? (
            <Typography variant="body2" color="error">{t('recurring.previewFailed')}</Typography>
          ) : preview.data ? (
            <Stack spacing={0.5}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="body2">{t('recurring.previewTaxable')}</Typography>
                <Typography variant="body2">{money(preview.data.taxableTotal)}</Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="body2">{t('recurring.previewTax')}</Typography>
                <Typography variant="body2">{money(preview.data.taxTotal)}</Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="subtitle2" component="p">{t('recurring.previewTotal')}</Typography>
                <Typography variant="subtitle2" component="p">{money(preview.data.grandTotal)}</Typography>
              </Stack>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">{t('common.loading')}</Typography>
          )}
        </Paper>

        <Box sx={{ flexGrow: 1 }} />
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button onClick={onClose} disabled={save.isPending}>{t('common.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={!valid || save.isPending}>
            {t('recurring.saveTemplate')}
          </Button>
        </Stack>
      </Box>
    </>
  );
}
