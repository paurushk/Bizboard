import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Checkbox from '@mui/material/Checkbox';
import MenuItem from '@mui/material/MenuItem';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { calculateLineTax } from '@/utils/tax';
import type { InvoiceSourceLine } from './invoiceSourceLines';
import { clampSourceLineQty } from './invoiceSourceLines';

interface Props {
  lines: InvoiceSourceLine[];
  onChange: (lines: InvoiceSourceLine[]) => void;
  intraState: boolean | null;
  readOnly?: boolean;
  availableToAdd?: InvoiceSourceLine[];
}

export function InvoiceSourceLineTable({
  lines,
  onChange,
  intraState,
  readOnly = false,
  availableToAdd = [],
}: Props) {
  const updateLine = (key: string, patch: Partial<InvoiceSourceLine>) => {
    onChange(
      lines.map((l) => {
        if (l.key !== key) return l;
        const next = { ...l, ...patch };
        if (patch.quantity != null) {
          next.quantity = clampSourceLineQty(next, patch.quantity);
        }
        return next;
      }),
    );
  };

  const removeLine = (key: string) => {
    onChange(lines.map((l) => (l.key === key ? { ...l, included: false, quantity: 0 } : l)));
  };

  const addLine = (src: InvoiceSourceLine) => {
    if (lines.some((l) => l.key === src.key && l.included)) return;
    const existing = lines.find((l) => l.key === src.key);
    if (existing) {
      onChange(
        lines.map((l) =>
          l.key === src.key ? { ...l, included: true, quantity: Math.min(1, l.maxQty) } : l,
        ),
      );
    } else {
      onChange([...lines, { ...src, included: true, quantity: Math.min(1, src.maxQty) }]);
    }
  };

  const active = lines.filter((l) => l.included);
  const pool = availableToAdd.filter((a) => !active.some((l) => l.key === a.key));

  return (
    <Stack spacing={1}>
      <Paper sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell align="right">{t('billing.qty')}</TableCell>
              <TableCell align="right">{t('billing.priceShort')}</TableCell>
              <TableCell align="right">{t('common.total')}</TableCell>
              {!readOnly ? <TableCell /> : null}
            </TableRow>
          </TableHead>
          <TableBody>
            {active.length === 0 ? (
              <TableRow>
                <TableCell colSpan={readOnly ? 4 : 5} align="center">
                  {t('phase1.selectInvoiceLines')}
                </TableCell>
              </TableRow>
            ) : (
              active.map((line) => {
                const tax = calculateLineTax({
                  quantity: line.quantity,
                  unitPrice: line.unitPrice,
                  discountPercent: line.discountPercent,
                  gstRate: line.gstRate,
                  cessRate: line.cessRate,
                  intraState,
                });
                return (
                  <TableRow key={line.key}>
                    <TableCell>{line.productName}</TableCell>
                    <TableCell align="right">
                      {readOnly ? (
                        line.quantity
                      ) : (
                        <TextField
                          type="number"
                          size="small"
                          value={line.quantity}
                          onChange={(e) =>
                            updateLine(line.key, { quantity: Number(e.target.value) })
                          }
                          inputProps={{ min: 1, max: line.maxQty, style: { width: 72 } }}
                          helperText={`max ${line.maxQty}`}
                          FormHelperTextProps={{ sx: { m: 0, textAlign: 'right' } }}
                        />
                      )}
                    </TableCell>
                    <TableCell align="right">{formatMoney(line.unitPrice)}</TableCell>
                    <TableCell align="right">{formatMoney(tax.lineTotal)}</TableCell>
                    {!readOnly ? (
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          aria-label={t('common.remove')}
                          onClick={() => removeLine(line.key)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    ) : null}
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </Paper>
      {!readOnly && pool.length > 0 ? (
        <Stack direction="row" flexWrap="wrap" gap={1}>
          {pool.map((src) => (
            <Button
              key={src.key}
              size="small"
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={() => addLine(src)}
            >
              {src.productName}
            </Button>
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}

/** Multi-line return picker: checkbox + qty per invoice line. */
export function InvoiceReturnLineTable({
  lines,
  onChange,
  readOnly = false,
}: {
  lines: InvoiceSourceLine[];
  onChange: (lines: InvoiceSourceLine[]) => void;
  readOnly?: boolean;
}) {
  const updateLine = (key: string, patch: Partial<InvoiceSourceLine>) => {
    onChange(
      lines.map((l) => {
        if (l.key !== key) return l;
        const next = { ...l, ...patch };
        if (patch.quantity != null) {
          next.quantity = clampSourceLineQty(next, patch.quantity);
        }
        if (patch.included === true && next.quantity === 0) {
          next.quantity = Math.min(1, next.maxQty);
        }
        if (patch.included === false) {
          next.quantity = 0;
        }
        return next;
      }),
    );
  };

  return (
    <Paper sx={{ overflow: 'auto' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            {!readOnly ? <TableCell padding="checkbox" /> : null}
            <TableCell>{t('nav.products')}</TableCell>
            <TableCell>Condition</TableCell>
            <TableCell align="right">{t('billing.qty')}</TableCell>
            <TableCell align="right">{t('billing.priceShort')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {lines.map((line) => (
            <TableRow key={line.key}>
              {!readOnly ? (
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={line.included}
                    onChange={(e) => updateLine(line.key, { included: e.target.checked })}
                  />
                </TableCell>
              ) : null}
              <TableCell>{line.productName}</TableCell>
              <TableCell>
                {readOnly || !line.included ? (
                  line.condition === 'DAMAGED' ? 'Damaged' : 'Sellable'
                ) : (
                  <TextField
                    select
                    size="small"
                    value={line.condition || 'SELLABLE'}
                    onChange={(e) =>
                      updateLine(line.key, { condition: e.target.value as 'SELLABLE' | 'DAMAGED' })
                    }
                    sx={{ minWidth: 120 }}
                  >
                    <MenuItem value="SELLABLE">Sellable</MenuItem>
                    <MenuItem value="DAMAGED">Damaged</MenuItem>
                  </TextField>
                )}
              </TableCell>
              <TableCell align="right">
                {readOnly || !line.included ? (
                  line.included ? line.quantity : '—'
                ) : (
                  <TextField
                    type="number"
                    size="small"
                    value={line.quantity}
                    onChange={(e) => updateLine(line.key, { quantity: Number(e.target.value) })}
                    inputProps={{ min: 1, max: line.maxQty, style: { width: 72 } }}
                  />
                )}
              </TableCell>
              <TableCell align="right">{formatMoney(line.unitPrice)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}
