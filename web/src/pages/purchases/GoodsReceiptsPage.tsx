import { todayIso } from '@/components/billing/lineHelpers';
import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listSuppliersPage, searchProducts } from '@/api/resources';
import {
  completeGoodsReceipt,
  createGoodsReceipt,
  listGoodsReceiptsPage,
  type GoodsReceiptLine,
} from '@/api/legacy/purchases';
import { useAuth } from '@/auth/AuthContext';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { canCreatePurchases } from '@/utils/permissions';

const PAGE_SIZE = 50;

interface DraftLine {
  product: string;
  quantityReceived: string;
  quantityAccepted: string;
  quantityRejected: string;
  unitPrice: string;
  rejectionReason: string;
}

function emptyLine(): DraftLine {
  return {
    product: '',
    quantityReceived: '1',
    quantityAccepted: '1',
    quantityRejected: '0',
    unitPrice: '',
    rejectionReason: '',
  };
}

export function GoodsReceiptsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canWrite = canCreatePurchases(user);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [supplierId, setSupplierId] = useState('');
  const [chosenNames, setChosenNames] = useState<Record<string, string>>({});
  const [receiptDate, setReceiptDate] = useState(() => todayIso());
  const [challan, setChallan] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([emptyLine()]);
  const [productQuery, setProductQuery] = useState('');

  const receipts = useQuery({
    queryKey: ['goods-receipts', page],
    queryFn: () => listGoodsReceiptsPage({ page, pageSize: PAGE_SIZE }),
  });
  const suppliers = useQuery({
    queryKey: ['suppliers-grn'],
    queryFn: () => listSuppliersPage({ pageSize: 50 }),
    enabled: canWrite,
  });
  const products = useQuery({
    queryKey: ['products-grn', productQuery],
    queryFn: () => searchProducts(productQuery.trim()),
    enabled: canWrite && productQuery.trim().length > 0,
  });

  const create = useMutation({
    mutationFn: () => {
      // Check what the form can check before posting stock: whole numbers, accepted plus rejected
      // equals received, and a price (a blank price would receive stock at zero cost).
      for (const [i, line] of lines.entries()) {
        const received = Number(line.quantityReceived || 0);
        const accepted = Number(line.quantityAccepted || 0);
        const rejected = Number(line.quantityRejected || 0);
        if (![received, accepted, rejected].every((n) => Number.isFinite(n) && n >= 0)) {
          throw new Error(t('grn.badQuantity', { line: String(i + 1) }));
        }
        if (Math.abs(accepted + rejected - received) > 0.0005) {
          throw new Error(t('grn.quantityMismatch', { line: String(i + 1) }));
        }
        if (!line.unitPrice || Number(line.unitPrice) <= 0) {
          throw new Error(t('grn.priceRequired', { line: String(i + 1) }));
        }
      }
      const items: GoodsReceiptLine[] = lines.map((line) => ({
        product: Number(line.product),
        quantityReceived: line.quantityReceived || '0',
        quantityAccepted: line.quantityAccepted || '0',
        quantityRejected: line.quantityRejected || '0',
        unitPrice: line.unitPrice || '0',
        rejectionReason: line.rejectionReason,
      }));
      return createGoodsReceipt({
        supplier: Number(supplierId),
        receiptDate,
        supplierChallanNumber: challan,
        items,
      });
    },
    onSuccess: () => {
      setError(null);
      setLines([emptyLine()]);
      setChallan('');
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const complete = useMutation({
    mutationFn: (id: number) => completeGoodsReceipt(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
      // Completing a receipt posts stock, so every stock view is stale now.
      for (const key of ['stock', 'products', 'stock-balance', 'low-stock']) void qc.invalidateQueries({ queryKey: [key] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  function patchLine(index: number, patch: Partial<DraftLine>) {
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  return (
    <Stack spacing={2}>
      <PageTitle page="goods-receipts">{t('nav.goodsReceipts')}</PageTitle>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {receipts.isError ? <Alert severity="error">{getErrorMessage(receipts.error)}</Alert> : null}

      {canWrite ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField
                select
                size="small"
                label={t('common.supplier')}
                value={supplierId}
                onChange={(e) => setSupplierId(e.target.value)}
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="">{t('common.none')}</MenuItem>
                {(suppliers.data?.results ?? []).map((supplier) => (
                  <MenuItem key={supplier.id} value={String(supplier.id)}>{supplier.name}</MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                type="date"
                label={t('common.date')}
                value={receiptDate}
                onChange={(e) => setReceiptDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                size="small"
                label={t('common.number')}
                value={challan}
                onChange={(e) => setChallan(e.target.value)}
              />
            </Stack>
            <TextField
              size="small"
              label={t('common.product')}
              value={productQuery}
              onChange={(e) => setProductQuery(e.target.value)}
              helperText={t('billing.grnGuidance')}
            />
            {lines.map((line, index) => (
              <Stack key={index} direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  select
                  size="small"
                  label={t('common.product')}
                  value={line.product}
                  onChange={(e) => {
                    const picked = (products.data ?? []).find((product) => String(product.id) === e.target.value);
                    if (picked) setChosenNames((names) => ({ ...names, [String(picked.id)]: picked.name }));
                    patchLine(index, { product: e.target.value });
                  }}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="">{t('common.none')}</MenuItem>
                  {/* Products already chosen on any line stay in the list when a new search replaces the results. */}
                  {[
                    ...(products.data ?? []).map((product) => ({ id: String(product.id), name: product.name })),
                    ...Object.entries(chosenNames)
                      .filter(([id]) => !(products.data ?? []).some((product) => String(product.id) === id))
                      .map(([id, name]) => ({ id, name })),
                  ].map((option) => (
                    <MenuItem key={option.id} value={option.id}>{option.name}</MenuItem>
                  ))}
                </TextField>
                <TextField size="small" label={t('common.qty')} value={line.quantityReceived} onChange={(e) => patchLine(index, { quantityReceived: e.target.value })} />
                <TextField size="small" label={t('billing.qtyAccepted')} value={line.quantityAccepted} onChange={(e) => patchLine(index, { quantityAccepted: e.target.value })} />
                <TextField size="small" label={t('billing.qtyRejected')} value={line.quantityRejected} onChange={(e) => patchLine(index, { quantityRejected: e.target.value })} />
                <TextField size="small" label={t('billing.unitPrice')} value={line.unitPrice} onChange={(e) => patchLine(index, { unitPrice: e.target.value })} />
                <TextField size="small" label={t('common.notes')} value={line.rejectionReason} onChange={(e) => patchLine(index, { rejectionReason: e.target.value })} />
              </Stack>
            ))}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setLines((current) => [...current, emptyLine()])}>{t('common.add')}</Button>
              <Button
                variant="contained"
                disabled={!supplierId || lines.some((line) => !line.product) || create.isPending}
                onClick={() => create.mutate()}
              >
                {t('common.save')}
              </Button>
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <Stack spacing={1}>
        {(receipts.data?.results ?? []).map((row) => (
          <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
              <strong>{row.number || `#${row.id}`}</strong>
              <span>{row.supplierName}</span>
              <span>{row.receiptDate}</span>
              <span>{row.status}</span>
              {canWrite && row.status === 'DRAFT' ? (
                <Button size="small" variant="contained" onClick={() => complete.mutate(row.id)} disabled={complete.isPending}>
                  {t('common.complete')}
                </Button>
              ) : null}
            </Stack>
          </Paper>
        ))}
        {!receipts.isLoading && (receipts.data?.results ?? []).length === 0 ? (
          <Alert severity="info">{t('nav.goodsReceipts')}</Alert>
        ) : null}
      </Stack>
      <Stack direction="row" spacing={1}>
        <Button disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>{t('common.previous')}</Button>
        <Button disabled={!receipts.data?.next} onClick={() => setPage((n) => n + 1)}>{t('common.next')}</Button>
      </Stack>
    </Stack>
  );
}
