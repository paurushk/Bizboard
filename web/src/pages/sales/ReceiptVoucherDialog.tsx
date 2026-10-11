import { useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { getErrorMessage } from '@/api/client';
import { fetchReceiptVoucher, type ReceiptVoucherLang, type ReceiptVoucherLayout } from '@/api/resources';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { receiptStatusChips } from '@/pages/sales/receiptStatus';
import { t, useLocale } from '@/i18n';
import type { CustomerReceipt } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { printBlob, triggerBlobDownload } from '@/utils/blob';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" component="div">
        {children}
      </Typography>
    </>
  );
}

/** Read-only receipt voucher with the invoices it was applied to, plus print / PDF download. */
export function ReceiptVoucherDialog({
  receipt,
  onClose,
  onEdit,
  onSend,
  onManage,
}: {
  receipt: CustomerReceipt | null;
  onClose: () => void;
  /** Offered only to people who may change receipts; each opens its own dialog on the page. */
  onEdit?: (receipt: CustomerReceipt) => void;
  onSend?: (receipt: CustomerReceipt) => void;
  onManage?: (receipt: CustomerReceipt) => void;
}) {
  const locale = useLocale();
  const [layout, setLayout] = useState<ReceiptVoucherLayout>('A4');
  // Follows the app language until the user picks one for this voucher.
  const [pickedLang, setPickedLang] = useState<ReceiptVoucherLang | null>(null);
  const lang: ReceiptVoucherLang = pickedLang ?? (locale === 'hi' ? 'hi' : 'en');
  const [busy, setBusy] = useState<'print' | 'download' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);

  const run = async (kind: 'print' | 'download') => {
    if (!receipt) return;
    setBusy(kind);
    setError(null);
    setErrorSource(null);
    try {
      const blob = await fetchReceiptVoucher(receipt.id, layout, lang);
      if (kind === 'print') printBlob(blob);
      else triggerBlobDownload(blob, `receipt-${receipt.number ?? receipt.id}.pdf`);
    } catch (err) {
      setError(getErrorMessage(err) || t('receipts.voucherFailed'));
      setErrorSource(err);
    } finally {
      setBusy(null);
    }
  };

  const close = () => {
    setError(null);
    setErrorSource(null);
    onClose();
  };

  const live = receipt?.status !== 'VOIDED' && receipt?.status !== 'REFUNDED';
  // What the receipt still holds as an advance, as the server counts it (TDS in, refunds out).
  const advance = receipt ? Math.max(0, toNumber(receipt.unallocated)) : 0;
  const lines = receipt?.allocationLines ?? [];
  const refunds = (receipt?.advanceRefunds ?? []).filter((row) => row.status === 'POSTED');
  const unappliedDiscount =
    receipt && toNumber(receipt.settlementDiscount) > 0
      ? toNumber(receipt.settlementDiscount) - lines.reduce((sum, line) => sum + toNumber(line.discountApplied), 0)
      : 0;

  return (
    <Dialog open={receipt != null} onClose={close} fullWidth maxWidth="sm" aria-labelledby="receipt-voucher-title">
      <DialogTitle id="receipt-voucher-title">
        <Box display="flex" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap">
          <span>
            {t('receipts.voucher')} {receipt?.number ?? receipt?.id}
          </span>
          <Stack direction="row" spacing={0.5}>
            {receipt
              ? receiptStatusChips(receipt).map((chip) => (
                  <Chip key={chip.key} size="small" label={chip.label} color={chip.color} />
                ))
              : null}
          </Stack>
        </Box>
      </DialogTitle>
      <DialogContent>
        {receipt ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} error={errorSource} /> : null}
            <Box display="grid" gridTemplateColumns="max-content 1fr" columnGap={3} rowGap={0.75}>
              <Row label={t('common.date')}>{receipt.receiptDate}</Row>
              <Row label={t('billing.customer')}>{receipt.customerName}</Row>
              <Row label={t('receipts.mode')}>{receipt.mode}</Row>
              <Row label={t('common.amount')}>
                <strong>{formatMoney(receipt.amount)}</strong>
              </Row>
              <Row label={t('receipts.allocated')}>{formatMoney(receipt.allocated)}</Row>
              {toNumber(receipt.tdsDeducted) > 0 ? (
                <Row label={t('receipts.voucherTds')}>
                  {formatMoney(receipt.tdsDeducted ?? 0)}
                  {receipt.tdsSection ? ` (${receipt.tdsSection})` : ''}
                </Row>
              ) : null}
              {toNumber(receipt.settlementDiscount) > 0 ? (
                <Row label={t('receipts.voucherDiscount')}>
                  {unappliedDiscount > 0.005
                    ? t('receipts.discountPending', { amount: formatMoney(receipt.settlementDiscount ?? 0) })
                    : formatMoney(receipt.settlementDiscount ?? 0)}
                </Row>
              ) : null}
              {toNumber(receipt.refunded) > 0 ? (
                <Row label={t('receipts.refundedLabel')}>{formatMoney(receipt.refunded ?? 0)}</Row>
              ) : null}
              {live && advance > 0 ? (
                <Row label={t('receipts.advanceLabel')}>
                  <Typography component="span" variant="body2" color="info.main">
                    {formatMoney(advance)}
                  </Typography>
                </Row>
              ) : null}
              {receipt.utr ? <Row label={t('receipts.utr')}>{receipt.utr}</Row> : null}
              {receipt.mode === 'CHEQUE' && receipt.chequeNumber ? (
                <Row label={t('receipts.cheque')}>
                  {[receipt.chequeNumber, receipt.chequeBankName].filter(Boolean).join(' · ')}
                </Row>
              ) : null}
              {receipt.bankAccountName ? <Row label={t('sweep.depositToBank')}>{receipt.bankAccountName}</Row> : null}
              {receipt.reconciled ? <Row label={t('receipts.reconciled')}>{t('receipts.reconciledNote')}</Row> : null}
              {receipt.status === 'VOIDED' ? (
                <>
                  <Row label={t('receipts.voidReason')}>{receipt.voidReason || '—'}</Row>
                  {receipt.voidedByName ? (
                    <Row label={t('receipts.voidedByLabel')}>{receipt.voidedByName}</Row>
                  ) : null}
                </>
              ) : null}
            </Box>
            {receipt.reviewFlags?.includes('invoice_returned_after_payment') ? (
              <Alert severity="warning">{t('receipts.reviewInvoiceReturned')}</Alert>
            ) : null}
            <Divider />
            <Box>
              <Typography variant="subtitle2" component="h3" gutterBottom>
                {t('receipts.appliedTo')}
              </Typography>
              {lines.length === 0 ? (
                toNumber(receipt.allocated) === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('receipts.notApplied')}
                  </Typography>
                ) : null
              ) : (
                <Box display="grid" gridTemplateColumns="1fr max-content" columnGap={3} rowGap={0.5}>
                  {lines.map((line, index) => (
                    <Box key={`${line.salesInvoice ?? 'x'}-${index}`} display="contents">
                      <Typography variant="body2">{line.invoiceNumber || `#${line.salesInvoice}`}</Typography>
                      <Typography variant="body2" align="right">
                        {formatMoney(line.amount)}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
            {refunds.length > 0 ? (
              <Box>
                <Typography variant="subtitle2" component="h3" gutterBottom>
                  {t('receipts.refundsTitle')}
                </Typography>
                <Box display="grid" gridTemplateColumns="1fr max-content" columnGap={3} rowGap={0.5}>
                  {refunds.map((refund) => (
                    <Box key={refund.id} display="contents">
                      <Typography variant="body2">
                        {refund.number} · {refund.refundDate} · {refund.mode}
                      </Typography>
                      <Typography variant="body2" align="right">
                        {formatMoney(refund.amount)}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Box>
            ) : null}
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
        <TextField
          select
          size="small"
          label={t('receipts.voucherLayout')}
          value={layout}
          onChange={(e) => setLayout(e.target.value as ReceiptVoucherLayout)}
          sx={{ minWidth: 150, mr: 'auto' }}
        >
          <MenuItem value="A4">{t('receipts.voucherA4')}</MenuItem>
          <MenuItem value="THERMAL">{t('receipts.voucherThermal')}</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label={t('receipts.voucherLanguage')}
          value={lang}
          onChange={(e) => setPickedLang(e.target.value as ReceiptVoucherLang)}
          sx={{ minWidth: 130 }}
        >
          <MenuItem value="en">{t('receipts.voucherLangEn')}</MenuItem>
          <MenuItem value="hi">{t('receipts.voucherLangHi')}</MenuItem>
        </TextField>
        {receipt && live && onManage ? (
          <Button onClick={() => onManage(receipt)}>{t('receipts.actionManage')}</Button>
        ) : null}
        {receipt && live && onEdit ? <Button onClick={() => onEdit(receipt)}>{t('receipts.actionEdit')}</Button> : null}
        {receipt && live && onSend ? <Button onClick={() => onSend(receipt)}>{t('receipts.actionSend')}</Button> : null}
        <Button onClick={() => void run('download')} disabled={busy != null}>
          {t('receipts.voucherDownload')}
        </Button>
        <Button variant="contained" onClick={() => void run('print')} disabled={busy != null}>
          {t('receipts.voucherPrint')}
        </Button>
        <Button onClick={close}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
