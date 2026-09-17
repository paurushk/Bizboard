import { useEffect, useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import type { Quotation } from '@/types/domain';
import { toNumber } from '@/utils/money';
import {
  buildConvertItemsPayload,
  remainingQuotationQty,
  type ConvertLinePayload,
} from '@/utils/quotationConvert';

type Mode = 'invoice' | 'order';

type Props = {
  quotation: Quotation | null;
  mode: Mode | null;
  pending?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: (items: ConvertLinePayload[]) => void;
};

export function ConvertQuotationDialog({
  quotation,
  mode,
  pending,
  error,
  onClose,
  onConfirm,
}: Props) {
  const [qtyById, setQtyById] = useState<Record<number, number>>({});

  // Computed once per quotation change instead of re-deriving
  // remainingQuotationQty(line) at every call site (initial qty, canSubmit,
  // table render, per-row max) -- same pure result, one source of truth.
  const remainingById = useMemo(() => {
    const map: Record<number, number> = {};
    for (const line of quotation?.items ?? []) {
      if (line.id == null) continue;
      map[line.id] = remainingQuotationQty(line);
    }
    return map;
  }, [quotation]);

  useEffect(() => {
    setQtyById(remainingById);
  }, [remainingById]);

  const open = Boolean(quotation && mode);
  const title =
    mode === 'order' ? t('common.confirmToOrder') : t('common.confirmConvert');

  const canSubmit = (quotation?.items ?? []).some((line) => {
    if (line.id == null) return false;
    const remaining = remainingById[line.id] ?? 0;
    const qty = qtyById[line.id] ?? remaining;
    return qty > 0;
  });

  const submit = () => {
    if (!quotation) return;
    try {
      const items = buildConvertItemsPayload(quotation.items ?? [], qtyById);
      if (items.length === 0) return;
      onConfirm(items);
    } catch (err) {
      // Parent already shows convert errors; keep dialog open on over-qty.
      void err;
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('common.convertPartialHint')}
          </Typography>
          {error ? (
            <Typography color="error" variant="body2">
              {error}
            </Typography>
          ) : null}
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('common.quotedQty')}</TableCell>
                <TableCell align="right">{t('common.alreadyConverted')}</TableCell>
                <TableCell align="right">{t('common.convertQty')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(quotation?.items ?? []).map((line) => {
                if (line.id == null) return null;
                const remaining = remainingById[line.id] ?? 0;
                return (
                  <TableRow key={line.id}>
                    <TableCell>{line.productName ?? line.product}</TableCell>
                    <TableCell align="right">{line.quantity}</TableCell>
                    <TableCell align="right">{line.convertedQuantity ?? 0}</TableCell>
                    <TableCell align="right">
                      <TextField
                        size="small"
                        type="number"
                        value={qtyById[line.id] ?? remaining}
                        onChange={(e) => {
                          const id = line.id as number;
                          const v = Math.max(0, toNumber(e.target.value) || 0);
                          setQtyById((prev) => ({ ...prev, [id]: Math.min(v, remaining) }));
                        }}
                        sx={{ width: 100 }}
                        inputProps={{
                          min: 0,
                          max: remaining,
                          step: '0.001',
                          'aria-label': t('common.convertQty'),
                        }}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={pending || !canSubmit} onClick={submit}>
          {mode === 'order' ? t('common.toOrder') : t('common.convert')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
