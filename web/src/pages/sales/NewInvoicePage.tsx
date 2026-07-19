import { useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
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
import Alert from '@mui/material/Alert';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import {
  completeSalesInvoice,
  createSalesInvoice,
  getCompany,
  listCustomers,
  searchProducts,
} from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { t } from '@/i18n';
import type { Customer, InvoiceType, Product, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';

interface FormValues {
  customerId: number | '';
  invoiceType: InvoiceType;
}

interface DraftLine {
  key: string;
  product: number;
  productName: string;
  sku: string;
  hsnCode?: string;
  quantity: number;
  unitPrice: number;
  discountPercent: number;
  gstRate: number;
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  lineTotal: number;
}

function makeLine(product: Product, intraState: boolean, quantity = 1): DraftLine {
  const tax = calculateLineTax({
    quantity,
    unitPrice: toNumber(product.sellingPrice),
    gstRate: toNumber(product.gstRate),
    intraState,
  });
  return {
    key: `${product.id}-${Date.now()}`,
    product: product.id,
    productName: product.name,
    sku: product.sku,
    hsnCode: product.hsnCode,
    quantity,
    unitPrice: toNumber(product.sellingPrice),
    discountPercent: 0,
    gstRate: toNumber(product.gstRate),
    ...tax,
  };
}

export function NewInvoicePage() {
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [productQuery, setProductQuery] = useState('');
  const [savedInvoice, setSavedInvoice] = useState<SalesInvoice | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const products = useQuery({
    queryKey: ['product-search', productQuery],
    queryFn: () => searchProducts(productQuery),
    enabled: productQuery.length >= 1,
  });

  const { control, handleSubmit, watch } = useForm<FormValues>({
    defaultValues: {
      customerId: '',
      invoiceType: 'GST',
    },
  });

  const customerId = watch('customerId');
  const selectedCustomer = (customers.data ?? []).find((c) => c.id === customerId);
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedCustomer?.gstin || selectedCustomer?.state,
  );

  const totals = useMemo(() => {
    const taxLines = lines.map((l) =>
      calculateLineTax({
        quantity: l.quantity,
        unitPrice: l.unitPrice,
        discountPercent: l.discountPercent,
        gstRate: l.gstRate,
        intraState,
      }),
    );
    return calculateInvoiceTotals(taxLines);
  }, [lines, intraState]);

  const saveMutation = useMutation({
    mutationFn: async (complete: boolean) => {
      if (!customerId) throw new Error('Customer is required');
      const draft = await createSalesInvoice({
        customer: Number(customerId),
        invoiceType: watch('invoiceType'),
        invoiceDate: new Date().toISOString().slice(0, 10),
        items: lines.map((l) => ({
          product: l.product,
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          discountPercent: l.discountPercent,
          gstRate: l.gstRate,
        })),
      });
      if (!complete) return draft;
      return completeSalesInvoice(draft.id);
    },
    onSuccess: (invoice) => {
      setError(null);
      setSavedInvoice(invoice);
      setMessage(
        invoice.status === 'COMPLETED'
          ? `Invoice ${invoice.number ?? invoice.id} completed`
          : 'Draft saved',
      );
    },
    onError: (err) => {
      setError(getErrorMessage(err));
    },
  });

  const addProduct = (product: Product | null) => {
    if (!product) return;
    if (product.status !== 'ACTIVE') {
      setError('Cannot sell inactive product');
      return;
    }
    setLines((prev) => {
      const existing = prev.find((l) => l.product === product.id);
      if (existing) {
        return prev.map((l) => {
          if (l.product !== product.id) return l;
          const quantity = l.quantity + 1;
          const tax = calculateLineTax({
            quantity,
            unitPrice: l.unitPrice,
            discountPercent: l.discountPercent,
            gstRate: l.gstRate,
            intraState,
          });
          return { ...l, quantity, ...tax };
        });
      }
      return [...prev, makeLine(product, intraState)];
    });
    setProductQuery('');
  };

  const updateQty = (key: string, quantity: number) => {
    setLines((prev) =>
      prev.map((l) => {
        if (l.key !== key) return l;
        const qty = Math.max(0.001, quantity);
        const tax = calculateLineTax({
          quantity: qty,
          unitPrice: l.unitPrice,
          discountPercent: l.discountPercent,
          gstRate: l.gstRate,
          intraState,
        });
        return { ...l, quantity: qty, ...tax };
      }),
    );
  };

  const activeCustomers = (customers.data ?? []).filter((c) => c.status === 'ACTIVE');

  return (
    <Stack spacing={2} component="form" onSubmit={handleSubmit(() => undefined)}>
      <Typography variant="h4">{t('billing.title')}</Typography>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Controller
            name="customerId"
            control={control}
            rules={{ required: true }}
            render={({ field }) => (
              <Autocomplete<Customer>
                sx={{ flex: 1 }}
                options={activeCustomers}
                getOptionLabel={(o) => o.name}
                value={activeCustomers.find((c) => c.id === field.value) ?? null}
                onChange={(_, v) => field.onChange(v?.id ?? '')}
                renderInput={(params) => (
                  <TextField {...params} required label={t('billing.customer')} />
                )}
              />
            )}
          />
          <Controller
            name="invoiceType"
            control={control}
            render={({ field }) => (
              <TextField select label={t('billing.invoiceType')} sx={{ minWidth: 160 }} {...field}>
                <MenuItem value="GST">GST Invoice</MenuItem>
                <MenuItem value="TAX">Tax Invoice</MenuItem>
                <MenuItem value="RETAIL">Retail Invoice</MenuItem>
                <MenuItem value="NON_GST">Non-GST Invoice</MenuItem>
              </TextField>
            )}
          />
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Autocomplete<Product>
          options={(products.data ?? []).filter((p) => p.status === 'ACTIVE')}
          loading={products.isFetching}
          inputValue={productQuery}
          onInputChange={(_, v) => setProductQuery(v)}
          onChange={(_, v) => addProduct(v)}
          getOptionLabel={(o) => `${o.name} · ${o.sku}${o.barcode ? ` · ${o.barcode}` : ''}`}
          renderInput={(params) => (
            <TextField
              {...params}
              autoFocus
              label={t('billing.searchProduct')}
              helperText="Barcode, SKU, or name — Enter to add"
            />
          )}
        />
      </Paper>

      <Paper sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell width={100}>{t('billing.qty')}</TableCell>
              <TableCell align="right">{t('billing.price')}</TableCell>
              <TableCell align="right">{t('billing.tax')}</TableCell>
              <TableCell align="right">{t('common.total')}</TableCell>
              <TableCell width={56} />
            </TableRow>
          </TableHead>
          <TableBody>
            {lines.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" sx={{ py: 2 }}>
                    {t('empty.products')}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              lines.map((line) => (
                <TableRow key={line.key}>
                  <TableCell>
                    <Typography fontWeight={600}>{line.productName}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {line.sku}
                      {line.hsnCode ? ` · HSN ${line.hsnCode}` : ''}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <TextField
                      type="number"
                      size="small"
                      value={line.quantity}
                      onChange={(e) => updateQty(line.key, Number(e.target.value))}
                      inputProps={{ min: 0.001, step: 1 }}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(line.unitPrice)}</TableCell>
                  <TableCell align="right">{formatMoney(line.cgst + line.sgst + line.igst)}</TableCell>
                  <TableCell align="right">{formatMoney(line.lineTotal)}</TableCell>
                  <TableCell>
                    <IconButton
                      aria-label={t('common.remove')}
                      onClick={() => setLines((prev) => prev.filter((l) => l.key !== line.key))}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Paper>

      <Paper sx={{ p: 2, maxWidth: 420, ml: 'auto', width: '100%' }}>
        <Stack spacing={1}>
          <Row label={t('billing.subtotal')} value={formatMoney(totals.subtotal)} />
          <Row label={t('billing.tax')} value={formatMoney(totals.taxTotal)} />
          <Row label={t('billing.roundOff')} value={formatMoney(totals.roundOff)} />
          <Divider />
          <Row label={t('billing.grandTotal')} value={formatMoney(totals.grandTotal)} bold />
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              disabled={lines.length === 0 || !customerId || saveMutation.isPending}
              onClick={() => saveMutation.mutate(false)}
            >
              {t('common.draft')}
            </Button>
            <Button
              variant="contained"
              disabled={lines.length === 0 || !customerId || saveMutation.isPending}
              onClick={() => saveMutation.mutate(true)}
            >
              {t('common.complete')}
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {savedInvoice?.status === 'COMPLETED' ? (
        <PdfStatusPoller invoiceId={savedInvoice.id} />
      ) : null}
    </Stack>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
      <Typography fontWeight={bold ? 700 : 400}>{label}</Typography>
      <Typography fontWeight={bold ? 700 : 500}>{value}</Typography>
    </Box>
  );
}
