import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import type { Gstr3bSummary } from '@/pages/reports/gstr3bSummary';

function Line({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="body2" color={muted ? 'text.secondary' : undefined}>{label}</Typography>
      <Typography variant="body2" fontWeight={muted ? 400 : 600}>{value}</Typography>
    </Stack>
  );
}

/** GSTR-3B worksheet: net payable straight from the payload, then every ITC line that feeds it. */
export function Gstr3bPanel({ summary }: { summary: Gstr3bSummary }) {
  const s = summary;
  const reversedTotal = s.reversed.total + s.ineligible.total;
  return (
    <Stack spacing={2}>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>{t('gstHonesty.worksheetNet')}</Typography>
        {!s.hasMatched2b ? (
          <Alert severity="warning" sx={{ mt: 1 }}>{t('gstHonesty.provisionalNo2b')}</Alert>
        ) : null}
        {s.netPayable === null ? (
          <Typography variant="h6" sx={{ my: 1 }} color="text.secondary">{t('gstr3b.netNotAvailable')}</Typography>
        ) : (
          <Typography variant="h4" fontWeight={700} sx={{ my: 1 }}>{formatMoney(s.payableToShow)}</Typography>
        )}
        <Typography variant="body2" color="text.secondary">{t('gstHonesty.booksAidNotChallan')}</Typography>
        <Stack spacing={0.5} sx={{ mt: 1 }}>
          <Line label={t('gstr3b.outwardTax')} value={formatMoney(s.outwardTax)} muted />
          <Line label={t('gstr3b.rcmTax')} value={formatMoney(s.rcmTax)} muted />
          <Line label={t('gstr3b.itcClaimed')} value={`− ${formatMoney(s.claimableItc)}`} muted />
        </Stack>
        {s.carryForward > 0 ? (
          <Typography variant="body2" color="text.secondary" fontWeight={600} sx={{ mt: 0.5 }}>
            {t('gstHonesty.itcCreditCarry', { amount: formatMoney(s.carryForward) })}
          </Typography>
        ) : null}
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
        <Typography variant="subtitle1" fontWeight={700} gutterBottom>{t('gstr3b.itcTitle')}</Typography>
        <Stack spacing={0.5}>
          <Line label={t('gstr3b.itcBooks')} value={formatMoney(s.booksItc)} />
          <Line label={t('gstr3b.itcClaimable')} value={formatMoney(s.claimableItc)} />
          <Line label={t('gstr3b.itcUnreviewed')} value={formatMoney(s.unreviewedItc)} muted />
          <Line label={t('gstr3b.itcRcm')} value={formatMoney(s.rcmProvisionalItc)} muted />
          <Line label={t('gstr3b.itcImport')} value={formatMoney(s.importItc)} muted />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }} data-testid="itc-4b">
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
          <Typography variant="subtitle1" fontWeight={700}>{t('gstr3b.itc4bTitle')}</Typography>
          {s.needsCaConfirmation ? <Chip size="small" color="warning" label={t('gstr3b.caConfirm')} /> : null}
        </Stack>
        <Stack spacing={0.5}>
          <Line
            label={t('gstr3b.itc4bReversed', { count: s.reversed.count })}
            value={formatMoney(s.reversed.total)}
          />
          <Line
            label={t('gstr3b.itc4bIneligible', { count: s.ineligible.count })}
            value={formatMoney(s.ineligible.total)}
          />
          <Line label={t('gstr3b.itc4bTotal')} value={formatMoney(reversedTotal)} />
          {s.gstr2bFlaggedCount > 0 ? (
            <Typography variant="caption" color="text.secondary">
              {t('gstr3b.itc4bFlaggedOn2b', { count: s.gstr2bFlaggedCount })}
            </Typography>
          ) : null}
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{t('gstr3b.itc4bNote')}</Typography>
      </Paper>
    </Stack>
  );
}
