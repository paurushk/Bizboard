import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import type { QtyConflict } from '@/pages/inventory/godownConflict';

export function StockConflictModal({
  open,
  conflicts,
  onKeepServer,
  onKeepLocal,
  onCancel,
}: {
  open: boolean;
  conflicts: QtyConflict[];
  onKeepServer: () => void;
  onKeepLocal: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>{t('inventory.conflictTitle')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('inventory.conflictBody')}
        </Typography>
        <Stack spacing={1}>
          {conflicts.map((row) => (
            <Typography key={row.lineId} variant="body2">
              {row.productName}: {t('inventory.conflictServerQty')} {row.serverQty} ·{' '}
              {t('inventory.conflictLocalQty')} {row.localQty}
            </Typography>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
        <Button onClick={onKeepServer}>{t('inventory.keepServer')}</Button>
        <Button variant="contained" onClick={onKeepLocal}>
          {t('inventory.keepLocal')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
