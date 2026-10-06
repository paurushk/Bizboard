import Typography, { type TypographyProps } from '@mui/material/Typography';
import { usePrivacyMaskOptional } from '@/privacy/PrivacyMask';
import { formatMoney } from '@/utils/money';

/**
 * Audit-safe money display — always routes through formatMoney (en-IN INR).
 */
export function MoneyText({
  value,
  currency = 'INR',
  align = 'inherit',
  ...props
}: {
  value: string | number | null | undefined;
  currency?: string;
  align?: 'inherit' | 'left' | 'center' | 'right';
} & Omit<TypographyProps, 'children' | 'align'>) {
  const { privacyMask } = usePrivacyMaskOptional();
  return (
    <Typography
      component="span"
      align={align}
      sx={{
        fontVariantNumeric: 'tabular-nums',
        fontFeatureSettings: '"tnum"',
        ...(align === 'right' ? { display: 'inline-block', width: '100%', textAlign: 'right' } : null),
        ...((props.sx as object) ?? {}),
      }}
      {...props}
    >
      {privacyMask ? '••••' : formatMoney(value, currency)}
    </Typography>
  );
}
