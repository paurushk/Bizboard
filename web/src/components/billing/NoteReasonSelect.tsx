import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';
import type { NoteReason } from '@/types/domain';

const REASONS: NoteReason[] = [
  'SALES_RETURN',
  'POST_SALE_DISCOUNT',
  'DEFICIENCY_IN_SERVICE',
  'CORRECTION_OF_INVOICE',
  'OTHERS',
];

export function NoteReasonSelect({
  value,
  onChange,
  disabled,
  allowSalesReturn = false,
}: {
  value: NoteReason;
  onChange: (v: NoteReason) => void;
  disabled?: boolean;
  /**
   * SALES_RETURN belongs to the credit note a sales return issues (stock is restored
   * there). It is offered only when that is what is being shown (CN-01).
   */
  allowSalesReturn?: boolean;
}) {
  return (
    <TextField
      select
      label={t('common.reason')}
      value={value}
      onChange={(e) => onChange(e.target.value as NoteReason)}
      disabled={disabled}
      fullWidth
    >
      {REASONS.filter((r) => r !== 'SALES_RETURN' || allowSalesReturn || value === 'SALES_RETURN').map((r) => (
        <MenuItem key={r} value={r}>
          {t(`phase1.reason.${r}`)}
        </MenuItem>
      ))}
    </TextField>
  );
}
