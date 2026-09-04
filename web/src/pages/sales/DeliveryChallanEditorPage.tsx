import { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
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
  cancelDeliveryChallan,
  completeDeliveryChallan,
  createDeliveryChallan,
  downloadSalesDocumentPdf,
  getDeliveryChallan,
  getSalesOrder,
  listCustomers,
  listSalesOrders,
  updateDeliveryChallan,
} from '@/api/resources';
import {
  DocumentEditorShell,
  NumericField,
  SimpleTotalsPanel,
  makeLine,
  primarySaveAction,
  printBlob,
  recomputeLine,
  todayIso,
  useBillingSaveFeedback,
  type DraftLine,
} from '@/components/billing';
import { ChallanEwayPanel } from '@/components/ChallanEwayPanel';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Customer, Product, SalesOrder } from '@/types/domain';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';
import { getCompany } from '@/api/resources';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { toNumber } from '@/utils/money';

export function DeliveryChallanEditorPage() {
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { message, error, clearFeedback, flashError, setMessage } = useBillingSaveFeedback();

  const [loaded, setLoaded] = useState(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<number | ''>('');
  const [salesOrderId, setSalesOrderId] = useState<number | ''>('');
  const [challanDate, setChallanDate] = useState(todayIso());
  const [vehicleNumber, setVehicleNumber] = useState('');
  const [transporterName, setTransporterName] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [pendingQty, setPendingQty] = useState('1');

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const cf = useProductCfFilters();
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct, cf: cf.cfFilters });
  const orders = useQuery({ queryKey: ['sales-orders'], queryFn: () => listSalesOrders() });
  const existing = useQuery({
    queryKey: ['delivery-challans', editId],
    queryFn: () => getDeliveryChallan(editId as number),
    enabled: isEdit,
  });

  const readOnly = editingStatus != null && editingStatus !== 'DRAFT';
  const selectedCustomer = customers.data?.find((c) => c.id === Number(customerId));
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedCustomer?.gstin || selectedCustomer?.state,
  );

  useEffect(() => {
    setLoaded(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (!existing.data || loaded) return;
    const c = existing.data;
    setEditingStatus(c.status);
    setCustomerId(c.customer);
    setSalesOrderId(c.salesOrder ?? '');
    setChallanDate(c.challanDate);
    setVehicleNumber(c.vehicleNumber ?? '');
    setTransporterName(c.transporterName ?? '');
    setNotes(c.notes ?? '');
    setLines(
      (c.items ?? []).map((item, idx) => {
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

  // F2-040: customers.data (and so intraState) may not have loaded yet at
  // hydration time, leaving every line at zero tax; also covers switching the
  // customer after lines already exist, which otherwise leaves them stale.
  useEffect(() => {
    if (!loaded) return;
    setLines((prev) => prev.map((line) => ({ ...recomputeLine(line, intraState), discountAmount: 0 })));
  }, [intraState, loaded]);

  const onOrderPick = async (order: SalesOrder | null) => {
    setSalesOrderId(order?.id ?? '');
    if (!order) return;
    setCustomerId(order.customer);
    // F2-022: the picker holds list-payload orders which usually omit `items`.
    // Fetch the full order before mapping, and compute intraState from the
    // order's own customer instead of the stale `intraState` closure (which is
    // still keyed to the previous customerId on this render).
    let full = order;
    if (!order.items?.length) {
      try {
        full = await getSalesOrder(order.id);
      } catch {
        full = order;
      }
    }
    const orderCustomer = customers.data?.find((c) => c.id === full.customer);
    const orderIntraState = isIntraState(
      company.data?.gstin || company.data?.state,
      orderCustomer?.gstin || orderCustomer?.state,
    );
    setLines(
      (full.items ?? []).map((item, idx) => {
        const qty = toNumber(item.quantity);
        const unitPrice = toNumber(item.unitPrice);
        const cessRate = toNumber(item.cessRate);
        const tax = calculateLineTax({
          quantity: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate,
          intraState: orderIntraState,
        });
        return {
          key: `ord-${idx}-${item.product}`,
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
  };

  const lineTaxes = useMemo(
    () =>
      lines.map((l) =>
        calculateLineTax({
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: l.gstRate,
          cessRate: l.cessRate ?? 0,
          intraState,
        }),
      ),
    [lines, intraState],
  );
  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((l, i) => ({ ...l, cessRate: lines[i]?.cessRate ?? 0, intraState })),
        { applyRoundOff: true },
      ),
    [lineTaxes, lines, intraState],
  );

  const canSave = Boolean(customerId) && lines.length > 0;
  const primarySave = primarySaveAction({ isEdit, editingStatus });

  const addLine = () => {
    if (!pendingProduct) return;
    const qty = Math.max(1, Math.floor(Number(pendingQty)) || 1);
    setLines((prev) => [...prev, makeLine(pendingProduct, intraState, qty, 'sellingPrice')]);
    setPendingProduct(null);
    setPendingQty('1');
  };

  const buildPayload = () => ({
    customer: Number(customerId),
    salesOrder: salesOrderId ? Number(salesOrderId) : null,
    challanDate,
    vehicleNumber,
    transporterName,
    notes,
    items: lines.map((l) => ({
      ...(l.lineId != null ? { id: l.lineId } : {}),
      product: l.product,
      quantity: l.quantity,
      unitPrice: l.unitPrice,
      gstRate: l.gstRate,
      cessRate: l.cessRate ?? 0,
    })),
  });

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete') => {
      const payload = buildPayload();
      let doc = isEdit && editId ? await updateDeliveryChallan(editId, payload) : await createDeliveryChallan(payload);
      if (mode === 'complete' && doc.status === 'DRAFT') {
        doc = await completeDeliveryChallan(doc.id);
      }
      return doc;
    },
    onSuccess: (doc) => {
      setMessage(t('phase1.saved'));
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
      if (!isEdit) void navigate(`/sales/delivery-challans/${doc.id}`, { replace: true });
      else setEditingStatus(doc.status);
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelDeliveryChallan(editId as number),
    onSuccess: () => void navigate('/sales/delivery-challans'),
    onError: (err) => flashError(getErrorMessage(err)),
  });

  if (isEdit && existing.isLoading) return <LoadingState />;
  if (isEdit && existing.isError) {
    return <ErrorState message={getErrorMessage(existing.error)} error={existing.error} onRetry={() => void existing.refetch()} />;
  }

  return (
    <DocumentEditorShell
      title={t(isEdit ? 'phase1.editDeliveryChallan' : 'phase1.newDeliveryChallan')}
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canSave}
      isEdit={isEdit}
      backTo="/sales/delivery-challans"
      message={message}
      error={error}
      saving={saveMutation.isPending}
      hideSaveAndNew
      showDraftButton={!readOnly}
      onPrimarySave={() => saveMutation.mutate(primarySave.mode === 'complete' ? 'complete' : 'draft')}
      onDraft={() => saveMutation.mutate('draft')}
      extraActions={
        <>
          {readOnly && editingStatus === 'COMPLETED' && isEdit ? (
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                void downloadSalesDocumentPdf('delivery-challan', editId as number)
                  .then((blob) => printBlob(blob))
                  .catch((err) => flashError(getErrorMessage(err)));
              }}
            >
              {t('billing.print')}
            </Button>
          ) : null}
          {readOnly && editingStatus === 'COMPLETED' ? (
            <Button color="warning" size="small" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              {t('phase1.cancelDocument')}
            </Button>
          ) : editingStatus && editingStatus !== 'DRAFT' ? (
            <StatusChip tone={documentStatusTone(editingStatus)} labelKey={statusLabelKey(editingStatus)} />
          ) : null}
        </>
      }
    >
      <Stack spacing={2}>
        {editingStatus === 'COMPLETED' && isEdit ? (
          <PdfStatusPoller
            documentId={editId as number}
            docType="delivery-challan"
            filenameBase={existing.data?.number ?? undefined}
          />
        ) : null}
        <Autocomplete
          options={customers.data ?? []}
          getOptionLabel={(o: Customer) => o.name}
          value={customers.data?.find((c) => c.id === Number(customerId)) ?? null}
          onChange={(_, v) => setCustomerId(v?.id ?? '')}
          disabled={readOnly}
          renderInput={(params) => <TextField {...params} label={t('billing.customer')} required />}
        />
        {!isEdit ? (
          <Autocomplete
            options={(orders.data ?? []).filter((o) => o.status === 'DRAFT')}
            getOptionLabel={(o) => `${o.number ?? o.id} · ${o.customerName ?? ''}`}
            value={(orders.data ?? []).find((o) => o.id === Number(salesOrderId)) ?? null}
            onChange={(_, v) => void onOrderPick(v)}
            disabled={readOnly}
            renderInput={(params) => <TextField {...params} label={t('phase1.optionalSalesOrder')} />}
          />
        ) : null}
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <TextField type="date" label={t('common.date')} value={challanDate} onChange={(e) => setChallanDate(e.target.value)} disabled={readOnly} InputLabelProps={{ shrink: true }} />
          <TextField label={t('phase1.vehicleNumber')} value={vehicleNumber} onChange={(e) => setVehicleNumber(e.target.value)} disabled={readOnly} />
          <TextField label={t('phase1.transporter')} value={transporterName} onChange={(e) => setTransporterName(e.target.value)} disabled={readOnly} />
        </Stack>
        <TextField label={t('billing.addNotes')} value={notes} onChange={(e) => setNotes(e.target.value)} disabled={readOnly} multiline minRows={2} fullWidth />

        <Typography variant="subtitle1">{t('billing.lines')}</Typography>
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
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
                            prev.map((x) => (x.key === l.key ? { ...x, quantity: Math.max(1, n || 1) } : x)),
                          )
                        }
                        min={1}
                        emptyAs={1}
                        size="small"
                        sx={{ width: 80 }}
                      />
                    )}
                  </TableCell>
                  <TableCell align="right" sx={{ minWidth: 88 }}>
                    {readOnly ? (
                      `${l.cessRate ?? 0}%`
                    ) : (
                      <NumericField
                        value={l.cessRate ?? 0}
                        onValueChange={(n) =>
                          setLines((prev) =>
                            prev.map((x) => (x.key === l.key ? { ...x, cessRate: Math.max(0, n) } : x)),
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
        {readOnly && editingStatus === 'COMPLETED' && existing.data ? (
          <ChallanEwayPanel
            challan={existing.data}
            onError={flashError}
            onMessage={setMessage}
          />
        ) : null}
      </Stack>
    </DocumentEditorShell>
  );
}
