import { useState } from 'react';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';
import {
  PHONE_COUNTRIES,
  cleanNationalNumber,
  countryForCallingCode,
  findPhoneCountry,
  isValidNationalNumber,
  joinPhone,
  splitPhone,
  type PhoneCountry,
} from '@/utils/phone';

/** What to tell the user when the number does not fit `country`. */
export function phoneErrorMessage(country: PhoneCountry): string {
  if (country.iso === 'IN') return t('phoneField.invalidIndia');
  if (country.min === country.max) return t('phoneField.invalidExact', { n: country.min });
  return t('phoneField.invalidLength', { min: country.min, max: country.max });
}

type Props = {
  /** E.164 (`+919876543210`) or blank. */
  value: string;
  /** Called with E.164, or '' when the number box is empty. */
  onChange: (value: string) => void;
  onBlur?: () => void;
  label?: string;
  required?: boolean;
  /** Say "Optional" in the hint instead of in the label (keeps the label short on phones). */
  optional?: boolean;
  disabled?: boolean;
  /** Server or form error; shown in place of the field's own check. */
  error?: string;
  name?: string;
};

/**
 * Mobile number as a country-code picker plus the national number.
 * India (+91) is the default; the stored value is always E.164.
 */
export function PhoneField({
  value,
  onChange,
  onBlur,
  label = t('auth.phone'),
  required,
  optional,
  disabled,
  error,
  name = 'phone',
}: Props) {
  const [{ iso, national }, setParts] = useState(() => splitPhone(value));
  // A calling code being typed by hand (`+`, `+9`, `+97`) before it names a country.
  const [typedCode, setTypedCode] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // Follow outside resets (form reset, loaded record) without fighting the user's typing.
  const [seenValue, setSeenValue] = useState(value);
  if (value !== seenValue) {
    setSeenValue(value);
    if (value !== joinPhone(iso, national)) {
      setParts(splitPhone(value));
      setTypedCode(null);
    }
  }

  const update = (nextIso: string, nextNational: string) => {
    setParts({ iso: nextIso, national: nextNational });
    onChange(joinPhone(nextIso, nextNational));
  };

  const country = findPhoneCountry(iso);
  const ownError =
    touched && national && !isValidNationalNumber(country, national) ? phoneErrorMessage(country) : undefined;
  const shownError = error || ownError;
  const hint = [optional ? t('phoneField.optional') : null, country.iso === 'IN' ? t('phoneField.hintIndia') : null]
    .filter(Boolean)
    .join(' · ') || undefined;

  return (
    <Stack direction="row" spacing={1} alignItems="flex-start">
      <TextField
        select
        label={t('phoneField.countryCode')}
        value={iso}
        disabled={disabled}
        onChange={(e) => {
          // Keep every digit: a wrong pick and back must not cost the user part of the number.
          setTypedCode(null);
          update(findPhoneCountry(e.target.value).iso, national);
        }}
        sx={{ width: 96, flexShrink: 0 }}
        SelectProps={{
          renderValue: (selected) => `+${findPhoneCountry(String(selected)).dial}`,
        }}
      >
        {PHONE_COUNTRIES.map((c) => (
          <MenuItem key={c.iso} value={c.iso}>
            {c.name} (+{c.dial})
          </MenuItem>
        ))}
      </TextField>
      <TextField
        fullWidth
        name={name}
        label={label}
        value={typedCode ?? national}
        required={required}
        disabled={disabled}
        type="tel"
        autoComplete="tel-national"
        inputProps={{ inputMode: 'tel' }}
        placeholder={country.iso === 'IN' ? '98765 43210' : undefined}
        error={Boolean(shownError)}
        helperText={shownError ?? hint}
        onChange={(e) => {
          const raw = e.target.value;
          const international = /^\s*\+/.test(raw);
          // A typed or pasted international number may name another country (+971 …).
          const match = international ? countryForCallingCode(raw) : undefined;
          const codeDigits = raw.replace(/\D/g, '');
          // Calling codes are at most 3 digits; until one matches, show what was typed.
          if (international && !match && codeDigits.length <= 3) {
            setTypedCode(`+${codeDigits}`);
            update(iso, '');
            return;
          }
          setTypedCode(null);
          const nextCountry = match ?? country;
          update(nextCountry.iso, cleanNationalNumber(raw, nextCountry));
        }}
        onBlur={() => {
          setTouched(true);
          onBlur?.();
        }}
      />
    </Stack>
  );
}
