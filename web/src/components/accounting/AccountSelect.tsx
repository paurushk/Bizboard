import { useMemo } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';
import type { AccountingAccount } from '@/types/domain';
import { accountLabel, selectableAccounts } from './accountOptions';

/**
 * Searchable account picker (code or name), shared by the accounting screens (ACS-00).
 * `value` is the account id as a string, "" for none.
 */
export function AccountSelect({
  accounts,
  value,
  onChange,
  label,
  allowInactive = false,
  types,
  size,
  sx,
  disabled,
  error,
  helperText,
}: {
  accounts: AccountingAccount[] | undefined;
  value: string;
  onChange: (id: string) => void;
  label: string;
  allowInactive?: boolean;
  types?: string[];
  size?: 'small' | 'medium';
  sx?: object;
  disabled?: boolean;
  error?: boolean;
  helperText?: string;
}) {
  const options = useMemo(() => selectableAccounts(accounts, { allowInactive, types }), [accounts, allowInactive, types]);
  // A saved value may point at an account that is now inactive: keep it visible so the field never looks empty.
  const selected = useMemo(
    () => (accounts ?? []).find((a) => String(a.id) === value) ?? null,
    [accounts, value],
  );
  const merged = selected && !options.includes(selected) ? [selected, ...options] : options;
  return (
    <Autocomplete
      size={size}
      sx={sx}
      disabled={disabled}
      options={merged}
      value={selected}
      onChange={(_event, next) => onChange(next ? String(next.id) : '')}
      getOptionLabel={accountLabel}
      isOptionEqualToValue={(option, v) => option.id === v.id}
      noOptionsText={t('phase.accountNone')}
      renderOption={(props, option) => (
        <li {...props} key={option.id}>
          {accountLabel(option)}
          {option.isActive === false ? ` · ${t('phase.journalAccountInactive')}` : ''}
        </li>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          error={error}
          helperText={helperText}
          placeholder={t('phase.accountSearch')}
        />
      )}
    />
  );
}
