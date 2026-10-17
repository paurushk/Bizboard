import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getDeliveryRoutePreflight, startDeliveryRoute, type RouteAcknowledgement } from '@/api/resources';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { AcknowledgeDialog } from './AcknowledgeDialog';
import type { PlanRisk, PlanSummary } from './planningTypes';

export type PreflightStop = {
  stop: number;
  order: number;
  number?: string | null;
  customer: string;
  status: 'ok' | 'needs_ack' | 'blocked';
  risks: PlanRisk[];
  summary: PlanSummary;
};

export type Preflight = {
  stops: PreflightStop[];
  totals: { orders: number; lines: number; quantity: string; value: string; toCollect: string; warnings: number; blocks: number };
  openProblems: number;
  canStart: boolean;
};

interface Props {
  routeId: number;
  canWrite: boolean;
  /** The route has no stops yet, or has left PLANNED. */
  hidden?: boolean;
  onStarted: () => void;
  onError: (message: string | null) => void;
}

/**
 * The check a route gets before it goes out (PL-05, PL-07, PL-08). The planning rules run again on the stops
 * as they are now: stock may have been sold, a customer blocked, credit changed since the route was planned.
 * What is blocked must be fixed or removed; what is a warning can be accepted here, with a reason that is kept.
 */
export function PreflightPanel({ routeId, canWrite, hidden, onStarted, onError }: Props) {
  const query = useQuery({
    queryKey: ['route-preflight', routeId],
    queryFn: async () => (await getDeliveryRoutePreflight(routeId)) as unknown as Preflight,
    enabled: !hidden,
  });
  const [local, setLocal] = useState<Record<number, Record<string, string>>>({});
  const [asking, setAsking] = useState<PreflightStop | null>(null);

  const start = useMutation({
    mutationFn: () => {
      const acknowledgements: RouteAcknowledgement[] = [];
      for (const [stop, codes] of Object.entries(local)) {
        for (const [code, reason] of Object.entries(codes)) acknowledgements.push({ stop: Number(stop), code, reason });
      }
      return startDeliveryRoute(routeId, acknowledgements);
    },
    onSuccess: () => {
      onError(null);
      onStarted();
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  const data = query.data;
  if (hidden || !data) return null;

  // What still stands in the way, counting what the user has accepted on this screen.
  const open = (stop: PreflightStop) =>
    stop.risks.filter((r) => r.level !== 'info' && !r.acknowledged && !local[stop.stop]?.[r.code]);
  const blocked = data.stops.filter((s) => open(s).some((r) => !r.canAccept));
  const toAccept = data.stops.filter((s) => open(s).length > 0 && open(s).every((r) => r.canAccept));
  const clear = blocked.length === 0 && toAccept.length === 0;

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="preflight-panel">
      <Stack spacing={1.25}>
        <Typography variant="subtitle1">{t('routes.plan.preflightTitle')}</Typography>
        <Typography variant="body2" data-testid="preflight-totals">
          {t('routes.plan.totals', {
            orders: data.totals.orders,
            lines: data.totals.lines,
            qty: data.totals.quantity,
            value: formatMoney(toNumber(data.totals.value)),
            collect: formatMoney(toNumber(data.totals.toCollect)),
          })}
          {data.totals.warnings > 0 ? ` · ${t('routes.plan.warningsCount', { n: data.totals.warnings })}` : ''}
        </Typography>
        {clear ? <Alert severity="success">{t('routes.plan.preflightOk')}</Alert> : null}
        {blocked.map((s) => (
          <Alert key={s.stop} severity="error">
            <b>{s.number || `#${s.order}`} · {s.customer}</b>: {t('routes.plan.blockedStop')}
            {open(s).filter((r) => !r.canAccept).map((r) => (
              <Typography key={r.code} variant="body2">{r.message}</Typography>
            ))}
          </Alert>
        ))}
        {toAccept.map((s) => (
          <Alert
            key={s.stop}
            severity="warning"
            action={canWrite ? (
              <Button size="small" sx={{ minHeight: 44 }} onClick={() => setAsking(s)}>{t('routes.plan.acceptButton')}</Button>
            ) : undefined}
          >
            <b>{s.number || `#${s.order}`} · {s.customer}</b>: {t('routes.plan.needsAccept')}
            {open(s).map((r) => (
              <Typography key={r.code} variant="body2">{r.message}</Typography>
            ))}
          </Alert>
        ))}
        {data.stops.flatMap((s) => s.risks.filter((r) => r.acknowledged && r.acknowledgedReason).map((r) => (
          <Stack key={`${s.stop}-${r.code}`} direction="row" spacing={1} alignItems="center">
            <Chip size="small" color="warning" variant="outlined" label={t(`routes.risk.${r.code}`)} />
            <Typography variant="caption">{s.number || `#${s.order}`}: {t('routes.plan.acceptedBy', { reason: r.acknowledgedReason ?? '' })}</Typography>
          </Stack>
        )))}
        {canWrite ? (
          <Button
            variant="contained"
            sx={{ minHeight: 44, alignSelf: 'flex-start' }}
            disabled={start.isPending || blocked.length > 0 || data.stops.length === 0}
            onClick={() => start.mutate()}
          >
            {t(toAccept.length === 0 && Object.keys(local).length === 0 ? 'routes.start' : 'routes.plan.acceptAndStart')}
          </Button>
        ) : null}
      </Stack>
      <AcknowledgeDialog
        open={asking !== null}
        title={asking ? asking.number || `#${asking.order}` : ''}
        risks={asking ? open(asking) : []}
        onCancel={() => setAsking(null)}
        onConfirm={(reason) => {
          if (asking) {
            setLocal((prev) => ({
              ...prev,
              [asking.stop]: { ...(prev[asking.stop] ?? {}), ...Object.fromEntries(open(asking).map((r) => [r.code, reason])) },
            }));
          }
          setAsking(null);
        }}
      />
    </Paper>
  );
}
