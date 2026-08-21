import { useEffect, useState, type ComponentProps } from 'react';
import TextField from '@mui/material/TextField';
import { formatMoney, roundMoney } from '@/utils/money';

export function CompactField(props: ComponentProps<typeof TextField>) {
  return <TextField size="small" variant="outlined" fullWidth {...props} />;
}

function formatNumericText(value: number, decimals?: number): string {
  if (!Number.isFinite(value)) return '';
  if (value === 0) return '';
  if (decimals != null) return String(roundMoney(value));
  return String(value);
}

function parseNumericText(
  text: string,
  opts: { min: number; emptyAs: number; decimals?: number },
): number {
  const trimmed = text.trim();
  if (trimmed === '' || trimmed === '.') return opts.emptyAs;
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return opts.emptyAs;
  const clamped = Math.max(opts.min, n);
  return opts.decimals != null ? roundMoney(clamped) : clamped;
}

/** Text decimal field — avoids leading-zero glitch of controlled type="number". */
export function NumericField({
  value,
  onValueChange,
  min = 0,
  emptyAs = 0,
  decimals,
  fullWidth = false,
  sx,
  InputProps,
  inputProps,
  ...rest
}: Omit<ComponentProps<typeof TextField>, 'value' | 'onChange' | 'type'> & {
  value: number;
  onValueChange: (n: number) => void;
  min?: number;
  emptyAs?: number;
  decimals?: number;
}) {
  const [text, setText] = useState(() => formatNumericText(value, decimals));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(formatNumericText(value, decimals));
  }, [value, focused, decimals]);

  return (
    <TextField
      size="small"
      variant="outlined"
      fullWidth={fullWidth}
      {...rest}
      value={text}
      onFocus={(e) => {
        setFocused(true);
        rest.onFocus?.(e);
      }}
      onBlur={(e) => {
        setFocused(false);
        const parsed = parseNumericText(text, { min, emptyAs, decimals });
        setText(formatNumericText(parsed, decimals));
        onValueChange(parsed);
        rest.onBlur?.(e);
      }}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw !== '' && !/^\d*\.?\d*$/.test(raw)) return;
        setText(raw);
        if (raw === '' || raw === '.') {
          onValueChange(emptyAs);
          return;
        }
        const n = Number(raw);
        if (!Number.isFinite(n)) return;
        onValueChange(Math.max(min, n));
      }}
      inputProps={{ inputMode: 'decimal', ...inputProps }}
      InputProps={InputProps}
      sx={sx}
    />
  );
}

export function MoneyAdornment({ prefix = '₹' }: { prefix?: string }) {
  return <>{prefix}</>;
}

export { formatMoney };
