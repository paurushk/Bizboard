import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { verifyDeliveryRouteHandover } from '@/api/resources';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import type { RouteRow } from './routeTypes';

interface Props {
  route: RouteRow;
  /** The person counting. The server refuses the person who recorded the money (unless owner/manager). */
  canCount: boolean;
  onChanged: () => void;
}

const money = (value: number) => Math.round(value * 100) / 100;

/**
 * The cashier's count of what the driver handed over. The totals the driver reported come from the
 * stops; the cashier enters what is actually in the drawer. A difference needs a reason, kept with the
 * count. A route with collections cannot be closed until this is done.
 */
export function CashierPanel({ route, canCount, onChanged }: Props) {
  const stops = route.stops ?? [];
  const expectedCash = money(stops.reduce((sum, s) => sum + toNumber(s.collectedCash), 0));
  const expectedUpi = money(stops.reduce((sum, s) => sum + toNumber(s.collectedUpi), 0));
  const handover = route.cashHandover ?? null;
  const [cash, setCash] = useState('');
  const [upi, setUpi] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const countedCash = cash.trim() === '' ? NaN : Number(cash);
  const countedUpi = upi.trim() === '' ? NaN : Number(upi);
  const ready = Number.isFinite(countedCash) && Number.isFinite(countedUpi) && countedCash >= 0 && countedUpi >= 0;
  const variance = ready ? money(countedCash - expectedCash + (countedUpi - expectedUpi)) : 0;

  const verify = useMutation({
    mutationFn: () =>
      verifyDeliveryRouteHandover(route.id, {
        cashCounted: cash.trim(),
        upiCounted: upi.trim(),
        varianceNote: variance !== 0 ? note.trim() : undefined,
      }),
    onSuccess: () => {
      setError(null);
      setCash('');
      setUpi('');
      setNote('');
      onChanged();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (expectedCash <= 0 && expectedUpi <= 0) return null;
  const status = handover?.status ?? null;

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="cashier-panel">
      <Stack spacing={1.25}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle1">{t('routes.cashierCount')}</Typography>
          {status ? (
            <StatusChip tone={status === 'VERIFIED' ? 'success' : 'warning'} label={t(`routes.handover.${status}`)} />
          ) : (
            <StatusChip tone="warning" label={t('routes.handover.NOT_COUNTED')} />
          )}
        </Stack>
        <Typography variant="body2">
          {t('routes.driverReported')}: <b>{formatMoney(expectedCash)}</b> {t('routes.cash')} · <b>{formatMoney(expectedUpi)}</b> UPI
        </Typography>
        {handover && status ? (
          <Typography variant="body2" color={status === 'VERIFIED' ? 'success.main' : 'warning.main'}>
            {t('routes.counted')}: {formatMoney(toNumber(handover.countedCash))} {t('routes.cash')} ·{' '}
            {formatMoney(toNumber(handover.countedUpi))} UPI
            {toNumber(handover.varianceAmount) !== 0 ? ` · ${t('routes.variance')} ${formatMoney(toNumber(handover.varianceAmount))}` : ''}
            {handover.varianceNote ? ` · ${handover.varianceNote}` : ''}
          </Typography>
        ) : null}
        {error ? <Alert severity="error">{error}</Alert> : null}
        {canCount && route.status !== 'CANCELLED' ? (
          <Stack component="form" spacing={1} onSubmit={(e) => { e.preventDefault(); if (ready) verify.mutate(); }} noValidate>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField size="small" type="number" label={t('routes.cashCounted')} value={cash} onChange={(e) => setCash(e.target.value)} inputProps={{ min: 0, step: '0.01' }} fullWidth />
              <TextField size="small" type="number" label={t('routes.upiCounted')} value={upi} onChange={(e) => setUpi(e.target.value)} inputProps={{ min: 0, step: '0.01' }} fullWidth />
            </Stack>
            {ready && variance !== 0 ? (
              <>
                <Alert severity="warning">
                  {t(variance < 0 ? 'routes.countShort' : 'routes.countOver', { amount: formatMoney(Math.abs(variance)) })}
                </Alert>
                <TextField size="small" label={t('routes.varianceReason')} value={note} onChange={(e) => setNote(e.target.value)} fullWidth />
              </>
            ) : null}
            <Button type="submit" variant="contained" sx={{ minHeight: 44 }} disabled={!ready || verify.isPending}>
              {t(status ? 'routes.recount' : 'routes.recordCount')}
            </Button>
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
