import type { ReactNode } from 'react';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import { CompactField, NumericField } from './NumericField';
import type { DraftLine } from './types';
import { t } from '@/i18n';
import { formatMoney, roundMoney } from '@/utils/money';
import type { LineTaxResult } from '@/utils/tax';
import { unitSwitchPatch } from './lineHelpers';

export type DraftLinePatchOpts = { fromDiscountAmount?: boolean };

interface DraftLineTableProps {
  lines: DraftLine[];
  taxes: Array<LineTaxResult | undefined>;
  showCess: boolean;
  showMrpSavings?: boolean;
  qtyDisabled?: boolean;
  moneyDisabled?: boolean;
  deleteDisabled?: boolean;
  showBatchSlot?: boolean;
  showSerialSlot?: boolean;
  showSupplyNature?: boolean;
  onUpdate: (key: string, patch: Partial<DraftLine>, opts?: DraftLinePatchOpts) => void;
  onDelete: (key: string) => void;
  onFocusAdd?: () => void;
  renderBatchSlot?: (line: DraftLine) => ReactNode;
  renderSerialSlot?: (line: DraftLine) => ReactNode;
}

export function DraftLineTable({
  lines,
  taxes,
  showCess,
  showMrpSavings = true,
  qtyDisabled,
  moneyDisabled,
  deleteDisabled,
  showBatchSlot,
  showSerialSlot,
  showSupplyNature,
  onUpdate,
  onDelete,
  onFocusAdd,
  renderBatchSlot,
  renderSerialSlot,
}: DraftLineTableProps) {
  return (
    <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto', width: '100%', maxWidth: '100%' }}>
      <Table size="small" stickyHeader>
      <TableHead>
        <TableRow>
          <TableCell width={48}>{t('billing.no')}</TableCell>
          <TableCell
            sx={{
              position: { xs: 'sticky', md: 'static' },
              left: 0,
              zIndex: { xs: 3, md: 1 },
              backgroundColor: 'background.paper',
              minWidth: 180,
            }}
          >
            {t('billing.items')}
          </TableCell>
          <TableCell width={90} sx={{ display: { xs: 'none', md: 'table-cell' } }}>
            {t('billing.hsn')}
          </TableCell>
          {showBatchSlot ? (
            <>
              <TableCell width={90}>{t('billing.batchNo')}</TableCell>
              <TableCell width={110}>{t('billing.expDate')}</TableCell>
              <TableCell width={110}>{t('billing.mfgDate')}</TableCell>
            </>
          ) : null}
          {showSerialSlot ? <TableCell width={140}>Serials</TableCell> : null}
          <TableCell width={80} align="right">
            {t('billing.mrp')}
          </TableCell>
          <TableCell width={130}>{t('billing.qty')}</TableCell>
          <TableCell width={110} align="right">
            {t('billing.price')}
          </TableCell>
          <TableCell width={200}>{t('billing.discount')}</TableCell>
          <TableCell width={100}>{t('billing.tax')}</TableCell>
          {showSupplyNature ? (
            <TableCell width={130}>{t('billing.supplyNature')}</TableCell>
          ) : null}
          <TableCell width={100} align="right">
            {t('billing.amount')}
          </TableCell>
          <TableCell
            width={72}
            sx={{
              position: { xs: 'sticky', md: 'static' },
              right: 0,
              zIndex: { xs: 3, md: 1 },
              backgroundColor: 'background.paper',
            }}
          />
        </TableRow>
      </TableHead>
      <TableBody>
        {lines.map((line, idx) => {
          const tax = taxes[idx];
          const mrpOff =
            line.mrp > 0 && line.unitPrice < line.mrp
              ? roundMoney(((line.mrp - line.unitPrice) / line.mrp) * 100)
              : null;
          return (
            <TableRow key={line.key} hover>
              <TableCell>{idx + 1}</TableCell>
              <TableCell
                sx={{
                  position: { xs: 'sticky', md: 'static' },
                  left: 0,
                  zIndex: { xs: 2, md: 1 },
                  backgroundColor: 'background.paper',
                }}
              >
                <Typography fontWeight={600} variant="body2">
                  {line.productName}
                </Typography>
                <CompactField
                  placeholder={t('billing.lineDescriptionPlaceholder')}
                  value={line.description}
                  onChange={(e) => onUpdate(line.key, { description: e.target.value })}
                  sx={{ mt: 0.5 }}
                />
              </TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                <Typography variant="body2">{line.hsnCode || '—'}</Typography>
              </TableCell>
              {showBatchSlot ? renderBatchSlot?.(line) : null}
              {showSerialSlot ? (
                renderSerialSlot ? (
                  renderSerialSlot(line)
                ) : (
                  <TableCell />
                )
              ) : null}
              <TableCell align="right">
                <Typography variant="body2">{line.mrp > 0 ? formatMoney(line.mrp) : '—'}</Typography>
                {showMrpSavings && mrpOff != null ? (
                  <Typography variant="caption" color="success.main" title="Savings vs MRP (not line discount)">
                    {mrpOff}% vs MRP
                  </Typography>
                ) : null}
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 110 }}>
                  <NumericField
                    value={line.quantity}
                    onValueChange={(n) => onUpdate(line.key, { quantity: n > 0 ? n : 1 })}
                    min={0}
                    emptyAs={1}
                    fullWidth={false}
                    disabled={qtyDisabled}
                    sx={{ width: 80, minWidth: 80 }}
                  />
                  {line.alternateUnitName ? (
                    <TextField
                      select
                      size="small"
                      value={line.unitName}
                      onChange={(e) => onUpdate(line.key, unitSwitchPatch(line, e.target.value))}
                      disabled={qtyDisabled}
                      sx={{ width: 88, minWidth: 88 }}
                    >
                      {[line.baseUnitName || 'PCS', line.alternateUnitName]
                        .filter((unit, index, all) => Boolean(unit) && all.indexOf(unit) === index)
                        .map((unit) => (
                          <MenuItem key={unit} value={unit}>
                            {unit}
                          </MenuItem>
                        ))}
                    </TextField>
                  ) : (
                    <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                      {line.unitName}
                    </Typography>
                  )}
                </Stack>
              </TableCell>
              <TableCell align="right">
                <NumericField
                  value={line.unitPrice}
                  onValueChange={(n) => onUpdate(line.key, { unitPrice: n })}
                  min={0}
                  decimals={2}
                  fullWidth={false}
                  disabled={moneyDisabled}
                  sx={{ width: 96, minWidth: 96 }}
                />
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.5} sx={{ minWidth: 180 }}>
                  <NumericField
                    value={line.discountPercent}
                    onValueChange={(n) => onUpdate(line.key, { discountPercent: Math.min(100, n) })}
                    min={0}
                    decimals={2}
                    fullWidth={false}
                    disabled={moneyDisabled}
                    sx={{ width: 88, minWidth: 88 }}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">%</InputAdornment>,
                    }}
                  />
                  <NumericField
                    value={line.discountAmount}
                    onValueChange={(n) => onUpdate(line.key, { discountAmount: n }, { fromDiscountAmount: true })}
                    min={0}
                    decimals={2}
                    fullWidth={false}
                    disabled={moneyDisabled}
                    sx={{ width: 96, minWidth: 96 }}
                    InputProps={{
                      startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                    }}
                  />
                </Stack>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {line.gstRate <= 0 ? '0%' : `${line.gstRate}%`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  ({formatMoney(tax?.taxTotal ?? 0)})
                </Typography>
                {showCess ? (
                  <NumericField
                    value={line.cessRate ?? 0}
                    onValueChange={(n) => onUpdate(line.key, { cessRate: n })}
                    min={0}
                    decimals={2}
                    fullWidth={false}
                    disabled={moneyDisabled}
                    sx={{ width: 72, mt: 0.5, display: { xs: 'none', md: 'inline-flex' } }}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">cess%</InputAdornment>,
                    }}
                  />
                ) : null}
              </TableCell>
              {showSupplyNature ? (
                <TableCell>
                  <CompactField
                    select
                    size="small"
                    value={line.supplyNature ?? 'TAXABLE'}
                    disabled={moneyDisabled}
                    onChange={(e) =>
                      onUpdate(line.key, {
                        supplyNature: e.target.value as DraftLine['supplyNature'],
                      })
                    }
                    sx={{ minWidth: 120 }}
                  >
                    <MenuItem value="TAXABLE">{t('billing.supplyTaxable')}</MenuItem>
                    <MenuItem value="NIL">{t('billing.supplyNil')}</MenuItem>
                    <MenuItem value="EXEMPT">{t('billing.supplyExempt')}</MenuItem>
                    <MenuItem value="NON_GST">{t('billing.supplyNonGst')}</MenuItem>
                  </CompactField>
                </TableCell>
              ) : null}
              <TableCell align="right">
                <Typography fontWeight={600}>{formatMoney(tax?.lineTotal ?? 0)}</Typography>
              </TableCell>
              <TableCell
                sx={{
                  position: { xs: 'sticky', md: 'static' },
                  right: 0,
                  zIndex: { xs: 2, md: 1 },
                  backgroundColor: 'background.paper',
                }}
              >
                <Stack direction="row">
                  {onFocusAdd ? (
                    <IconButton
                      size="small"
                      color="primary"
                      aria-label={t('a11y.addRow')}
                      disabled={deleteDisabled}
                      onClick={onFocusAdd}
                    >
                      <AddIcon fontSize="small" />
                    </IconButton>
                  ) : null}
                  <IconButton
                    size="small"
                    aria-label={t('common.remove')}
                    disabled={deleteDisabled}
                    onClick={() => onDelete(line.key)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  </TableContainer>
  );
}
