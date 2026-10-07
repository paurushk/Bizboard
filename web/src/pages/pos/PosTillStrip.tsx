import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQueryClient } from '@tanstack/react-query';
import { t } from '@/i18n';
import { getErrorMessage } from '@/api/client';
import { formatMoney } from '@/utils/money';
import {
  closeTodayShift,
  dropShiftCash,
  openTodayShift,
  printShiftSummary,
} from '@/pages/pos/posCounterApi';
import { posTerminalId, posTerminalLabel } from '@/pages/pos/posTerminal';
import { useTill } from '@/pages/pos/useTill';

const NOTES = ['500', '200', '100', '50', '20', '10', '5', '2', '1'] as const;

/** The cashier's own till for today. Cash drops reduce expected cash. */
export function PosTillStrip({ onClosed }: { onClosed: () => void }) {
  const queryClient = useQueryClient();
  const shift = useTill(posTerminalId());
  const [opening, setOpening] = useState('0');
  const [drop, setDrop] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [closedSummary, setClosedSummary] = useState<{
    expected?: string;
    counted?: string;
    variance?: string;
  } | null>(null);
  const row = shift.data?.shift;
  const open = row && row.status === 'OPEN';

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['pos-shift-today'] });
  };

  return (
    <Stack spacing={1} sx={{ mb: 1 }} data-testid="pos-till">
      {error ? <Typography color="error" variant="body2" role="alert">{error}</Typography> : null}
      {closedSummary ? (
        <Typography variant="body2">
          {t('pos.expectedCash', { amount: formatMoney(closedSummary.expected ?? 0) })}
          {' · '}
          {t('pos.countedCash', { amount: formatMoney(closedSummary.counted ?? 0) })}
          {' · '}
          {t('pos.tillVariance', { amount: formatMoney(closedSummary.variance ?? 0) })}
        </Typography>
      ) : null}
      {!open ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            label={t('pos.openingFloat')}
            value={opening}
            onChange={(e) => setOpening(e.target.value)}
            sx={{ width: 140 }}
          />
          <Button
            size="small"
            variant="outlined"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              setError(null);
              void openTodayShift(opening || '0', { id: posTerminalId(), label: posTerminalLabel() })
                .then(refresh)
                .catch((err: unknown) => setError(getErrorMessage(err)))
                .finally(() => setBusy(false));
            }}
          >
            {t('pos.openTill')}
          </Button>
        </Stack>
      ) : (
        <Stack spacing={1}>
          <Typography variant="body2">
            {t('pos.expectedCash', { amount: formatMoney(row.expectedCash ?? row.openingFloat) })}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <TextField
              size="small"
              label={t('pos.dropCash')}
              value={drop}
              onChange={(e) => setDrop(e.target.value)}
              sx={{ width: 120 }}
            />
            <Button
              size="small"
              disabled={busy || !drop}
              onClick={() => {
                setBusy(true);
                setError(null);
                void dropShiftCash(row.id, drop)
                  .then(() => {
                    setDrop('');
                    return refresh();
                  })
                  .catch((err: unknown) => setError(getErrorMessage(err)))
                  .finally(() => setBusy(false));
              }}
            >
              {t('pos.dropCash')}
            </Button>
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {NOTES.map((note) => (
              <TextField
                key={note}
                size="small"
                label={`₹${note}`}
                value={notes[note] ?? ''}
                onChange={(e) => setNotes((prev) => ({ ...prev, [note]: e.target.value }))}
                sx={{ width: 72 }}
                inputProps={{ 'aria-label': `${t('pos.countedNotes')} ${note}`, inputMode: 'numeric' }}
              />
            ))}
            <Button
              size="small"
              variant="outlined"
              disabled={busy}
              onClick={() => {
                const denominations: Record<string, number> = {};
                for (const note of NOTES) {
                  const count = Number(notes[note] || 0);
                  if (count > 0) denominations[note] = Math.trunc(count);
                }
                setBusy(true);
                setError(null);
                void closeTodayShift(row.id, denominations)
                  .then((closed) => {
                    setClosedSummary({
                      expected: closed.expectedCash,
                      counted: closed.countedCash,
                      variance: closed.variance,
                    });
                    onClosed();
                    void printShiftSummary(row.id).catch(() => undefined);
                    return refresh();
                  })
                  .catch((err: unknown) => setError(getErrorMessage(err)))
                  .finally(() => setBusy(false));
              }}
            >
              {t('pos.closeTill')}
            </Button>
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}
