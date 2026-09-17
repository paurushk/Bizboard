import { useEffect, useRef, useState } from 'react';
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
import JsBarcode from 'jsbarcode';
import { EmptyState } from '@/components/PageState';
import { useProductSearch } from '@/hooks/useProductSearch';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';

interface LabelRow {
  product: Product;
  copies: number;
}

/** One shelf label: barcode (falls back to SKU when no barcode is set), name, price. */
function Label({ product }: { product: Product }) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const code = (product.barcode || product.sku || '').trim();

  useEffect(() => {
    if (!svgRef.current || !code) return;
    try {
      JsBarcode(svgRef.current, code, {
        format: 'CODE128',
        width: 1.6,
        height: 40,
        fontSize: 12,
        margin: 2,
        displayValue: true,
      });
    } catch {
      // QOS-0047: a barcode value with characters CODE128 can't encode must
      // not crash the whole print run — that label just shows no barcode.
    }
  }, [code]);

  const price = product.mrp ?? product.sellingPrice;

  return (
    <Stack
      className="label-card"
      spacing={0.25}
      alignItems="center"
      sx={{
        border: '1px solid #000',
        borderRadius: 0.5,
        p: 0.75,
        width: '2.6in',
        minHeight: '1.3in',
        justifyContent: 'center',
        breakInside: 'avoid',
      }}
    >
      <Typography variant="caption" fontWeight={700} align="center" noWrap sx={{ maxWidth: '100%' }}>
        {product.name}
      </Typography>
      {code ? <svg ref={svgRef} /> : <Typography variant="caption">{t('labels.noBarcodeValue')}</Typography>}
      <Typography variant="body2" fontWeight={700}>
        {formatMoney(price)}
      </Typography>
    </Stack>
  );
}

export function LabelPrintPage() {
  const [rows, setRows] = useState<LabelRow[]>([]);
  const [pending, setPending] = useState<Product | null>(null);
  const productSearch = useProductSearch({ activeOnly: true, selected: pending });

  const addProduct = (product: Product | null) => {
    if (!product) return;
    setRows((current) => {
      if (current.some((r) => r.product.id === product.id)) return current;
      return [...current, { product, copies: 1 }];
    });
    setPending(null);
    productSearch.setProductQuery('');
  };

  const setCopies = (productId: number, copies: number) => {
    setRows((current) => current.map((r) => (r.product.id === productId ? { ...r, copies } : r)));
  };

  const removeRow = (productId: number) => {
    setRows((current) => current.filter((r) => r.product.id !== productId));
  };

  const totalLabels = rows.reduce((sum, r) => sum + Math.max(0, toNumber(r.copies)), 0);

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
        <PageTitle>{t('labels.pageTitle')}</PageTitle>
        <Button
          className="no-print"
          variant="contained"
          disabled={rows.length === 0}
          onClick={() => window.print()}
        >
          {t('labels.printAll', { count: totalLabels })}
        </Button>
      </Stack>

      <Paper className="no-print" sx={{ p: 2 }}>
        <Autocomplete<Product>
          options={productSearch.options}
          loading={productSearch.isFetching}
          filterOptions={(opts) => opts}
          inputValue={productSearch.productQuery}
          onInputChange={(_, v, reason) => {
            if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
          }}
          value={pending}
          onChange={(_, value) => addProduct(value)}
          getOptionLabel={(p) => `${p.name} (${p.sku})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t('labels.addProduct')}
              helperText={productSearch.helperText}
            />
          )}
        />
      </Paper>

      {rows.length === 0 ? (
        <EmptyState description={t('labels.empty')} />
      ) : (
        <>
          <Paper className="no-print" sx={{ overflow: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('common.name')}</TableCell>
                  <TableCell>{t('common.sku')}</TableCell>
                  <TableCell align="right">{t('labels.copies')}</TableCell>
                  <TableCell align="right">{t('common.actions')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.product.id}>
                    <TableCell>{row.product.name}</TableCell>
                    <TableCell>{row.product.sku}</TableCell>
                    <TableCell align="right">
                      <TextField
                        size="small"
                        type="number"
                        value={row.copies}
                        onChange={(e) => setCopies(row.product.id, Math.max(0, Number(e.target.value) || 0))}
                        sx={{ width: 90 }}
                        inputProps={{ min: 0 }}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <IconButton size="small" onClick={() => removeRow(row.product.id)} aria-label={t('common.delete')}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          <Stack
            className="label-sheet"
            direction="row"
            flexWrap="wrap"
            gap={1}
            sx={{ p: 1 }}
          >
            {rows.flatMap((row) =>
              Array.from({ length: Math.max(0, Math.trunc(row.copies)) }, (_, i) => (
                <Label key={`${row.product.id}-${i}`} product={row.product} />
              )),
            )}
          </Stack>
        </>
      )}
    </Stack>
  );
}
