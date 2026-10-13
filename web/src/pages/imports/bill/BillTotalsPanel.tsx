import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import type { BillTotals } from '@/types/domain';

type Props = {
  totals?: BillTotals;
  /** Edits not yet saved: the figures below are from the last save. */
  updating?: boolean;
  priceMode: 'EXCLUSIVE' | 'INCLUSIVE';
  additionalCharges: string;
  invoiceDiscount: string;
  printedTotal: string;
  onPriceMode: (value: 'EXCLUSIVE' | 'INCLUSIVE') => void;
  onAdditionalCharges: (value: string) => void;
  onInvoiceDiscount: (value: string) => void;
  onPrintedTotal: (value: string) => void;
};

function Figure({ label, value }: { label: string; value?: string }) {
  return (
    <Stack>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={600}>
        {value ?? '—'}
      </Typography>
    </Stack>
  );
}

/**
 * Header-level money on the bill (tax mode, freight, bill discount, printed
 * total) and the totals the draft will have, computed by the server with the
 * same rules as the draft so the reviewer can compare against the print.
 */
export function BillTotalsPanel({
  totals,
  updating,
  priceMode,
  additionalCharges,
  invoiceDiscount,
  printedTotal,
  onPriceMode,
  onAdditionalCharges,
  onInvoiceDiscount,
  onPrintedTotal,
}: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap">
          <TextField
            select
            size="small"
            label={t('billUpload.priceModeLabel')}
            value={priceMode}
            onChange={(e) => onPriceMode(e.target.value as 'EXCLUSIVE' | 'INCLUSIVE')}
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="EXCLUSIVE">{t('billUpload.priceModeExclusive')}</MenuItem>
            <MenuItem value="INCLUSIVE">{t('billUpload.priceModeInclusive')}</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="number"
            label={t('billUpload.additionalCharges')}
            value={additionalCharges}
            onChange={(e) => onAdditionalCharges(e.target.value)}
            sx={{ width: 190 }}
          />
          <TextField
            size="small"
            type="number"
            label={t('billUpload.invoiceDiscount')}
            value={invoiceDiscount}
            onChange={(e) => onInvoiceDiscount(e.target.value)}
            sx={{ width: 160 }}
          />
          <TextField
            size="small"
            type="number"
            label={t('billUpload.printedTotal')}
            value={printedTotal}
            onChange={(e) => onPrintedTotal(e.target.value)}
            sx={{ width: 200 }}
          />
        </Stack>
        <Typography variant="subtitle2">
          {t('billUpload.totalsTitle')}
          {updating ? (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }} role="status">
              {t('billUpload.totalsUpdating')}
            </Typography>
          ) : null}
        </Typography>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap sx={{ opacity: updating ? 0.55 : 1 }} aria-busy={updating || undefined}>
          <Figure label={t('billUpload.totTaxable')} value={totals?.taxable} />
          {totals?.taxType === 'INTER' ? (
            <Figure label={t('billUpload.totIgst')} value={totals.igst} />
          ) : totals?.cgst != null ? (
            <>
              <Figure label={t('billUpload.totCgst')} value={totals.cgst} />
              <Figure label={t('billUpload.totSgst')} value={totals.sgst} />
            </>
          ) : (
            <Figure label={t('billUpload.totGst')} value={totals?.gst} />
          )}
          {totals && Number(totals.cess) > 0 ? <Figure label={t('billUpload.totCess')} value={totals.cess} /> : null}
          {totals && Number(totals.charges) > 0 ? <Figure label={t('billUpload.totCharges')} value={totals.charges} /> : null}
          {totals && Number(totals.invoiceDiscount) > 0 ? (
            <Figure label={t('billUpload.totDiscount')} value={totals.invoiceDiscount} />
          ) : null}
          <Figure label={t('billUpload.totTotal')} value={totals?.grandTotal} />
        </Stack>
        {totals?.taxType === 'ASSUMED_INTRA' ? (
          <Typography variant="caption" color="text.secondary">
            {t('billUpload.taxSplitAssumed')}
          </Typography>
        ) : null}
        {totals?.error ? (
          <Typography variant="caption" color="error">
            {totals.error}
          </Typography>
        ) : null}
        {totals?.printedDifference != null ? (
          <Chip
            size="small"
            sx={{ alignSelf: 'flex-start' }}
            color={totals.printedMatches ? 'success' : 'warning'}
            label={
              totals.printedMatches
                ? t('billUpload.totMatches')
                : t('billUpload.totDifference', { amount: totals.printedDifference })
            }
          />
        ) : null}
      </Stack>
    </Paper>
  );
}
