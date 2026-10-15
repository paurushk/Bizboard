import { useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import type { BillLineError, Product } from '@/types/domain';
import { errorFor, lineAmount, localLineErrors, type EditorLine } from './billLines';

type Props = {
  lines: EditorLine[];
  /** Keys of the rows to show, in bill order. */
  visibleKeys: string[];
  expanded: Set<string>;
  showAdvanced: boolean;
  showPack: boolean;
  showDiscount: boolean;
  priceInclusive: boolean;
  /** v2: a line with only fuzzy product matches must be resolved by the reviewer. */
  productChoiceRequired?: boolean;
  onToggleExpand: (key: string, open: boolean) => void;
  onChange: (key: string, patch: Partial<EditorLine>) => void;
  onDelete: (key: string) => void;
  /** Key whose first invalid field should take focus (set after a failed commit). */
  focusKey?: string | null;
  /** The row the reviewer is pointing at / editing (drives the highlight on the bill image). */
  onActiveRow?: (key: string | null) => void;
};

/** Above this many rows the table is windowed instead of drawn whole. */
export const WINDOW_THRESHOLD = 100;
const ROW_ESTIMATE = 64;

function ProductPickerDialog({
  open,
  onClose,
  onPick,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (product: Product) => void;
}) {
  const search = useProductSearch({ activeOnly: true });
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{t('billUpload.productChoose')}</DialogTitle>
      <DialogContent>
        <Autocomplete
          options={search.options}
          getOptionLabel={(p: Product) => (p.sku ? `${p.name} (${p.sku})` : p.name)}
          filterOptions={(opts) => opts}
          onInputChange={(_, v) => search.setProductQuery(v)}
          onChange={(_, product) => {
            if (product) {
              onPick(product);
              onClose();
            }
          }}
          renderInput={(params) => (
            <TextField {...params} autoFocus margin="dense" label={t('billUpload.productSearch')} />
          )}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function ProductMatchCell({
  line,
  onChange,
}: {
  line: EditorLine;
  onChange: (patch: Partial<EditorLine>) => void;
}) {
  const [picking, setPicking] = useState(false);
  const match = line.productMatch;
  const chosen = line.productId != null;
  const picker = picking ? (
    <ProductPickerDialog
      open={picking}
      onClose={() => setPicking(false)}
      onPick={(product) =>
        onChange({
          productId: product.id,
          createNew: false,
          productMatch: {
            status: 'matched',
            productId: product.id,
            name: product.name,
            method: 'chosen',
            candidates: [],
          },
        })
      }
    />
  ) : null;
  if (chosen || match?.status === 'matched') {
    return (
      <Stack spacing={0.5} alignItems="flex-start">
        <Chip
          size="small"
          color="success"
          variant="outlined"
          label={t('billUpload.productMatched', { name: match?.name ?? '' })}
        />
        {match?.trackBatch ? (
          <Typography variant="caption" color="warning.dark">
            {t('billUpload.batchNeeded')}
          </Typography>
        ) : null}
        <Button size="small" onClick={() => setPicking(true)}>
          {t('billUpload.productChoose')}
        </Button>
        {picker}
      </Stack>
    );
  }
  if (match?.status === 'candidates' && !line.createNew) {
    return (
      <Stack spacing={0.5} alignItems="flex-start">
        {match.candidates.map((candidate) => (
          <Button
            key={candidate.id}
            size="small"
            variant="outlined"
            color="warning"
            onClick={() =>
              onChange({
                productId: candidate.id,
                createNew: false,
                productMatch: {
                  status: 'matched',
                  productId: candidate.id,
                  name: candidate.name,
                  method: 'chosen',
                  candidates: [],
                },
              })
            }
          >
            {t('billUpload.productSimilar', { name: candidate.name })}
          </Button>
        ))}
        <Button size="small" onClick={() => onChange({ createNew: true })}>
          {t('billUpload.productCreateNew')}
        </Button>
        <Button size="small" onClick={() => setPicking(true)}>
          {t('billUpload.productChoose')}
        </Button>
        {picker}
      </Stack>
    );
  }
  return (
    <Stack spacing={0.5} alignItems="flex-start">
      <Chip size="small" variant="outlined" label={t('billUpload.productNew')} />
      <Button size="small" onClick={() => setPicking(true)}>
        {t('billUpload.productChoose')}
      </Button>
      {picker}
    </Stack>
  );
}

export function BillLinesTable({
  lines,
  visibleKeys,
  expanded,
  showAdvanced,
  showPack,
  showDiscount,
  priceInclusive,
  productChoiceRequired,
  onToggleExpand,
  onChange,
  onDelete,
  focusKey,
  onActiveRow,
}: Props) {
  // Big bills are windowed (only the rows on screen are in the DOM); small ones render whole.
  const windowed = visibleKeys.length > WINDOW_THRESHOLD;
  const focusIndex = focusKey ? visibleKeys.indexOf(focusKey) : -1;
  const byKey = new Map(lines.map((line, index) => [line.clientKey, { line, index }]));
  const columnCount = 8 + (showAdvanced ? 2 : 0) + (showPack ? 3 : 0) + (showDiscount ? 1 : 0);

  const field = (
    line: EditorLine,
    row: number,
    name: keyof EditorLine & string,
    labelKey: string,
    width: number,
    errors: BillLineError[],
    errorField: string,
    numberInput = true,
  ) => {
    const problem = errorFor(errors, errorField);
    const label = t(labelKey);
    return (
      <TextField
        size="small"
        type={numberInput ? 'number' : 'text'}
        value={(line[name] as string | undefined) ?? ''}
        placeholder="—"
        error={Boolean(problem)}
        helperText={problem?.message}
        FormHelperTextProps={{ sx: { maxWidth: width + 40, whiteSpace: 'normal', mx: 0 } }}
        onChange={(e) => onChange(line.clientKey, { [name]: e.target.value } as Partial<EditorLine>)}
        inputProps={{
          'aria-label': t('billUpload.fieldForRow', { field: label, row }),
          'aria-invalid': problem ? true : undefined,
          title: problem?.message,
        }}
        sx={{ width }}
        autoFocus={focusKey === line.clientKey && Boolean(problem)}
      />
    );
  };

  // Errors for these fields appear under their own input (U-02); the rest stay under the name.
  const shownFields = new Set<string>([
    'name', 'quantity', 'unit_price', 'gst_rate', 'mrp',
    ...(showAdvanced ? ['sku', 'hsn_code'] : []),
    ...(showPack ? ['cs', 'pcs', 'upc'] : []),
    ...(showDiscount ? ['discount_percent'] : []),
  ]);

  type Measure = ((el: Element | null) => void) | undefined;
  const renderRow = (key: string, position: number, measure?: Measure) => {
      const entry = byKey.get(key);
      if (!entry) return null;
      const { line, index } = entry;
      const row = index + 1;
      const serverErrors = line.errors ?? [];
      const clientErrors = line.include !== false ? localLineErrors(line) : [];
      // Server errors win (they include context-only rules such as product choice).
      const errors = [...serverErrors, ...clientErrors.filter((c) => !serverErrors.some((s) => s.field === c.field))];
      if (
        productChoiceRequired &&
        line.include !== false &&
        line.productMatch?.status === 'candidates' &&
        line.productId == null &&
        !line.createNew &&
        !errors.some((e) => e.field === 'product')
      ) {
        errors.push({ field: 'product', code: 'PRODUCT_CHOICE_REQUIRED', message: t('billUpload.productChoose') });
      }
      const hasProblem = errors.some((e) => e.severity !== 'warning') && line.include !== false;
      const isFlagged = (line.flags?.length ?? 0) > 0;
      const open = isFlagged || hasProblem || expanded.has(key);
      const amount = lineAmount(line, priceInclusive);

      if (!open) {
        return (
          <TableRow
            key={key}
            ref={measure} data-index={position} id={`bill-row-${key}`}
            hover
            onMouseEnter={() => onActiveRow?.(key)}
            onMouseLeave={() => onActiveRow?.(null)}
            onFocus={() => onActiveRow?.(key)}
            // F2-047: the collapsed row expands on click — reachable from the keyboard too.
            role="button"
            tabIndex={0}
            aria-expanded={false}
            aria-label={t('billUpload.expandRow')}
            sx={{ cursor: 'pointer' }}
            onClick={() => onToggleExpand(key, true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onToggleExpand(key, true);
              }
            }}
          >
            <TableCell>{line.si || row}</TableCell>
            <TableCell padding="checkbox">
              <Checkbox
                checked={line.include !== false}
                inputProps={{ 'aria-label': t('billUpload.fieldForRow', { field: t('billUpload.include'), row }) }}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onChange(key, { include: e.target.checked })}
              />
            </TableCell>
            <TableCell>{line.name}</TableCell>
            <TableCell>
              {line.productMatch?.status === 'matched' || line.productId != null ? (
                <Chip size="small" color="success" variant="outlined" label={t('billUpload.productMatched', { name: line.productMatch?.name ?? '' })} />
              ) : line.productMatch?.status === 'candidates' && !line.createNew ? (
                <Chip size="small" color="warning" variant="outlined" label={t('billUpload.productSimilarChip')} />
              ) : (
                <Chip size="small" variant="outlined" label={t('billUpload.productNew')} />
              )}
            </TableCell>
            {showAdvanced ? <TableCell>{line.sku || '—'}</TableCell> : null}
            {showAdvanced ? <TableCell>{line.hsnCode || '—'}</TableCell> : null}
            {showPack ? <TableCell align="right">{line.cs || '—'}</TableCell> : null}
            {showPack ? <TableCell align="right">{line.pcs || '—'}</TableCell> : null}
            {showPack ? <TableCell align="right">{line.upc || '—'}</TableCell> : null}
            <TableCell align="right">{line.quantity || '—'}</TableCell>
            <TableCell align="right">{line.unitPrice || '—'}</TableCell>
            {showDiscount ? <TableCell align="right">{line.discountPercent || '—'}</TableCell> : null}
            <TableCell align="right">{line.gstRate || '—'}</TableCell>
            <TableCell align="right">{line.mrp || '—'}</TableCell>
            <TableCell align="right">{amount != null ? amount.toFixed(2) : '—'}</TableCell>
          </TableRow>
        );
      }
      return (
        <TableRow
          key={key}
          ref={measure} data-index={position} id={`bill-row-${key}`}
          aria-expanded
          onMouseEnter={() => onActiveRow?.(key)}
          onMouseLeave={() => onActiveRow?.(null)}
          onFocus={() => onActiveRow?.(key)}
          sx={hasProblem ? { bgcolor: 'error.light' } : isFlagged ? { bgcolor: 'warning.light' } : undefined}
        >
          <TableCell>
            <Stack direction="row" alignItems="center">
              {line.si || row}
              {!isFlagged && !hasProblem ? (
                <IconButton
                  size="small"
                  aria-label={t('billUpload.collapseRow', { row })}
                  onClick={() => onToggleExpand(key, false)}
                >
                  <ExpandLessIcon fontSize="small" />
                </IconButton>
              ) : null}
            </Stack>
          </TableCell>
          <TableCell padding="checkbox">
            <Checkbox
              checked={line.include !== false}
              inputProps={{ 'aria-label': t('billUpload.fieldForRow', { field: t('billUpload.include'), row }) }}
              onChange={(e) => onChange(key, { include: e.target.checked })}
            />
          </TableCell>
          <TableCell>
            <Stack spacing={0.5}>
              {field(line, row, 'name', 'common.name', 220, errors, 'name', false)}
              {(line.flags ?? []).map((flag, fi) => (
                <Typography key={fi} variant="caption" color="warning.dark">
                  {t('billUpload.rowFlagged')}: {flag}
                </Typography>
              ))}
              {line.excludedReason && line.include === false ? (
                <Typography variant="caption" color="text.secondary">
                  {t('billUpload.systemExcluded', { reason: line.excludedReason })}
                </Typography>
              ) : null}
              {errors
                .filter((e) => e.severity !== 'warning' && e.field !== 'product' && !shownFields.has(e.field))
                .map((e, ei) => (
                  <Typography key={ei} variant="caption" color="error">
                    {e.message}
                  </Typography>
                ))}
              {errors
                .filter((e) => e.field === 'product')
                .map((e, ei) => (
                  <Typography key={`p${ei}`} variant="caption" color="error">
                    {e.message}
                  </Typography>
                ))}
              {line.belowPriceList ? (
                <Chip
                  size="small"
                  color="warning"
                  label={t('billUpload.belowPriceList', { price: line.priceListPrice ?? '' })}
                />
              ) : null}
              <Button
                size="small"
                color="inherit"
                startIcon={<DeleteOutlineIcon fontSize="small" />}
                onClick={() => onDelete(key)}
                aria-label={t('billUpload.deleteRow', { row })}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t('common.delete')}
              </Button>
            </Stack>
          </TableCell>
          <TableCell>
            <ProductMatchCell line={line} onChange={(patch) => onChange(key, patch)} />
          </TableCell>
          {showAdvanced ? (
            <TableCell>{field(line, row, 'sku', 'common.sku', 120, errors, 'sku', false)}</TableCell>
          ) : null}
          {showAdvanced ? (
            <TableCell>{field(line, row, 'hsnCode', 'billUpload.hsn', 110, errors, 'hsn_code', false)}</TableCell>
          ) : null}
          {showPack ? <TableCell align="right">{field(line, row, 'cs', 'billUpload.colCs', 72, errors, 'cs')}</TableCell> : null}
          {showPack ? <TableCell align="right">{field(line, row, 'pcs', 'billUpload.colPcs', 72, errors, 'pcs')}</TableCell> : null}
          {showPack ? <TableCell align="right">{field(line, row, 'upc', 'billUpload.colUpc', 72, errors, 'upc')}</TableCell> : null}
          <TableCell align="right">
            {field(line, row, 'quantity', 'billing.qty', 90, errors, 'quantity')}
            {line.packQtyHint ? (
              <Button
                size="small"
                color="warning"
                sx={{ display: 'block', mt: 0.25, p: 0, minWidth: 0, textTransform: 'none' }}
                aria-label={t('billUpload.packApplyButton', { qty: line.packQtyHint })}
                onClick={() => onChange(key, { quantity: line.packQtyHint, packQtyHint: undefined })}
              >
                {t('billUpload.packApply', { qty: line.packQtyHint })}
              </Button>
            ) : null}
          </TableCell>
          <TableCell align="right">{field(line, row, 'unitPrice', 'billing.price', 110, errors, 'unit_price')}</TableCell>
          {showDiscount ? (
            <TableCell align="right">{field(line, row, 'discountPercent', 'billUpload.colDiscount', 80, errors, 'discount_percent')}</TableCell>
          ) : null}
          <TableCell align="right">{field(line, row, 'gstRate', 'billUpload.gstPercent', 90, errors, 'gst_rate')}</TableCell>
          <TableCell align="right">{field(line, row, 'mrp', 'billUpload.mrp', 100, errors, 'mrp')}</TableCell>
          <TableCell align="right">{amount != null ? amount.toFixed(2) : '—'}</TableCell>
        </TableRow>
      );
  };

  const head = (
    <TableHead>
      <TableRow>
        <TableCell>{t('billUpload.siNo')}</TableCell>
        <TableCell>{t('billUpload.include')}</TableCell>
        <TableCell>{t('common.name')}</TableCell>
        <TableCell>{t('billUpload.colProduct')}</TableCell>
        {showAdvanced ? <TableCell>{t('common.sku')}</TableCell> : null}
        {showAdvanced ? <TableCell>{t('billUpload.hsn')}</TableCell> : null}
        {showPack ? <TableCell align="right">{t('billUpload.colCs')}</TableCell> : null}
        {showPack ? <TableCell align="right">{t('billUpload.colPcs')}</TableCell> : null}
        {showPack ? <TableCell align="right">{t('billUpload.colUpc')}</TableCell> : null}
        <TableCell align="right">{t('billing.qty')}</TableCell>
        <TableCell align="right">{t('billing.price')}</TableCell>
        {showDiscount ? <TableCell align="right">{t('billUpload.colDiscount')}</TableCell> : null}
        <TableCell align="right">{t('billUpload.gstPercent')}</TableCell>
        <TableCell align="right">{t('billUpload.mrp')}</TableCell>
        <TableCell align="right">{t('billUpload.colLineTotal')}</TableCell>
      </TableRow>
    </TableHead>
  );

  const emptyRow = visibleKeys.length === 0 ? (
    <TableRow>
      <TableCell colSpan={columnCount}>
        <Box sx={{ py: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('billUpload.noLines')}
          </Typography>
        </Box>
      </TableCell>
    </TableRow>
  ) : null;

  if (windowed) {
    return (
      <VirtualizedTable rowCount={visibleKeys.length} rowHeight={ROW_ESTIMATE} maxHeight={680} scrollToIndex={focusIndex >= 0 ? focusIndex : null}>
        {({ rows: virtualRows, totalSize, measureElement }) => (
          <Table size="small">
            {head}
            <TableBody>
              {virtualRows.length > 0 && virtualRows[0].start > 0 ? (
                <TableRow style={{ height: virtualRows[0].start }} aria-hidden>
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={columnCount} />
                </TableRow>
              ) : null}
              {virtualRows.map((v) => renderRow(visibleKeys[v.index], v.index, measureElement))}
              {virtualRows.length > 0 ? (
                <TableRow
                  style={{ height: Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end) }}
                  aria-hidden
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={columnCount} />
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        )}
      </VirtualizedTable>
    );
  }

  return (
    <TableContainer sx={{ overflowX: 'auto' }}>
      <Table size="small">
        {head}
        <TableBody>
          {visibleKeys.map((key, index) => renderRow(key, index))}
          {emptyRow}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
