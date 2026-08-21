import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';
import { INDIAN_STATES } from '@/utils/indianStates';

type Props = {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  required?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  helperText?: string;
  error?: boolean;
};

/**
 * Indian state/UT dropdown for party and company forms (BUG-631).
 * Keeps legacy free-text values selectable so edit forms still display them.
 */
export function StateSelect({
  value,
  onChange,
  label = t('auth.state'),
  required,
  disabled,
  fullWidth = true,
  helperText,
  error,
}: Props) {
  const options =
    value && !INDIAN_STATES.includes(value as (typeof INDIAN_STATES)[number])
      ? [value, ...INDIAN_STATES]
      : [...INDIAN_STATES];

  return (
    <TextField
      select
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      required={required}
      disabled={disabled}
      fullWidth={fullWidth}
      helperText={helperText}
      error={error}
    >
      <MenuItem value="">
        <em>—</em>
      </MenuItem>
      {options.map((state) => (
        <MenuItem key={state} value={state}>
          {state}
        </MenuItem>
      ))}
    </TextField>
  );
}
