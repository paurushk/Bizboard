import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
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
import { useMutation, useQuery } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { getErrorMessage } from '@/api/client';
import {
  completePurchase,
  createPurchase,
  getCompany,
  listSuppliers,
  searchProducts,
} from '@/api/resources';
import { t } from '@/i18n';
import type { Product, PurchaseType, Supplier } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';

interface FormValues {
  supplierId: number | '';
  purchaseType: PurchaseType;
  invoiceDate: string;
  supplierBillNumber: string;
}

interface DraftLine {
  key: string;
  product: number;
  productName: string;
  sku: string;
  quantity: number;
  unitPrice: number;
  gstRate: number;
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  lineTotal: number;
}

export function NewPurchasePage() {
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [productQuery, setProductQuery] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const products = useQuery({
    queryKey: ['product-search', productQuery],
    queryFn: () => searchProducts(productQuery),
    enabled: productQuery.length >= 1,
  });

  const { control, watch } = useForm<FormValues>({
    defaultValues: {
      supplierId: '',
      purchaseType: 'GST',
      invoiceDate: new Date().toISOString().slice(0, 10),
      supplierBillNumber: '',
    },
  });

  const supplierId = watch('supplierId');
  const selectedSupplier = (suppliers.data ?? []).find((s) => s.id === supplierId);
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedSupplier?.gstin || selectedSupplier?.state,
  );

  const totals = useMemo(() => {
    const taxLines = lines.map((l) =>
      calculateLineTax({
        quantity: l.quantity,
        unitPrice: l.unitPrice,
        gstRate: l.gstRate,
        intraState,
      }),
    );
    return calculateInvoiceTotals(taxLines);
  }, [lines, intraState]);

  const mutation = useMutation({
    mutationFn: async (complete: boolean) => {
      if (!supplierId) throw new Error('Supplier is required');
      const draft = await createPurchase({
        supplier: Number(supplierId),
        purchaseType: watch('purchaseType'),
        invoiceDate: watch('invoiceDate'),
        supplierBillNumber: watch('supplierBillNumber') || undefined,
        items: lines.map((l) => ({
          product: l.product,
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: l.gstRate,
        })),
      });
      if (!complete) return draft;
      return completePurchase(draft.id);
    },
    onSuccess: (doc) => {
      setError(null);
      setMessage(
        doc.status === 'COMPLETED'
          ? `Purchase ${doc.number ?? doc.id} completed`
          : 'Purchase draft saved',
      );
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const addProduct = (product: Product | null) => {
    if (!product) return;
    setLines((prev) => {
      const existing = prev.find((l) => l.product === product.id);
      if (existing) {
        return prev.map((l) => {
          if (l.product !== product.id) return l;
          const quantity = l.quantity + 1;
          const tax = calculateLineTax({
            quantity,
            unitPrice: l.unitPrice,
            gstRate: l.gstRate,
            intraState,
          });
          return { ...l, quantity, ...tax };
        });
      }
      const unitPrice = toNumber(product.purchasePrice);
      const tax = calculateLineTax({
        quantity: 1,
        unitPrice,
        gstRate: toNumber(product.gstRate),
        intraState,
      });
      return [
        ...prev,
        {
          key: `${product.id}-${Date.now()}`,
          product: product.id,
          productName: product.name,
          sku: product.sku,
          quantity: 1,
          unitPrice,
          gstRate: toNumber(product.gstRate),
          ...tax,
        },
      ];
    });
    setProductQuery('');
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.newPurchase')}</Typography>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Controller
            name="supplierId"
            control={control}
            rules={{ required: true }}
            render={({ field }) => (
              <Autocomplete<Supplier>
                sx={{ flex: 1 }}
                options={(suppliers.data ?? []).filter((s) => s.isActive)}
                getOptionLabel={(o) => o.name}
                value={(suppliers.data ?? []).find((s) => s.id === field.value) ?? null}
                onChange={(_, v) => field.onChange(v?.id ?? '')}
                renderInput={(params) => (
                  <TextField {...params} required label={t('billing.supplier')} />
                )}
              />
            )}
          />
          <Controller
            name="purchaseType"
            control={control}
            render={({ field }) => (
              <TextField select label="Purchase type" sx={{ minWidth: 140 }} {...field}>
                <MenuItem value="GST">GST</MenuItem>
                <MenuItem value="NON_GST">Non-GST</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="invoiceDate"
            control={control}
            render={({ field }) => <TextField type="date" label={t('common.date')} {...field} />}
          />
          <Controller
            name="supplierBillNumber"
            control={control}
            render={({ field }) => <TextField label="Supplier bill #" {...field} />}
          />
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Autocomplete<Product>
          options={products.data ?? []}
          loading={products.isFetching}
          inputValue={productQuery}
          onInputChange={(_, v) => setProductQuery(v)}
          onChange={(_, v) => addProduct(v)}
          getOptionLabel={(o) => `${o.name} · ${o.sku}`}
          renderInput={(params) => (
            <TextField {...params} label={t('billing.searchProduct')} />
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
              <TableCell align="right">{t('common.total')}</TableCell>
              <TableCell width={56} />
            </TableRow>
          </TableHead>
          <TableBody>
            {lines.map((line) => (
              <TableRow key={line.key}>
                <TableCell>{line.productName}</TableCell>
                <TableCell>
                  <TextField
                    type="number"
                    size="small"
                    value={line.quantity}
                    onChange={(e) => {
                      const quantity = Math.max(0.001, Number(e.target.value));
                      setLines((prev) =>
                        prev.map((l) => {
                          if (l.key !== line.key) return l;
                          const tax = calculateLineTax({
                            quantity,
                            unitPrice: l.unitPrice,
                            gstRate: l.gstRate,
                            intraState,
                          });
                          return { ...l, quantity, ...tax };
                        }),
                      );
                    }}
                  />
                </TableCell>
                <TableCell align="right">{formatMoney(line.unitPrice)}</TableCell>
                <TableCell align="right">{formatMoney(line.lineTotal)}</TableCell>
                <TableCell>
                  <IconButton onClick={() => setLines((prev) => prev.filter((l) => l.key !== line.key))}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Paper sx={{ p: 2, maxWidth: 420, ml: 'auto', width: '100%' }}>
        <Stack spacing={1}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography>{t('billing.subtotal')}</Typography>
            <Typography>{formatMoney(totals.subtotal)}</Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography>{t('billing.tax')}</Typography>
            <Typography>{formatMoney(totals.taxTotal)}</Typography>
          </Box>
          <Divider />
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography fontWeight={700}>{t('billing.grandTotal')}</Typography>
            <Typography fontWeight={700}>{formatMoney(totals.grandTotal)}</Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              disabled={!supplierId || lines.length === 0 || mutation.isPending}
              onClick={() => mutation.mutate(false)}
            >
              {t('common.draft')}
            </Button>
            <Button
              variant="contained"
              disabled={!supplierId || lines.length === 0 || mutation.isPending}
              onClick={() => mutation.mutate(true)}
            >
              {t('common.complete')}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Stack>
  );
}
