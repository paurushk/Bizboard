import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

type Money = string | number;
export type CountAmount = { count: number; amount: Money };

function documentsLabel(count: number): string {
  return count === 1 ? t('money.document') : t('money.documents', { count });
}

/** A headline figure. Links to the screen that lists what it adds up. */
export function StatCard({
  label,
  value,
  to,
  badge,
  note,
  tone,
  unavailable,
}: {
  label: string;
  value: Money | null | undefined;
  to?: string;
  badge?: string;
  note?: string;
  tone?: 'success' | 'warning' | 'error';
  unavailable?: boolean;
}) {
  const missing = unavailable || value === null || value === undefined;
  const body = (
    <Paper variant="outlined" sx={{ p: 1.5, height: '100%' }}>
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        {badge ? <Chip size="small" variant="outlined" label={badge} /> : null}
      </Stack>
      <Typography variant="h5" component="p" color={missing ? 'text.secondary' : tone ? `${tone}.main` : undefined}>
        {missing ? t('money.unavailable') : formatMoney(value as Money)}
      </Typography>
      {note ? (
        <Typography variant="caption" color="text.secondary" component="p">
          {note}
        </Typography>
      ) : null}
    </Paper>
  );
  if (!to || missing) return body;
  return (
    <Box
      component={RouterLink}
      to={to}
      aria-label={`${label}: ${formatMoney(value as Money)}`}
      sx={{ textDecoration: 'none', color: 'inherit', display: 'block', height: '100%' }}
    >
      {body}
    </Box>
  );
}

/** One line in a Money In / Money Out column: label, count, amount, link to the list. */
export function TileRow({
  label,
  data,
  to,
  tone,
  hint,
  hideWhenZero,
}: {
  label: string;
  data: CountAmount | null | undefined;
  to: string;
  tone?: 'warning' | 'error' | 'info';
  hint?: string;
  hideWhenZero?: boolean;
}) {
  if (data && hideWhenZero && data.count === 0 && toNumber(data.amount) === 0) return null;
  const missing = data === null || data === undefined;
  const content = (
    <Stack
      direction="row"
      justifyContent="space-between"
      alignItems="baseline"
      spacing={1}
      sx={{ py: 1, px: 1.5 }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2">{label}</Typography>
        {hint ? (
          <Typography variant="caption" color="text.secondary" component="p">
            {hint}
          </Typography>
        ) : null}
      </Box>
      <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
        <Typography
          variant="body1"
          component="p"
          fontWeight={600}
          color={missing ? 'text.secondary' : tone && toNumber(data.amount) > 0 ? `${tone}.main` : undefined}
        >
          {missing ? t('money.unavailable') : formatMoney(data.amount)}
        </Typography>
        {!missing ? (
          <Typography variant="caption" color="text.secondary">
            {documentsLabel(data.count)}
          </Typography>
        ) : null}
      </Box>
    </Stack>
  );
  if (missing) return <Box>{content}</Box>;
  return (
    <Box
      component={RouterLink}
      to={to}
      aria-label={`${label}: ${formatMoney(data.amount)} (${documentsLabel(data.count)})`}
      sx={{
        display: 'block',
        textDecoration: 'none',
        color: 'inherit',
        borderRadius: 1,
        '&:hover, &:focus-visible': { bgcolor: 'action.hover' },
      }}
    >
      {content}
    </Box>
  );
}

/** Ageing as numbers first (a table-like list), with a proportional bar as an aid. */
export function AgeingList({
  ageing,
  notOnABill,
  to,
  side,
}: {
  ageing: Record<string, Money>;
  notOnABill: Money;
  to: string;
  /** Which column this belongs to, so the two ageing regions have different names. */
  side: string;
}) {
  const rows: Array<{ key: string; label: string; value: Money }> = [
    { key: 'current', label: t('money.ageing.current'), value: ageing.current },
    { key: 'days130', label: t('money.ageing.d1to30'), value: ageing.days130 },
    { key: 'days3160', label: t('money.ageing.d31to60'), value: ageing.days3160 },
    { key: 'days6190', label: t('money.ageing.d61to90'), value: ageing.days6190 },
    { key: 'days90Plus', label: t('money.ageing.d90plus'), value: ageing.days90Plus },
  ];
  const total = rows.reduce((sum, row) => sum + toNumber(row.value), 0);
  return (
    <Box component="section" aria-label={`${side}: ${t('money.ageing.title')}`} sx={{ px: 1.5, pt: 1 }}>
      <Typography variant="overline" color="text.secondary">
        {t('money.ageing.title')}
      </Typography>
      {total > 0 ? (
        <Box
          aria-hidden
          sx={{ display: 'flex', height: 8, borderRadius: 1, overflow: 'hidden', bgcolor: 'action.hover', my: 0.5 }}
        >
          {rows.map((row, index) =>
            toNumber(row.value) > 0 ? (
              <Box
                key={row.key}
                sx={{
                  width: `${(toNumber(row.value) / total) * 100}%`,
                  bgcolor: index === 0 ? 'success.light' : index === 1 ? 'warning.light' : 'error.light',
                  opacity: index > 2 ? 1 : 0.85,
                }}
              />
            ) : null,
          )}
        </Box>
      ) : null}
      <Box component="dl" sx={{ m: 0 }}>
        {rows.map((row) => (
          <Stack key={row.key} direction="row" justifyContent="space-between" sx={{ py: 0.25 }}>
            <Typography component="dt" variant="body2" color="text.secondary">
              {row.label}
            </Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0 }}>
              {formatMoney(row.value)}
            </Typography>
          </Stack>
        ))}
        {toNumber(notOnABill) !== 0 ? (
          <Stack direction="row" justifyContent="space-between" sx={{ py: 0.25 }}>
            <Typography component="dt" variant="body2" color="text.secondary">
              {t('money.ageing.notOnABill')}
            </Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0 }}>
              {formatMoney(notOnABill)}
            </Typography>
          </Stack>
        ) : null}
      </Box>
      <Typography
        component={RouterLink}
        to={to}
        variant="caption"
        sx={{ display: 'inline-block', mt: 0.5 }}
      >
        {t('money.ageing.openList')}
      </Typography>
    </Box>
  );
}
