import { useEffect, useMemo, useRef, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelSalesOrder,
  convertSalesOrder,
  convertSalesOrderToChallan,
  createSalesOrder,
  getCompany,
  getCustomer,
  getProduct,
  getSalesOrder,
  updateSalesOrder,
} from '@/api/resources';
import { checkSalesOrderGate, confirmSalesOrder, type GateCheck } from '@/api/osPlan';
import { listEmployeesPage } from '@/api/payroll';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
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
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import type { Customer, InvoiceType, Product } from '@/types/domain';
import { formatMoney, expectedProfitAmount, toNumber } from '@/utils/money';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { firstCompleteDisabledReason } from '@/completeGates/completeBlockers';

export function SalesOrderEditorPage() {
  useFeatureFlagEpoch();
  const [searchParams] = useSearchParams();
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
  const prefillDone = useRef(false);
  const [gate, setGate] = useState<GateCheck | null>(null);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<number | ''>('');
  const [invoiceType, setInvoiceType] = useState<InvoiceType>('NON_GST');
  const [invoiceTypeTouched, setInvoiceTypeTouched] = useState(false);
  const [orderDate, setOrderDate] = useState(todayIso());
  const [expectedDelivery, setExpectedDelivery] = useState('');
  const [salesman, setSalesman] = useState<number | ''>('');
  const [salesChannel, setSalesChannel] = useState('');
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [paymentTermsDays, setPaymentTermsDays] = useState(0);
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [pendingQty, setPendingQty] = useState('1');

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const employees = useQuery({ queryKey: ['employees-mini'], queryFn: async () => (await listEmployeesPage({ pageSize: 100 })).results });
  useEffect(() => {
    if (isEdit || invoiceTypeTouched || !company.data) return;
    setInvoiceType(preferredInvoiceType(company.data.registrationType));
  }, [company.data, isEdit, invoiceTypeTouched]);
  // F2-025: server-searched customer picker (was listCustomers() pulling every
  // row into the Autocomplete) — selectedCustomerQuery keeps the already-set
  // party resolved even when it falls outside the current search results.
  const selectedCustomerQuery = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: Boolean(customerId),
  });
  const customerSearch = useCustomerSearch({ selected: selectedCustomerQuery.data ?? null });
  const cf = useProductCfFilters();
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct, cf: cf.cfFilters });
  const existing = useQuery({
    queryKey: ['sales-orders', editId],
    queryFn: () => getSalesOrder(editId as number),
    enabled: isEdit,
  });

  const readOnly = editingStatus != null && editingStatus !== 'DRAFT';
  const selectedCustomer =
    selectedCustomerQuery.data ?? customerSearch.options.find((c) => c.id === Number(customerId));
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedCustomer?.gstin || selectedCustomer?.state,
  );

  useEffect(() => {
    setLoaded(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (isEdit || prefillDone.current || !company.data) return;
    const customerParam = Number(searchParams.get('customer') || '');
    const productParam = Number(searchParams.get('product') || '');
    const wantsCustomer = Number.isFinite(customerParam) && customerParam > 0;
    const wantsProduct = Number.isFinite(productParam) && productParam > 0;
    if (!wantsCustomer && !wantsProduct) {
      prefillDone.current = true;
      return;
    }
    if (wantsCustomer && customerId !== customerParam) {
      setCustomerId(customerParam);
      return;
    }
    if (wantsCustomer && !selectedCustomer) return;
    if (!wantsProduct || lines.length > 0) {
      prefillDone.current = true;
      return;
    }
    let cancelled = false;
    void getProduct(productParam).then((product) => {
      if (cancelled || prefillDone.current) return;
      const intra = isIntraState(
        company.data?.gstin || company.data?.state,
        selectedCustomer?.gstin || selectedCustomer?.state,
      );
      setLines([makeLine(product, intra, 1, 'sellingPrice')]);
      prefillDone.current = true;
    }).catch(() => {
      prefillDone.current = true;
    });
    return () => {
      cancelled = true;
    };
  }, [isEdit, company.data, searchParams, customerId, selectedCustomer, lines.length]);

  useEffect(() => {
    if (!existing.data || loaded) return;
    const o = existing.data;
    setEditingStatus(o.status);
    setCustomerId(o.customer);
    setInvoiceType(o.invoiceType);
    setOrderDate(o.orderDate);
    setExpectedDelivery(o.expectedDelivery ?? '');
    setPaymentTermsDays(o.paymentTermsDays ?? 0);
    setNotes(o.notes ?? '');
    setSalesman((o as { salesman?: number }).salesman ?? '');
    setSalesChannel((o as { salesChannel?: string }).salesChannel ?? '');
    setDeliveryAddress((o as { deliveryAddress?: string }).deliveryAddress ?? '');
    setLines(
      (o.items ?? []).map((item, idx) => {
        const qty = toNumber(item.quantity);
        const unitPrice = toNumber(item.unitPrice);
        const cessRate = toNumber(item.cessRate);
        const tax = calculateLineTax({
          quantity: qty,
          unitPrice,
          discountPercent: toNumber(item.discountPercent),
          gstRate: toNumber(item.gstRate),
          cessRate,
          intraState,
        });
        return {
          key: `edit-${item.id ?? idx}`,
          lineId: item.id,
          product: item.product,
          productName: item.productName ?? '',
          description: item.description ?? '',
          sku: '',
          hsnCode: item.hsnCode ?? '',
          unitName: item.unitName ?? 'PCS',
          batchNo: '',
          expDate: '',
          mfgDate: '',
          mrp: 0,
          quantity: qty,
          unitPrice,
          expectedPrice: toNumber((item as { expectedPrice?: string | number }).expectedPrice),
          gstRate: toNumber(item.gstRate),
          cessRate,
          ...tax,
          discountAmount: 0,
        };
      }),
    );
    setLoaded(true);
    // F2-040: intentionally NOT keyed on intraState — see the effect below,
    // which re-derives tax once intraState is known/changes instead of
    // re-running this whole hydration (which would clobber in-progress edits).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing.data, loaded]);

  // F2-040: on first hydration, the selected customer (and so intraState) may
  // not have resolved yet, so the mapping above computed zero tax for every line.
  // Also covers switching the customer after lines are already on the order —
  // nothing else re-taxes existing lines when intraState changes.
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
          discountPercent: l.discountPercent,
          gstRate: invoiceType === 'NON_GST' ? 0 : l.gstRate,
          cessRate: invoiceType === 'NON_GST' ? 0 : l.cessRate ?? 0,
          intraState,
        }),
      ),
    [lines, intraState, invoiceType],
  );

  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((l, i) => ({
          ...l,
          gstRate: lines[i]?.gstRate ?? 0,
          cessRate: invoiceType === 'NON_GST' ? 0 : lines[i]?.cessRate ?? 0,
          intraState,
        })),
        { applyRoundOff: true },
      ),
    [lineTaxes, lines, intraState, invoiceType],
  );

  const zeroQty = lines.some((l) => Number(l.quantity) <= 0);
  const canSaveBase = Boolean(customerId) && lines.length > 0;
  const canSave = canSaveBase && !zeroQty;
  const completeDisabledReason = firstCompleteDisabledReason({ canSave: canSaveBase, zeroQty });

  const addLine = () => {
    if (!pendingProduct) return;
    const qty = Math.max(1, Math.floor(Number(pendingQty)) || 1);
    setLines((prev) => [...prev, makeLine(pendingProduct, intraState, qty, 'sellingPrice')]);
    setPendingProduct(null);
    setPendingQty('1');
  };

  const buildPayload = () => ({
    customer: Number(customerId),
    invoiceType,
    orderDate,
    expectedDelivery: expectedDelivery || null,
    paymentTermsDays,
    notes,
    salesman: salesman || null,
    salesChannel,
    deliveryAddress,
    items: lines.map((l) => ({
      ...(l.lineId != null ? { id: l.lineId } : {}),
      product: l.product,
      quantity: l.quantity,
      unitPrice: l.unitPrice,
      discountPercent: l.discountPercent,
      gstRate: invoiceType === 'NON_GST' ? 0 : l.gstRate,
      cessRate: invoiceType === 'NON_GST' ? 0 : l.cessRate ?? 0,
      expectedPrice: l.expectedPrice ?? 0,
    })),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = buildPayload();
      return isEdit && editId ? updateSalesOrder(editId, payload) : createSalesOrder(payload);
    },
    onSuccess: (order) => {
      setMessage(t('phase1.saved'));
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      if (!isEdit) {
        skipLeaveGuard.current = true;
        void navigate(`/sales/orders/${order.id}`, { replace: true });
      } else {
        setEditingStatus(order.status);
      }
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const confirmMutation = useMutation({
    mutationFn: () => confirmSalesOrder(editId as number),
    onSuccess: () => {
      setGate(null);
      setEditingStatus('CONFIRMED');
      setMessage(t('osPlan.confirmOrder'));
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void qc.invalidateQueries({ queryKey: ['sales-order', editId] });
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const convertMutation = useMutation({
    mutationFn: () => convertSalesOrder(editId as number),
    onSuccess: (inv) => {
      setMessage(t('phase1.convertedToInvoice', { id: String(inv.id) }));
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void qc.invalidateQueries({ queryKey: ['sales-order', editId] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      void qc.invalidateQueries({ queryKey: ['stock-balance'] });
      void qc.invalidateQueries({ queryKey: ['products'] });
      skipLeaveGuard.current = true;
      void navigate('/sales/history');
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const convertToChallanMutation = useMutation({
    mutationFn: () => convertSalesOrderToChallan(editId as number),
    onSuccess: (challan) => {
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void qc.invalidateQueries({ queryKey: ['sales-order', editId] });
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
      skipLeaveGuard.current = true;
      void navigate(`/sales/delivery-challans/${challan.id}`);
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSalesOrder(editId as number),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void qc.invalidateQueries({ queryKey: ['sales-order', editId] });
      void qc.invalidateQueries({ queryKey: ['stock-balance'] });
      void qc.invalidateQueries({ queryKey: ['products'] });
      skipLeaveGuard.current = true;
      void navigate('/sales/orders');
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  if (isEdit && existing.isLoading) return <LoadingState />;
  if (isEdit && existing.isError) {
    return <ErrorState message={getErrorMessage(existing.error)} error={existing.error} onRetry={() => void existing.refetch()} />;
  }

  return (
    <DocumentEditorShell
      title={t(isEdit ? 'phase1.editSalesOrder' : 'phase1.newSalesOrder')}
      primarySave={{ mode: 'save', labelKey: 'common.save' }}
      canSave={canSave}
      canComplete={canSave}
      primaryDisabledReason={completeDisabledReason}
      warning={completeDisabledReason && canSaveBase && !canSave ? completeDisabledReason : null}
      isEdit={isEdit}
      backTo="/sales/orders"
      message={message}
      error={error}
      saving={saveMutation.isPending}
      hideSaveAndNew
      showDraftButton={false}
      onPrimarySave={() => saveMutation.mutate()}
      extraActions={
        <>
          {isEdit && editingStatus === 'DRAFT' && isRuntimeFlagEnabled('ENABLE_ORDER_GATES') ? (
            <Button
              size="small"
              variant="contained"
              disabled={confirmMutation.isPending || saveMutation.isPending}
              onClick={() => {
                saveMutation.mutate(undefined, {
                  onSuccess: () => {
                    void checkSalesOrderGate(editId as number).then(setGate).catch((err) => flashError(getErrorMessage(err)));
                  },
                });
              }}
            >
              {t('osPlan.confirmOrder')}
            </Button>
          ) : null}
          {isEdit && (isRuntimeFlagEnabled('ENABLE_ORDER_GATES') ? editingStatus === 'CONFIRMED' : editingStatus === 'DRAFT') ? (
            <Button
              size="small"
              variant="outlined"
              disabled={convertToChallanMutation.isPending || convertMutation.isPending}
              onClick={() => convertToChallanMutation.mutate()}
            >
              {t('phase1.toChallan')}
            </Button>
          ) : null}
          {isEdit && (isRuntimeFlagEnabled('ENABLE_ORDER_GATES') ? editingStatus === 'CONFIRMED' : editingStatus === 'DRAFT') ? (
            <Button size="small" disabled={convertMutation.isPending || convertToChallanMutation.isPending} onClick={() => convertMutation.mutate()}>
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
      {/* F2-038: same coarse "any line or party selected" heuristic NewInvoicePage/
          NewPurchasePage already use — deliberately fires on opening an existing
          order too, not just fresh edits (matches that established behavior). */}
      <Dialog open={gate !== null} onClose={() => setGate(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('osPlan.confirmOrderTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1}>
            <Typography variant="body2">{t('osPlan.confirmOrderBody')}</Typography>
            {gate?.creditBlocked ? <Typography color="error">{gate.creditMessage || t('osPlan.creditBlocked')}</Typography> : null}
            {(gate?.marginWarnings ?? []).map((warning) => (
              <Typography key={warning.productId} variant="body2">
                {t('osPlan.marginWarning', { name: warning.productName, margin: warning.margin })}
              </Typography>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGate(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!gate || gate.creditBlocked || confirmMutation.isPending} onClick={() => confirmMutation.mutate()}>
            {t('osPlan.continueConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
      <UnsavedChangesGuard when={!skipLeaveGuard.current && (lines.length > 0 || Boolean(customerId))} />
      <Stack spacing={2}>
        <Autocomplete
          options={customerSearch.options}
          getOptionLabel={(o: Customer) => o.name}
          value={selectedCustomer ?? null}
          onChange={(_, v) => {
            setCustomerId(v?.id ?? '');
            if (v && !deliveryAddress) setDeliveryAddress(v.shippingAddress ?? '');
          }}
          onInputChange={(_, v) => customerSearch.setQuery(v)}
          filterOptions={(opts) => opts}
          loading={customerSearch.isFetching}
          disabled={readOnly}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t('billing.customer')}
              required
              helperText={!customerSearch.enabled ? t('common.typeToSearch') : undefined}
            />
          )}
        />
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <TextField
            select
            label={t('billing.invoiceType')}
            value={invoiceType}
            onChange={(e) => {
              setInvoiceTypeTouched(true);
              setInvoiceType(e.target.value as InvoiceType);
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
        <TextField
          select
          label={t('billing.salesman')}
          value={salesman}
          onChange={(e) => setSalesman(e.target.value ? Number(e.target.value) : '')}
          disabled={readOnly}
        >
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(employees.data ?? []).map((emp) => (
            <MenuItem key={emp.id} value={emp.id}>{emp.name}</MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label={t('billing.salesChannel')}
          value={salesChannel}
          onChange={(e) => setSalesChannel(e.target.value)}
          disabled={readOnly}
        >
          <MenuItem value="">{t('common.all')}</MenuItem>
          <MenuItem value="WALK_IN">{t('billing.channelWalkIn')}</MenuItem>
          <MenuItem value="ONLINE">{t('billing.channelOnline')}</MenuItem>
          <MenuItem value="DISTRIBUTOR">{t('billing.channelDistributor')}</MenuItem>
        </TextField>
        <TextField
          label={t('billing.deliveryAddress')}
          value={deliveryAddress}
          onChange={(e) => setDeliveryAddress(e.target.value)}
          disabled={readOnly}
          multiline
          minRows={2}
        />
        {expectedProfitAmount(existing.data?.expectedProfit) != null ? (
          <Typography variant="body2" color="text.secondary">
            {t('billing.expectedProfit')}: {formatMoney(expectedProfitAmount(existing.data?.expectedProfit))}
          </Typography>
        ) : null}
        <TextField label={t('billing.addNotes')} value={notes} onChange={(e) => setNotes(e.target.value)} disabled={readOnly} multiline minRows={2} fullWidth />

        <Typography variant="subtitle1">{t('billing.lines')}</Typography>
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
                <TableCell align="right">{t('billing.priceShort')}</TableCell>
                <TableCell align="right">{t('billing.expectedPrice')}</TableCell>
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
                                ? recomputeLine({ ...x, quantity: Math.max(0, n || 0) }, intraState)
                                : x,
                            ),
                          )
                        }
                        min={0}
                        emptyAs={0}
                        size="small"
                        inputProps={{ 'aria-label': t('billing.qty') }}
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
                  <TableCell align="right" sx={{ minWidth: 100 }}>
                    {readOnly ? (
                      l.expectedPrice ?? 0
                    ) : (
                      <NumericField
                        value={l.expectedPrice ?? 0}
                        onValueChange={(n) =>
                          setLines((prev) =>
                            prev.map((x) => (x.key === l.key ? { ...x, expectedPrice: Math.max(0, n) } : x)),
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
                    {readOnly || invoiceType === 'NON_GST' ? (
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
                if (reason === 'input' || reason === 'clear' || reason === 'reset') productSearch.setProductQuery(v);
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
            <TextField type="number" label={t('billing.qty')} value={pendingQty} onChange={(e) => setPendingQty(e.target.value)} sx={{ width: 100 }} inputProps={{ min: 1 }} />
            <Button variant="outlined" disabled={!pendingProduct} onClick={addLine}>{t('common.add')}</Button>
          </Stack>
          </Stack>
        ) : null}

        <SimpleTotalsPanel totals={totals} />
      </Stack>
    </DocumentEditorShell>
  );
}
