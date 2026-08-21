import { type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Checkbox from '@mui/material/Checkbox';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { CompactField, NumericField } from '@/components/billing';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import type { InvoiceDiscountMode } from '@/utils/tax';

export type DocumentTotals = {
  taxableTotal: number;
  cgstTotal: number;
  sgstTotal: number;
  igstTotal: number;
  roundOff: number;
  grandTotal: number;
};

function SummaryRow({
  label,
  value,
  bold,
}: {
  label: string;
  value: ReactNode;
  bold?: boolean;
}) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
      <Typography fontWeight={bold ? 700 : 400}>{label}</Typography>
      {typeof value === 'string' || typeof value === 'number' ? (
        <Typography fontWeight={bold ? 700 : 500}>{value}</Typography>
      ) : (
        value
      )}
    </Box>
  );
}

export function DocumentTaxSummary({
  totals,
  displayGrandTotal,
  totalLabel,
  additionalCharges,
  onAdditionalChargesChange,
  invoiceDiscount,
  onInvoiceDiscountChange,
  invoiceDiscountMode,
  onInvoiceDiscountModeChange,
  autoRoundOff,
  onAutoRoundOffChange,
  posKnown,
  partyRole = 'customer',
  isCompletedEdit,
  canAmendMoney,
  extraAlerts,
  children,
}: {
  totals: DocumentTotals;
  displayGrandTotal?: number;
  totalLabel?: string;
  additionalCharges: number;
  onAdditionalChargesChange: (n: number) => void;
  invoiceDiscount: number;
  onInvoiceDiscountChange: (n: number) => void;
  invoiceDiscountMode: InvoiceDiscountMode;
  onInvoiceDiscountModeChange: (mode: InvoiceDiscountMode) => void;
  autoRoundOff: boolean;
  onAutoRoundOffChange: (checked: boolean) => void;
  posKnown: boolean;
  partyRole?: 'customer' | 'supplier';
  isCompletedEdit: boolean;
  canAmendMoney: boolean;
  extraAlerts?: ReactNode;
  children?: ReactNode;
}) {
  const grand = displayGrandTotal ?? totals.grandTotal;
  return (
    <Paper sx={{ p: 2, width: '100%', maxWidth: 420, ml: { md: 'auto' } }}>
      <Stack spacing={1.25}>
        <SummaryRow
          label={`+ ${t('billing.additionalCharges')}`}
          value={
            <NumericField
              value={additionalCharges}
              onValueChange={onAdditionalChargesChange}
              min={0}
              decimals={2}
              fullWidth={false}
              disabled={isCompletedEdit && !canAmendMoney}
              helperText={t('billing.additionalChargesHint')}
              InputProps={{
                startAdornment: <InputAdornment position="start">₹</InputAdornment>,
              }}
              sx={{ maxWidth: 140 }}
            />
          }
        />
        <SummaryRow label={t('billing.taxableAmount')} value={formatMoney(totals.taxableTotal)} />
        {totals.cgstTotal > 0 ? (
          <SummaryRow label={t('billing.cgst')} value={formatMoney(totals.cgstTotal)} />
        ) : null}
        {totals.sgstTotal > 0 ? (
          <SummaryRow label={t('billing.sgst')} value={formatMoney(totals.sgstTotal)} />
        ) : null}
        {totals.igstTotal > 0 ? (
          <SummaryRow label={t('billing.igst')} value={formatMoney(totals.igstTotal)} />
        ) : null}
        {totals.igstTotal > 0 ? (
          <Typography variant="caption" color="text.secondary">
            {t('billing.taxInterStateHint')}
          </Typography>
        ) : totals.cgstTotal > 0 || totals.sgstTotal > 0 ? (
          <Typography variant="caption" color="text.secondary">
            {t('billing.taxIntraStateHint')}
          </Typography>
        ) : null}
        <SummaryRow
          label={t('billing.invoiceDiscount')}
          value={
            <Stack direction="row" spacing={1} alignItems="center">
              <CompactField
                select
                value={invoiceDiscountMode}
                onChange={(e) => onInvoiceDiscountModeChange(e.target.value as InvoiceDiscountMode)}
                disabled={isCompletedEdit && !canAmendMoney}
                sx={{ minWidth: 180 }}
              >
                <MenuItem value="AFTER_TAX">{t('billing.invoiceDiscountAfterTax')}</MenuItem>
                <MenuItem value="BEFORE_TAX">{t('billing.invoiceDiscountBeforeTax')}</MenuItem>
              </CompactField>
              <NumericField
                value={invoiceDiscount}
                onValueChange={onInvoiceDiscountChange}
                min={0}
                decimals={2}
                fullWidth={false}
                disabled={isCompletedEdit && !canAmendMoney}
                InputProps={{
                  startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                }}
                sx={{ maxWidth: 120 }}
              />
            </Stack>
          }
        />
        {!posKnown ? (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {partyRole === 'supplier'
              ? t('billing.placeOfSupplyRequiredSupplier')
              : t('billing.placeOfSupplyRequired')}
          </Alert>
        ) : null}
        {extraAlerts}
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <FormControlLabel
            control={
              <Checkbox
                checked={autoRoundOff}
                onChange={(e) => onAutoRoundOffChange(e.target.checked)}
                size="small"
              />
            }
            label={t('billing.autoRoundOff')}
          />
          <Typography variant="body2">{formatMoney(totals.roundOff)}</Typography>
        </Stack>
        <Divider />
        <SummaryRow label={totalLabel ?? t('billing.totalAmount')} value={formatMoney(grand)} bold />
        {children}
      </Stack>
    </Paper>
  );
}
