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
}: {
  value: NoteReason;
  onChange: (v: NoteReason) => void;
  disabled?: boolean;
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
      {REASONS.map((r) => (
        <MenuItem key={r} value={r}>
          {t(`phase1.reason.${r}`)}
        </MenuItem>
      ))}
    </TextField>
  );
}
