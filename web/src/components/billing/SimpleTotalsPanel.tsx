import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

interface Totals {
  subtotal: number;
  cgstTotal: number;
  sgstTotal: number;
  igstTotal: number;
  cessTotal?: number;
  roundOff: number;
  grandTotal: number;
}

export function SimpleTotalsPanel({ totals }: { totals: Totals }) {
  return (
    <Paper sx={{ p: 2, maxWidth: 360, ml: 'auto' }}>
      <Stack spacing={0.5}>
        <Row label={t('billing.subtotal')} value={totals.subtotal} />
        {totals.cgstTotal > 0 ? <Row label={t('billing.cgst')} value={totals.cgstTotal} /> : null}
        {totals.sgstTotal > 0 ? <Row label={t('billing.sgst')} value={totals.sgstTotal} /> : null}
        {totals.igstTotal > 0 ? <Row label={t('billing.igst')} value={totals.igstTotal} /> : null}
        {(totals.cessTotal ?? 0) > 0 ? <Row label={t('billing.cess')} value={totals.cessTotal ?? 0} /> : null}
        {totals.roundOff !== 0 ? (
          <Row label={t('billing.roundOff')} value={totals.roundOff} />
        ) : null}
        <Row label={t('billing.grandTotal')} value={totals.grandTotal} bold />
      </Stack>
    </Paper>
  );
}

function Row({ label, value, bold }: { label: string; value: number; bold?: boolean }) {
  return (
    <Stack direction="row" justifyContent="space-between">
      <Typography variant="body2" fontWeight={bold ? 600 : 400}>
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={bold ? 600 : 400}>
        {formatMoney(value)}
      </Typography>
    </Stack>
  );
}
