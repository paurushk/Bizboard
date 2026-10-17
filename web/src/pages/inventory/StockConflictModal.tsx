import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import type { LineResolution, QtyConflict } from '@/pages/inventory/godownConflict';

const CHOICES: Array<{ value: LineResolution; labelKey: string }> = [
  { value: 'ADJUST_FOR_MOVEMENTS', labelKey: 'inventory.conflictChoiceAdjust' },
  { value: 'KEEP_SERVER', labelKey: 'inventory.conflictChoiceServer' },
  { value: 'KEEP_LOCAL', labelKey: 'inventory.conflictChoiceLocal' },
];

/**
 * Lines whose stock moved after the sheet was made. Each gets its own answer; the default adjusts the
 * count for the sales and receipts that happened while it was being taken, so nothing is counted twice.
 * Mount it with a key built from the conflicting lines so the answers start fresh for each set.
 */
export function StockConflictModal({
  open,
  conflicts,
  onResolve,
  onCancel,
}: {
  open: boolean;
  conflicts: QtyConflict[];
  onResolve: (resolutions: Record<number, LineResolution>) => void;
  onCancel: () => void;
}) {
  const [choices, setChoices] = useState<Record<number, LineResolution>>({});
  const choiceOf = (lineId: number): LineResolution => choices[lineId] ?? 'ADJUST_FOR_MOVEMENTS';
  const setAll = (value: LineResolution) =>
    setChoices(Object.fromEntries(conflicts.map((row) => [row.lineId, value])));

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>{t('inventory.conflictTitle')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('inventory.conflictBody')}
        </Typography>
        {conflicts.length > 1 ? (
          <TextField
            select
            size="small"
            fullWidth
            label={t('inventory.conflictApplyAll')}
            value=""
            onChange={(e) => setAll(e.target.value as LineResolution)}
            sx={{ mb: 2 }}
          >
            {CHOICES.map((choice) => (
              <MenuItem key={choice.value} value={choice.value}>
                {t(choice.labelKey)}
              </MenuItem>
            ))}
          </TextField>
        ) : null}
        <Stack spacing={1.5}>
          {conflicts.map((row) => (
            <Stack key={row.lineId} spacing={0.5}>
              <Typography variant="body2">
                <strong>{row.productName}</strong>: {t('inventory.conflictServerQty')} {row.serverQty} ·{' '}
                {t('inventory.conflictLocalQty')} {row.localQty}
              </Typography>
              <TextField
                select
                size="small"
                fullWidth
                label={t('inventory.conflictWhatToDo')}
                value={choiceOf(row.lineId)}
                onChange={(e) => setChoices((cur) => ({ ...cur, [row.lineId]: e.target.value as LineResolution }))}
              >
                {CHOICES.map((choice) => (
                  <MenuItem key={choice.value} value={choice.value}>
                    {t(choice.labelKey)}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
        <Button
          variant="contained"
          onClick={() => onResolve(Object.fromEntries(conflicts.map((row) => [row.lineId, choiceOf(row.lineId)])))}
        >
          {t('inventory.conflictPost')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
