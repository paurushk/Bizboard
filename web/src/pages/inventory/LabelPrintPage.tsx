import { useEffect, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
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
import JsBarcode from 'jsbarcode';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  downloadLabelsZpl,
  downloadLabelZpl,
  generateBarcode,
  getProduct,
  listBatches,
  listMissingBarcode,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';
import { canAdjustInventory } from '@/utils/permissions';
import { EmptyState } from '@/components/PageState';
import { useProductSearch } from '@/hooks/useProductSearch';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import {
  clampCopies,
  isCode128Encodable,
  isThermalSize,
  LABEL_SIZES,
  labelPrice,
  MAX_COPIES,
  MAX_ZPL_COPIES,
  parseLabelItems,
  SHEET_TEMPLATES,
  type LabelSize,
} from '@/pages/inventory/labelHelpers';
import type { BatchLot, Product } from '@/types/domain';
import { formatMoney } from '@/utils/money';

interface LabelRow {
  product: Product;
  copies: number;
  /** Chosen lot, for batch-tracked items: the label then carries its batch and expiry. */
  batch: BatchLot | null;
}

/** One shelf label: barcode (falls back to SKU when no barcode is set), name, price, lot. */
function Label({ product, batch, size }: { product: Product; batch: BatchLot | null; size: LabelSize }) {
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

  const { width, minHeight } = LABEL_SIZES[size];
  return (
    <Stack
      className="label-card"
      spacing={0.25}
      alignItems="center"
      sx={{
        border: '1px solid #000',
        borderRadius: 0.5,
        p: 0.75,
        width,
        minHeight,
        boxSizing: 'border-box',
        justifyContent: 'center',
        breakInside: 'avoid',
      }}
    >
      <Typography variant="caption" fontWeight={700} align="center" noWrap sx={{ maxWidth: '100%' }}>
        {product.name}
      </Typography>
      {code ? <svg ref={svgRef} /> : <Typography variant="caption">{t('labels.noBarcodeValue')}</Typography>}
      <Typography variant="body2" fontWeight={700}>
        {formatMoney(labelPrice(product))}
      </Typography>
      {batch ? (
        <Typography variant="caption">
          {t('labels.batchLine', { batch: batch.batchNo })}
          {batch.expiryDate ? ` · ${t('labels.expLine', { date: batch.expiryDate })}` : ''}
        </Typography>
      ) : null}
    </Stack>
  );
}

function saveBlob(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Lot picker for one batch-tracked row. */
function BatchPicker({ row, onPick }: { row: LabelRow; onPick: (lot: BatchLot | null) => void }) {
  const lots = useQuery({ queryKey: ['batches', row.product.id], queryFn: () => listBatches(row.product.id) });
  return (
    <TextField
      select
      size="small"
      label={t('labels.batch')}
      value={row.batch ? String(row.batch.id) : ''}
      onChange={(e) => onPick((lots.data ?? []).find((lot) => String(lot.id) === e.target.value) ?? null)}
      sx={{ minWidth: 140 }}
    >
      <MenuItem value="">{t('labels.noBatchOnLabel')}</MenuItem>
      {(lots.data ?? []).map((lot) => (
        <MenuItem key={lot.id} value={String(lot.id)}>
          {lot.batchNo}
          {lot.expiryDate ? ` · ${lot.expiryDate}` : ''}
        </MenuItem>
      ))}
    </TextField>
  );
}

export function LabelPrintPage() {
  const [rows, setRows] = useState<LabelRow[]>([]);
  const [pending, setPending] = useState<Product | null>(null);
  const [size, setSize] = useState<LabelSize>('small');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const { ask, dialog } = useConfirmPrompt();
  const { user } = useAuth();
  // Printing is open to anyone who can see stock; changing an item (a new barcode) is not.
  const canGiveBarcodes = canAdjustInventory(user);
  const [calibrating, setCalibrating] = useState(false);
  const productSearch = useProductSearch({ activeOnly: true, selected: pending });
  const [params] = useSearchParams();

  // A purchase bill links here with the items that came in and how many.
  const linkedItems = params.get('items');
  const [loadedLink, setLoadedLink] = useState<string | null>(null);
  if (linkedItems && loadedLink !== linkedItems) {
    setLoadedLink(linkedItems);
    const wanted = parseLabelItems(linkedItems);
    void Promise.all(wanted.map((w) => getProduct(w.productId).then((product) => ({ product, copies: w.copies }))))
      .then((found) => {
        setRows((current) => {
          const next = [...current];
          for (const { product, copies } of found) {
            if (!next.some((r) => r.product.id === product.id)) next.push({ product, copies, batch: null });
          }
          return next;
        });
        setNotice(t('labels.fromBill', { count: String(found.length) }));
      })
      .catch((e) => setError(getErrorMessage(e)));
  }

  const addProduct = (product: Product | null) => {
    if (!product) return;
    const exists = rows.some((r) => r.product.id === product.id);
    setRows((current) => {
      if (current.some((r) => r.product.id === product.id)) {
        // Picking the same item again means "one more", not nothing.
        return current.map((r) =>
          r.product.id === product.id ? { ...r, copies: clampCopies(r.copies + 1) } : r,
        );
      }
      return [...current, { product, copies: 1, batch: null }];
    });
    setNotice(exists ? t('labels.anotherCopy', { name: product.name }) : '');
    setPending(null);
    productSearch.setProductQuery('');
  };

  const addWithoutBarcode = async () => {
    setError('');
    try {
      // The server counts them and hands over a page, so the sheet says how many were left out.
      const { count, results } = await listMissingBarcode(1, 100);
      setRows((current) => {
        const next = [...current];
        for (const product of results) {
          if (!next.some((r) => r.product.id === product.id)) next.push({ product, copies: 1, batch: null });
        }
        return next;
      });
      setNotice(
        count > results.length
          ? t('labels.addedWithoutBarcodePartial', { shown: String(results.length), count: String(count) })
          : t('labels.addedWithoutBarcode', { count: String(results.length) }),
      );
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  // Give the items on this sheet that have no barcode a new one (asks first: a barcode is never reused).
  const withoutBarcode = rows.filter((r) => !(r.product.barcode || '').trim());
  const [generating, setGenerating] = useState<{ done: number; total: number } | null>(null);
  const generateBarcodes = async () => {
    if (withoutBarcode.length === 0) return;
    if (!(await ask([t('labels.generateConfirm', { count: String(withoutBarcode.length) })]))) return;
    setError('');
    const made = new Map<number, string>();
    try {
      for (const [index, row] of withoutBarcode.entries()) {
        setGenerating({ done: index, total: withoutBarcode.length });
        const result = await generateBarcode(row.product.id);
        made.set(row.product.id, result.barcode);
      }
      setNotice(t('labels.generated', { count: String(made.size) }));
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setGenerating(null);
      setRows((current) =>
        current.map((r) => (made.has(r.product.id) ? { ...r, product: { ...r.product, barcode: made.get(r.product.id) } } : r)),
      );
    }
  };

  const setCopies = (productId: number, copies: number) => {
    setRows((current) => current.map((r) => (r.product.id === productId ? { ...r, copies } : r)));
  };
  const setBatch = (productId: number, batch: BatchLot | null) => {
    setRows((current) => current.map((r) => (r.product.id === productId ? { ...r, batch } : r)));
  };
  const removeRow = (productId: number) => {
    setRows((current) => current.filter((r) => r.product.id !== productId));
  };

  const downloadZpl = async (row: LabelRow) => {
    setError('');
    try {
      const { url } = await downloadLabelZpl(row.product.id, Math.max(1, Math.min(row.copies, MAX_ZPL_COPIES)), {
        size: isThermalSize(size) ? size : 'small',
        batch: row.batch ? Number(row.batch.id) : null,
      });
      saveBlob(url, `labels-${row.product.sku || row.product.id}.zpl`);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  const downloadAllZpl = async () => {
    setError('');
    try {
      const { url } = await downloadLabelsZpl(
        rows
          .filter((r) => r.copies > 0)
          .map((r) => ({
            product: Number(r.product.id),
            copies: Math.max(1, Math.min(r.copies, MAX_ZPL_COPIES)),
            batch: r.batch ? Number(r.batch.id) : null,
          })),
        { size: isThermalSize(size) ? size : 'small' },
      );
      saveBlob(url, 'labels.zpl');
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  // A page of numbered empty cells, to check that the sheet lines up before real labels are wasted.
  useEffect(() => {
    if (!calibrating) return;
    const id = window.setTimeout(() => {
      window.print();
      setCalibrating(false);
    }, 0);
    return () => window.clearTimeout(id);
  }, [calibrating]);
  const template = SHEET_TEMPLATES[size];

  const totalLabels = rows.reduce((sum, r) => sum + clampCopies(r.copies), 0);

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

      {notice ? (
        <Alert className="no-print" severity="info" onClose={() => setNotice('')}>
          {notice}
        </Alert>
      ) : null}
      {error ? (
        <Alert className="no-print" severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      ) : null}

      <Paper className="no-print" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'flex-start' }}>
          <Autocomplete<Product>
            sx={{ flex: 1 }}
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
          <TextField
            select
            label={t('labels.size')}
            value={size}
            onChange={(e) => setSize(e.target.value as LabelSize)}
            sx={{ minWidth: 190 }}
          >
            <MenuItem value="small">{t('labels.sizeSmall')}</MenuItem>
            <MenuItem value="medium">{t('labels.sizeMedium')}</MenuItem>
            <MenuItem value="large">{t('labels.sizeLarge')}</MenuItem>
            <MenuItem value="a4_3x8">{t('labels.sizeSheet3x8')}</MenuItem>
            <MenuItem value="a4_2x7">{t('labels.sizeSheet2x7')}</MenuItem>
          </TextField>
          {template ? (
            <Button variant="outlined" onClick={() => setCalibrating(true)} sx={{ whiteSpace: 'nowrap' }}>
              {t('labels.calibrate')}
            </Button>
          ) : null}
          <Button variant="outlined" onClick={() => void addWithoutBarcode()} sx={{ whiteSpace: 'nowrap' }}>
            {t('labels.addWithoutBarcode')}
          </Button>
        </Stack>
      </Paper>

      {rows.length === 0 ? (
        <EmptyState description={t('labels.empty')} />
      ) : (
        <>
          <Paper className="no-print" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('common.name')}</TableCell>
                  <TableCell>{t('common.sku')}</TableCell>
                  <TableCell>{t('labels.batch')}</TableCell>
                  <TableCell align="right">{t('labels.copies')}</TableCell>
                  <TableCell align="right">{t('common.actions')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.product.id}>
                    <TableCell>
                      {row.product.name}
                      {(row.product.barcode || row.product.sku) && !isCode128Encodable((row.product.barcode || row.product.sku || '').trim()) ? (
                        <Chip size="small" color="warning" label={t('labels.unencodable')} sx={{ ml: 1 }} />
                      ) : null}
                    </TableCell>
                    <TableCell>{row.product.sku}</TableCell>
                    <TableCell>
                      {row.product.trackBatch ? (
                        <BatchPicker row={row} onPick={(lot) => setBatch(row.product.id, lot)} />
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell align="right">
                      <TextField
                        size="small"
                        type="number"
                        value={row.copies}
                        onChange={(e) => setCopies(row.product.id, clampCopies(e.target.value))}
                        sx={{ width: 90 }}
                        inputProps={{ min: 0, max: MAX_COPIES }}
                        helperText={row.copies >= MAX_COPIES ? t('labels.maxCopies', { max: String(MAX_COPIES) }) : undefined}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => void downloadZpl(row)} disabled={row.copies <= 0 || !isThermalSize(size)}>
                        {t('labels.zpl')}
                      </Button>
                      <IconButton size="small" onClick={() => removeRow(row.product.id)} aria-label={t('common.delete')}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ p: 1 }}>
              <Button size="small" variant="outlined" onClick={() => void downloadAllZpl()} disabled={!isThermalSize(size)}>
                {t('labels.zplAll')}
              </Button>
              {canGiveBarcodes && withoutBarcode.length > 0 ? (
                <Button size="small" variant="outlined" disabled={generating !== null} onClick={() => void generateBarcodes()}>
                  {generating
                    ? t('labels.generating', { done: String(generating.done), total: String(generating.total) })
                    : t('labels.generateBarcodes', { count: String(withoutBarcode.length) })}
                </Button>
              ) : null}
              <Typography variant="caption" color="text.secondary">
                {isThermalSize(size) ? t('labels.zplHelp', { max: String(MAX_ZPL_COPIES) }) : t('labels.zplSheetNote')}
              </Typography>
            </Stack>
          </Paper>

          <Stack
            className="label-sheet"
            direction="row"
            flexWrap="wrap"
            gap={template ? 0 : 1}
            sx={{
              p: template ? 0 : 1,
              ...(template ? { display: 'grid', gridTemplateColumns: `repeat(${template.columns}, ${LABEL_SIZES[size].width})` } : {}),
              '@media print': calibrating ? { display: 'none' } : undefined,
            }}
          >
            {rows.flatMap((row) =>
              Array.from({ length: clampCopies(row.copies) }, (_, i) => (
                <Label key={`${row.product.id}-${i}`} product={row.product} batch={row.batch} size={size} />
              )),
            )}
          </Stack>
        </>
      )}
      {calibrating && template ? (
        <Box
          className="label-calibration"
          sx={{
            display: 'none',
            '@media print': {
              display: 'grid',
              gridTemplateColumns: `repeat(${template.columns}, ${LABEL_SIZES[size].width})`,
            },
          }}
        >
          {Array.from({ length: template.columns * template.rows }, (_, i) => (
            <Box
              key={i}
              sx={{ border: '1px dashed #000', width: LABEL_SIZES[size].width, height: LABEL_SIZES[size].minHeight, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              {i + 1}
            </Box>
          ))}
        </Box>
      ) : null}
      {dialog}
    </Stack>
  );
}
