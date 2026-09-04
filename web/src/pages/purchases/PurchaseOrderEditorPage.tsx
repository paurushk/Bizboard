import { useEffect, useMemo, useRef, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
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
import DeleteIcon from '@mui/icons-material/Delete';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelPurchaseOrder,
  convertPurchaseOrder,
  createPurchaseOrder,
  getCompany,
  getPurchaseOrder,
  getSupplier,
  updatePurchaseOrder,
} from '@/api/resources';
import {
  DocumentEditorShell,
  NumericField,
  SimpleTotalsPanel,
  makeLine,
  recomputeLine,
  todayIso,
  useBillingSaveFeedback,
  type DraftLine,
} from '@/components/billing';
import { ErrorState, LoadingState } from '@/components/PageState';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { StatusChip } from '@/components/StatusChip';
import { useSupplierSearch } from '@/hooks/usePartySearch';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import type { Product, PurchaseType, Supplier } from '@/types/domain';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { toNumber } from '@/utils/money';

export function PurchaseOrderEditorPage() {
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { message, error, clearFeedback, flashError, setMessage } = useBillingSaveFeedback();

  const [loaded, setLoaded] = useState(false);
  // F2-038: suppress UnsavedChangesGuard for the programmatic navigate() after
  // a deliberate save/convert/cancel — those aren't "discarding" anything.
  const skipLeaveGuard = useRef(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [supplierId, setSupplierId] = useState<number | ''>('');
  const [purchaseType, setPurchaseType] = useState<PurchaseType>('NON_GST');
  const [purchaseTypeTouched, setPurchaseTypeTouched] = useState(false);
  const [orderDate, setOrderDate] = useState(todayIso());
  const [expectedDelivery, setExpectedDelivery] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [pendingQty, setPendingQty] = useState('1');

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  useEffect(() => {
    if (isEdit || purchaseTypeTouched || !company.data) return;
    setPurchaseType(preferredInvoiceType(company.data.registrationType));
  }, [company.data, isEdit, purchaseTypeTouched]);
  // F2-025: server-searched supplier picker (was listSuppliers() pulling every
  // row into the Autocomplete) — selectedSupplierQuery keeps the already-set
  // party resolved even when it falls outside the current search results.
  const selectedSupplierQuery = useQuery({
    queryKey: ['supplier', supplierId],
    queryFn: () => getSupplier(supplierId as number),
    enabled: Boolean(supplierId),
  });
  const supplierSearch = useSupplierSearch({ selected: selectedSupplierQuery.data ?? null });
  const cf = useProductCfFilters();
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct, cf: cf.cfFilters });
  const existing = useQuery({
    queryKey: ['purchase-orders', editId],
    queryFn: () => getPurchaseOrder(editId as number),
    enabled: isEdit,
  });

  const readOnly = editingStatus != null && editingStatus !== 'DRAFT';
  const selectedSupplier =
    selectedSupplierQuery.data ?? supplierSearch.options.find((s) => s.id === Number(supplierId));
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedSupplier?.gstin || selectedSupplier?.state,
  );

  useEffect(() => {
    setLoaded(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (!existing.data || loaded) return;
    const o = existing.data;
    setEditingStatus(o.status);
    setSupplierId(o.supplier);
    setPurchaseType(o.purchaseType);
    setOrderDate(o.orderDate);
    setExpectedDelivery(o.expectedDelivery ?? '');
    setNotes(o.notes ?? '');
    setLines(
      (o.items ?? []).map((item, idx) => {
        const qty = toNumber(item.quantity);
        const unitPrice = toNumber(item.unitPrice);
        const cessRate = toNumber(item.cessRate);
        const tax = calculateLineTax({
          quantity: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate,
          intraState,
        });
        return {
          key: `edit-${item.id ?? idx}`,
          lineId: item.id,
          product: item.product,
          productName: item.productName ?? '',
          description: '',
          sku: '',
          hsnCode: '',
          unitName: 'PCS',
          batchNo: '',
          expDate: '',
          mfgDate: '',
          mrp: 0,
          quantity: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate,
          ...tax,
          discountAmount: 0,
        };
      }),
    );
    setLoaded(true);
    // F2-040: intentionally NOT keyed on intraState — see the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing.data, loaded]);

  // F2-040: the selected supplier (and so intraState) may not have resolved
  // yet at hydration time, leaving every line at zero tax; also covers switching the
  // supplier after lines already exist, which otherwise leaves them stale.
  useEffect(() => {
    if (!loaded) return;
    setLines((prev) => prev.map((line) => ({ ...recomputeLine(line, intraState), discountAmount: 0 })));
  }, [intraState, loaded]);

  const lineTaxes = useMemo(
    () =>
      lines.map((l) =>
        calculateLineTax({
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: purchaseType === 'NON_GST' ? 0 : l.gstRate,
          cessRate: purchaseType === 'NON_GST' ? 0 : l.cessRate ?? 0,
          intraState,
        }),
      ),
    [lines, intraState, purchaseType],
  );
  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((l, i) => ({
          ...l,
          gstRate: lines[i]?.gstRate ?? 0,
          cessRate: purchaseType === 'NON_GST' ? 0 : lines[i]?.cessRate ?? 0,
          intraState,
        })),
        { applyRoundOff: true },
      ),
    [lineTaxes, lines, intraState, purchaseType],
  );

  const canSave = Boolean(supplierId) && lines.length > 0;

  const addLine = () => {
    if (!pendingProduct) return;
    const qty = Math.max(1, Math.floor(Number(pendingQty)) || 1);
    setLines((prev) => [...prev, makeLine(pendingProduct, intraState, qty, 'purchasePrice')]);
    setPendingProduct(null);
    setPendingQty('1');
  };

  const buildPayload = () => ({
    supplier: Number(supplierId),
    purchaseType,
    orderDate,
    expectedDelivery: expectedDelivery || null,
    notes,
    items: lines.map((l) => ({
      ...(l.lineId != null ? { id: l.lineId } : {}),
      product: l.product,
      quantity: l.quantity,
      unitPrice: l.unitPrice,
      gstRate: purchaseType === 'NON_GST' ? 0 : l.gstRate,
      cessRate: purchaseType === 'NON_GST' ? 0 : l.cessRate ?? 0,
    })),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = buildPayload();
      return isEdit && editId ? updatePurchaseOrder(editId, payload) : createPurchaseOrder(payload);
    },
    onSuccess: (order) => {
      setMessage(t('phase1.saved'));
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
      if (!isEdit) {
        skipLeaveGuard.current = true;
        void navigate(`/purchases/orders/${order.id}`, { replace: true });
      } else {
        setEditingStatus(order.status);
      }
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const convertMutation = useMutation({
    mutationFn: () => convertPurchaseOrder(editId as number),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
      skipLeaveGuard.current = true;
      void navigate('/purchases/history');
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelPurchaseOrder(editId as number),
    onSuccess: () => {
      skipLeaveGuard.current = true;
      void navigate('/purchases/orders');
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  if (isEdit && existing.isLoading) return <LoadingState />;
  if (isEdit && existing.isError) {
    return <ErrorState message={getErrorMessage(existing.error)} error={existing.error} onRetry={() => void existing.refetch()} />;
  }

  return (
    <DocumentEditorShell
      title={t(isEdit ? 'phase1.editPurchaseOrder' : 'phase1.newPurchaseOrder')}
      primarySave={{ mode: 'save', labelKey: 'common.save' }}
      canSave={canSave}
      canComplete={canSave}
      isEdit={isEdit}
      backTo="/purchases/orders"
      message={message}
      error={error}
      saving={saveMutation.isPending}
      hideSaveAndNew
      showDraftButton={false}
      onPrimarySave={() => saveMutation.mutate()}
      extraActions={
        <>
          {editingStatus === 'DRAFT' && isEdit ? (
            <Button size="small" disabled={convertMutation.isPending} onClick={() => convertMutation.mutate()}>
              {t('common.convert')}
            </Button>
          ) : null}
          {editingStatus === 'DRAFT' && isEdit ? (
            <Button size="small" color="warning" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              {t('common.cancel')}
            </Button>
          ) : null}
          {editingStatus && editingStatus !== 'DRAFT' ? (
            <StatusChip tone={documentStatusTone(editingStatus)} labelKey={statusLabelKey(editingStatus)} />
          ) : null}
        </>
      }
    >
      <UnsavedChangesGuard when={!skipLeaveGuard.current && (lines.length > 0 || Boolean(supplierId))} />
      <Stack spacing={2}>
        <Autocomplete
          options={supplierSearch.options}
          getOptionLabel={(o: Supplier) => o.name}
          value={selectedSupplier ?? null}
          onChange={(_, v) => setSupplierId(v?.id ?? '')}
          onInputChange={(_, v) => supplierSearch.setQuery(v)}
          filterOptions={(opts) => opts}
          loading={supplierSearch.isFetching}
          disabled={readOnly}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t('billing.supplier')}
              required
              helperText={!supplierSearch.enabled ? t('common.typeToSearch') : undefined}
            />
          )}
        />
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <TextField
            select
            label={t('billing.purchaseType')}
            value={purchaseType}
            onChange={(e) => {
              setPurchaseTypeTouched(true);
              setPurchaseType(e.target.value as PurchaseType);
            }}
            disabled={readOnly}
            sx={{ minWidth: 140 }}
          >
            {company.data?.registrationType === 'REGULAR' ? <MenuItem value="GST">GST</MenuItem> : null}
            <MenuItem value="NON_GST">Non-GST</MenuItem>
          </TextField>
          <TextField type="date" label={t('common.date')} value={orderDate} onChange={(e) => setOrderDate(e.target.value)} disabled={readOnly} InputLabelProps={{ shrink: true }} />
          <TextField type="date" label={t('phase1.expectedDelivery')} value={expectedDelivery} onChange={(e) => setExpectedDelivery(e.target.value)} disabled={readOnly} InputLabelProps={{ shrink: true }} />
        </Stack>
        <TextField label={t('billing.addNotes')} value={notes} onChange={(e) => setNotes(e.target.value)} disabled={readOnly} multiline minRows={2} fullWidth />

        <Typography variant="subtitle1">{t('billing.lines')}</Typography>
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
                <TableCell align="right">{t('billing.priceShort')}</TableCell>
                <TableCell align="right">{t('billing.cess')}</TableCell>
                {!readOnly ? <TableCell /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.key}>
                  <TableCell>{l.productName}</TableCell>
                  <TableCell align="right" sx={{ minWidth: 88 }}>
                    {readOnly ? (
                      l.quantity
                    ) : (
                      <NumericField
                        value={l.quantity}
                        onValueChange={(n) =>
                          setLines((prev) =>
                            prev.map((x) =>
                              x.key === l.key
                                ? recomputeLine({ ...x, quantity: Math.max(1, n || 1) }, intraState)
                                : x,
                            ),
                          )
                        }
                        min={1}
                        emptyAs={1}
                        size="small"
                        sx={{ width: 80 }}
                      />
                    )}
                  </TableCell>
                  <TableCell align="right" sx={{ minWidth: 100 }}>
                    {readOnly ? (
                      l.unitPrice
                    ) : (
                      <NumericField
                        value={l.unitPrice}
                        onValueChange={(n) =>
                          setLines((prev) =>
                            prev.map((x) =>
                              x.key === l.key
                                ? recomputeLine({ ...x, unitPrice: Math.max(0, n) }, intraState)
                                : x,
                            ),
                          )
                        }
                        min={0}
                        emptyAs={0}
                        decimals={2}
                        size="small"
                        sx={{ width: 96 }}
                      />
                    )}
                  </TableCell>
                  <TableCell align="right" sx={{ minWidth: 88 }}>
                    {readOnly || purchaseType === 'NON_GST' ? (
                      `${l.cessRate ?? 0}%`
                    ) : (
                      <NumericField
                        value={l.cessRate ?? 0}
                        onValueChange={(n) =>
                          setLines((prev) =>
                            prev.map((x) =>
                              x.key === l.key ? recomputeLine({ ...x, cessRate: Math.max(0, n) }, intraState) : x,
                            ),
                          )
                        }
                        min={0}
                        emptyAs={0}
                        decimals={2}
                        size="small"
                        sx={{ width: 80 }}
                      />
                    )}
                  </TableCell>
                  {!readOnly ? (
                    <TableCell align="right">
                      <IconButton size="small" onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
        {!readOnly ? (
          <Stack spacing={1}>
            {cf.filterBar}
          <Stack direction="row" spacing={1} alignItems="center">
            <Autocomplete
              sx={{ flex: 1 }}
              options={productSearch.options}
              loading={productSearch.isFetching}
              filterOptions={(opts) => opts}
              inputValue={productSearch.productQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
              }}
              getOptionLabel={(o) => `${o.name} · ${o.sku}`}
              value={pendingProduct}
              onChange={(_, v) => setPendingProduct(v)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('nav.products')}
                  helperText={productSearch.helperText}
                />
              )}
            />
            <TextField type="number" label={t('billing.qty')} value={pendingQty} onChange={(e) => setPendingQty(e.target.value)} sx={{ width: 100 }} />
            <Button variant="outlined" disabled={!pendingProduct} onClick={addLine}>{t('common.add')}</Button>
          </Stack>
          </Stack>
        ) : null}
        <SimpleTotalsPanel totals={totals} />
      </Stack>
    </DocumentEditorShell>
  );
}
