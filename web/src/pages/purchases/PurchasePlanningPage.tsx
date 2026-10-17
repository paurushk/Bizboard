import { useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';
import { getErrorCode, getErrorMessage } from '@/api/client';
import { AttemptKeys } from '@/pages/inventory/attemptKeys';
import { createPlanningDrafts, getPurchasePlan, type PlanningLine } from '@/api/osPlan';
import { listWarehouses } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { useSupplierSearch } from '@/hooks/usePartySearch';
import { t } from '@/i18n';
import {
  buildPreview,
  draftRows,
  effectiveQty,
  effectiveSupplier,
  orderedQty,
  planRowKey,
  qtyProblem,
  type SupplierPick,
} from '@/pages/inventory/planningHelpers';
import type { Supplier } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { canCreatePurchases } from '@/utils/permissions';

export function PurchasePlanningPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canDraft = canCreatePurchases(user);
  const [warehouse, setWarehouse] = useState('');
  const [supplier, setSupplier] = useState('');
  const [urgency, setUrgency] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, SupplierPick>>({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [drafts, setDrafts] = useState<Array<{ label: string; href: string }>>([]);
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  // PB-02: searched on the server, so a supplier beyond the first page can still be picked.
  const [supplierPick, setSupplierPick] = useState<Supplier | null>(null);
  const supplierSearch = useSupplierSearch({ selected: supplierPick });
  const [assignPick, setAssignPick] = useState<Supplier | null>(null);
  const assignSearch = useSupplierSearch({ selected: assignPick });
  const plan = useQuery({
    queryKey: ['purchase-plan', warehouse, supplier, urgency],
    queryFn: () => getPurchasePlan({
      warehouse: warehouse || undefined,
      supplier: supplier || undefined,
      urgency: urgency || undefined,
    }),
    retry: false,
  });
  const rows = useMemo(() => plan.data?.rows ?? [], [plan.data]);
  // Opened from Low stock: ?select=all ticks every row that can become a draft order, ?products=1,2 only those items.
  const [searchParams] = useSearchParams();
  const [preselected, setPreselected] = useState(false);
  if (!preselected && rows.length > 0) {
    setPreselected(true);
    const wanted = (searchParams.get('products') ?? '').split(',').map(Number).filter(Boolean);
    if (searchParams.get('select') === 'all' || wanted.length) {
      setSelected(
        rows
          .filter((row) => !row.transferFromWarehouseId && (wanted.length === 0 || wanted.includes(row.productId)))
          .map(planRowKey),
      );
    }
  }
  const selectedRows = useMemo(
    () => rows.filter((row) => selected.includes(planRowKey(row))),
    [rows, selected],
  );
  const [notice, setNotice] = useState('');
  const preview = useMemo(() => buildPreview(selectedRows, edits, overrides), [selectedRows, edits, overrides]);
  const willOrder = preview.groups.reduce((sum, g) => sum + g.lines, 0);

  // One key per attempt: a double click or a retry after a lost answer is one set of drafts.
  const attemptKeys = useRef(new AttemptKeys());
  const createDrafts = useMutation({
    mutationFn: (confirmDuplicate: boolean) =>
      createPlanningDrafts(draftRows(selectedRows, edits, overrides), {
        idempotencyKey: attemptKeys.current.get('drafts'),
        confirmDuplicate,
      }),
    onError: (e) => attemptKeys.current.settle('drafts', e),
    onSuccess: (result) => {
      attemptKeys.current.settle('drafts');
      setPreviewOpen(false);
      const ids = result.purchaseOrderIds ?? [];
      const waiting = result.needsSupplier?.length ?? 0;
      setNotice(
        waiting
          ? `${t('osPlan.draftsCreated', { count: ids.length })} · ${t('osPlan.needsSupplier', { count: waiting })}`
          : t('osPlan.draftsCreated', { count: ids.length }),
      );
      setSelected([]);
      void qc.invalidateQueries({ queryKey: ['purchase-plan'] });
      if (ids.length === 1) navigate(`/purchases/orders/${ids[0]}`);
      else if (ids.length > 1) navigate('/purchases/orders');
    },
  });

  const duplicateDraft = createDrafts.isError && getErrorCode(createDrafts.error) === 'duplicate_draft';

  const openTransfers = () => {
    const transfers = new Map<string, PlanningLine[]>();
    for (const row of selectedRows) {
      if (!row.transferFromWarehouseId) continue;
      const key = `${row.transferFromWarehouseId}:${row.warehouseId}`;
      transfers.set(key, [...(transfers.get(key) ?? []), row]);
    }
    const next: Array<{ label: string; href: string }> = [];
    for (const [key, lines] of transfers) {
      const [from, to] = key.split(':');
      const encoded = encodeURIComponent(JSON.stringify(lines.map((line) => ({
        productId: line.productId,
        qty: effectiveQty(line, edits),
        warehouseId: line.warehouseId,
      }))));
      next.push({
        label: `${t('osPlan.transferFrom', { name: lines[0]?.transferFromWarehouseName || from })} · ${lines.length}`,
        href: `/inventory/transfers?from=${from}&to=${to}&lines=${encoded}`,
      });
    }
    if (next.length === 1) {
      navigate(next[0].href);
      return;
    }
    setDrafts(next);
  };

  const toggle = (key: string) =>
    setSelected((prev) => (prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]));

  const assignSupplier = () => {
    if (!assignPick) return;
    const pick = { id: assignPick.id, name: assignPick.name };
    setOverrides((prev) => {
      const next = { ...prev };
      for (const row of selectedRows) if (!row.transferFromWarehouseId) next[planRowKey(row)] = pick;
      return next;
    });
  };

  // The plan needs replenishment on; say so here instead of showing a bare server error.
  const needsReplenishment = plan.isError && getErrorCode(plan.error) === 'replenishment_required';

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.purchasePlanning')}</PageTitle>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button component={RouterLink} to="/inventory/demand-forecast" size="small">
            {t('inventory.planForecastLink')}
          </Button>
          {canDraft ? (
            <>
              <Button
                variant="contained"
                disabled={selectedRows.length === 0 || selectedRows.every((row) => row.transferFromWarehouseId) || createDrafts.isPending}
                onClick={() => setPreviewOpen(true)}
              >
                {t('osPlan.openDraft')}
              </Button>
              <Button
                variant="outlined"
                disabled={!selectedRows.some((row) => row.transferFromWarehouseId)}
                onClick={openTransfers}
              >
                {t('osPlan.openTransfer')}
              </Button>
            </>
          ) : null}
        </Stack>
      </Stack>
      <Typography variant="body2" color="text.secondary">{t('osPlan.planningHelp')}</Typography>
      {notice ? <Alert severity="success" onClose={() => setNotice('')}>{notice}</Alert> : null}
      {createDrafts.isError && !duplicateDraft ? <Alert severity="error">{getErrorMessage(createDrafts.error)}</Alert> : null}
      {(plan.data?.staleDrafts?.length ?? 0) > 0 ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" component={RouterLink} to="/purchases/orders">
              {t('inventory.planStaleOpen')}
            </Button>
          }
        >
          {t('inventory.planStaleDrafts', { count: String(plan.data?.staleDrafts?.length) })}
        </Alert>
      ) : null}
      {needsReplenishment ? <Alert severity="info">{t('inventory.planNeedsReplenishment')}</Alert> : null}
      {drafts.length > 1 ? (
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {drafts.map((draft) => (
            <Button key={draft.href} variant="outlined" onClick={() => navigate(draft.href)}>{draft.label}</Button>
          ))}
        </Stack>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField select label={t('nav.warehouses')} value={warehouse} onChange={(e) => setWarehouse(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(warehouses.data ?? []).map((row) => (
            <MenuItem key={row.id} value={String(row.id)}>{row.name}</MenuItem>
          ))}
        </TextField>
        <Autocomplete
          options={supplierSearch.options}
          getOptionLabel={(option) => option.name}
          isOptionEqualToValue={(option, value) => option.id === value.id}
          filterOptions={(options) => options}
          value={supplierPick}
          onChange={(_e, value) => {
            setSupplierPick(value);
            setSupplier(value ? String(value.id) : '');
          }}
          onInputChange={(_e, value) => supplierSearch.setQuery(value)}
          loading={supplierSearch.isFetching}
          sx={{ minWidth: 220 }}
          renderInput={(params) => (
            <TextField {...params} label={t('nav.suppliers')} placeholder={t('common.all')} />
          )}
        />
        <TextField
          label={t('osPlan.urgencyDays')}
          value={urgency}
          onChange={(e) => setUrgency(e.target.value.replace(/[^\d]/g, ''))}
          sx={{ maxWidth: 160 }}
        />
      </Stack>
      {canDraft && selectedRows.some((row) => !row.transferFromWarehouseId) ? (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <Autocomplete
            options={assignSearch.options}
            getOptionLabel={(option) => option.name}
            isOptionEqualToValue={(option, value) => option.id === value.id}
            filterOptions={(options) => options}
            value={assignPick}
            onChange={(_e, value) => setAssignPick(value)}
            onInputChange={(_e, value) => assignSearch.setQuery(value)}
            loading={assignSearch.isFetching}
            sx={{ minWidth: 260 }}
            renderInput={(params) => <TextField {...params} size="small" label={t('inventory.planAssignSupplier')} />}
          />
          <Button variant="outlined" size="small" disabled={!assignPick} onClick={assignSupplier}>
            {t('inventory.planApply')}
          </Button>
        </Stack>
      ) : null}
      {plan.isLoading ? <LoadingState /> : null}
      {plan.isError && !needsReplenishment ? (
        <ErrorState message={getErrorMessage(plan.error)} error={plan.error} onRetry={() => void plan.refetch()} />
      ) : null}
      {!plan.isLoading && !plan.isError && rows.length === 0 ? (
        <EmptyState description={t('osPlan.planningEmpty')} />
      ) : null}
      {(plan.data?.coveredByOrders ?? 0) > 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('inventory.planCovered', { count: String(plan.data?.coveredByOrders) })}
        </Typography>
      ) : null}
      {rows.length > 0 ? (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>{t('supplierPrices.product')}</TableCell>
                <TableCell>{t('nav.warehouses')}</TableCell>
                <TableCell align="right">{t('inventory.planColAvailable')}</TableCell>
                <TableCell align="right">{t('inventory.planColOnOrder')}</TableCell>
                <TableCell align="right">{t('supplierPrices.qty')}</TableCell>
                <TableCell align="right">{t('osPlan.daysToStockout')}</TableCell>
                <TableCell>{t('osPlan.supply')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => {
                const key = planRowKey(row);
                const isTransfer = Boolean(row.transferFromWarehouseId);
                const bad = qtyProblem(row, edits);
                const supplierInfo = effectiveSupplier(row, overrides);
                const rounded = orderedQty(row, edits);
                const typedQty = Number(effectiveQty(row, edits));
                return (
                  <TableRow key={key} hover>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selected.includes(key)}
                        onChange={() => toggle(key)}
                        inputProps={{ 'aria-label': row.productName }}
                      />
                    </TableCell>
                    <TableCell>{row.productName}</TableCell>
                    <TableCell>
                      {row.warehouseName}
                      {row.scope === 'company' ? (
                        <Chip size="small" variant="outlined" label={t('inventory.planAllGodowns')} sx={{ ml: 1 }} />
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {row.available ?? '—'} / {row.reorderLevel ?? '—'}
                    </TableCell>
                    <TableCell align="right">{row.onOrder && Number(row.onOrder) > 0 ? row.onOrder : '—'}</TableCell>
                    <TableCell align="right">
                      <TextField
                        size="small"
                        type="number"
                        value={effectiveQty(row, edits)}
                        onChange={(e) => setEdits((prev) => ({ ...prev, [key]: e.target.value }))}
                        error={bad}
                        inputProps={{ min: 0, step: 'any', 'aria-label': `${t('supplierPrices.qty')} ${row.productName}` }}
                        helperText={
                          bad
                            ? t('inventory.transferQtyInvalid')
                            : !isTransfer && row.wholeUnitsOnly && rounded !== typedQty
                              ? t('inventory.planWholeUnits', { qty: String(rounded) })
                              : undefined
                        }
                        sx={{ width: 120 }}
                      />
                      {row.unit ? ` ${row.unit}` : ''}
                    </TableCell>
                    <TableCell align="right">{row.daysToStockout ?? '—'}</TableCell>
                    <TableCell>
                      {isTransfer ? (
                        t('osPlan.transferFrom', { name: row.transferFromWarehouseName })
                      ) : supplierInfo.id ? (
                        <>
                          {t('osPlan.purchaseFromSupplier')} · {supplierInfo.name}
                          {row.lastPrice && Number(row.lastPrice) > 0 ? ` · ${t('inventory.planLastPrice', { price: formatMoney(row.lastPrice) })}` : ''}
                        </>
                      ) : (
                        <Chip size="small" color="warning" label={t('inventory.planNoSupplier')} />
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('inventory.planPreviewTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {preview.groups.length === 0 ? <Alert severity="warning">{t('inventory.planPreviewNothing')}</Alert> : null}
            {preview.groups.map((group) => (
              <Typography key={group.supplierId}>
                {t('inventory.planPreviewSupplier', {
                  name: group.supplierName,
                  count: String(group.lines),
                  amount: formatMoney(group.estimate),
                })}
              </Typography>
            ))}
            {preview.noSupplier.length > 0 ? (
              <Alert severity="warning">
                {t('inventory.planPreviewNoSupplier', { count: String(preview.noSupplier.length) })}
              </Alert>
            ) : null}
            {preview.invalid.length > 0 ? (
              <Alert severity="warning">{t('inventory.planPreviewInvalid', { count: String(preview.invalid.length) })}</Alert>
            ) : null}
            {preview.transfers.length > 0 ? (
              <Alert severity="info">{t('inventory.planPreviewTransfers', { count: String(preview.transfers.length) })}</Alert>
            ) : null}
            {duplicateDraft ? (
              <Alert
                severity="warning"
                action={
                  <Button color="inherit" size="small" disabled={createDrafts.isPending} onClick={() => createDrafts.mutate(true)}>
                    {t('inventory.planCreateAnyway')}
                  </Button>
                }
              >
                {t('inventory.planDuplicateDraft')}
              </Alert>
            ) : null}
            <Typography variant="caption" color="text.secondary">{t('inventory.planPreviewNote')}</Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={willOrder === 0 || createDrafts.isPending} onClick={() => createDrafts.mutate(false)}>
            {t('inventory.planPreviewConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
