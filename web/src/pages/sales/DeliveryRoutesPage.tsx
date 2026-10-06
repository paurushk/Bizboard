import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient, getErrorMessage, unwrapData } from '@/api/client';
import { capturePodPhoto } from '@/lib/native';
import { queuePodPhoto } from '@/offline/photoOutbox';
import { listRouteCombineSuggestions } from '@/api/osPlan';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import {
  completeDeliveryRoute,
  createDeliveryRoute,
  downloadDeliveryRouteManifest,
  getDeliveryRoute,
  listDeliveryRoutesPage,
  listSalesOrdersPage,
  removeDeliveryRouteStop,
  setDeliveryRouteStopStatus,
  startDeliveryRoute,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { todayIso } from '@/components/billing';
import { ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreateSales } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { triggerBlobDownload } from '@/utils/blob';

type RouteRow = {
  id: number;
  number?: string;
  routeDate?: string;
  vehicleNumber?: string;
  driverName?: string;
  status?: string;
  rollup?: { expectedProfit?: string | number; stopCount?: number };
  realizedProfit?: string | number | null;
  invoicedStopCount?: number | null;
  stopCount?: number | null;
  stops?: Array<{
    id: number;
    salesOrder: number;
    orderNumber?: string;
    customerName?: string;
    deliveryAddress?: string;
    status?: string;
    sequence?: number;
    completionSource?: string;
    receivedByName?: string;
  }>;
};

export function DeliveryRoutesPage() {
  const { id } = useParams();
  if (id) return <DeliveryRouteDetail id={Number(id)} />;
  return <DeliveryRouteList />;
}

function DeliveryRouteList() {
  const { user } = useAuth();
  useFeatureFlagEpoch();
  const routeOpt = isRuntimeFlagEnabled('ENABLE_ROUTE_OPTIMIZATION');
  const canWrite = canCreateSales(user);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ routeDate: todayIso(), vehicleNumber: '', driverName: '', notes: '' });
  const [selectedOrders, setSelectedOrders] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['delivery-routes'],
    queryFn: async () => (await listDeliveryRoutesPage({ pageSize: 100 })).results as RouteRow[],
  });
  const combine = useQuery({
    queryKey: ['route-combine'],
    queryFn: listRouteCombineSuggestions,
    enabled: routeOpt,
  });
  const orders = useQuery({
    queryKey: ['sales-orders-open'],
    queryFn: async () => {
      // A route can pick up a draft order (quote converted, not yet confirmed)
      // or one that is already confirmed. Cancelled and converted orders stay out.
      const [draft, confirmed] = await Promise.all([
        listSalesOrdersPage({ pageSize: 100, status: 'DRAFT' }),
        listSalesOrdersPage({ pageSize: 100, status: 'CONFIRMED' }),
      ]);
      return [...draft.results, ...confirmed.results];
    },
    enabled: open,
  });

  const create = useMutation({
    mutationFn: async () => createDeliveryRoute({
      ...form,
      orderIds: selectedOrders,
    }),
    onSuccess: (route) => {
      setError(null);
      setOpen(false);
      setSelectedOrders([]);
      void qc.invalidateQueries({ queryKey: ['delivery-routes'] });
      navigate(`/sales/delivery-routes/${route.id}`);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
    );
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.deliveryRoutes')}</PageTitle>
        {canWrite ? (
          <Button variant="contained" onClick={() => setOpen(true)}>
            {t('routes.create')}
          </Button>
        ) : null}
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      <Alert severity="info">{t('routes.expectedProfitHelp')}</Alert>
      {routeOpt ? <Alert severity="info">{t('routes.heuristic')}</Alert> : null}
      {routeOpt ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2">{t('osPlan.combineTitle')}</Typography>
          {combine.isLoading ? <LoadingState /> : null}
          {(combine.data ?? []).length === 0 && !combine.isLoading ? (
            <Typography variant="body2" color="text.secondary">{t('osPlan.combineEmpty')}</Typography>
          ) : null}
          {(combine.data ?? []).map((row) => (
            <Typography key={`${row.date}-${row.pincode}`} variant="body2">
              {t('osPlan.combineRow', { date: row.date, pincode: row.pincode, count: row.stopIds.length })}
            </Typography>
          ))}
        </Paper>
      ) : null}
      <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('common.number')}</TableCell>
              <TableCell>{t('common.date')}</TableCell>
              <TableCell>{t('routes.vehicle')}</TableCell>
              <TableCell>{t('routes.driver')}</TableCell>
              <TableCell>{t('common.status')}</TableCell>
              <TableCell align="right">{t('routes.expectedProfit')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(query.data ?? []).map((row) => (
              <TableRow
                key={row.id}
                hover
                sx={{ cursor: 'pointer' }}
                onClick={() => navigate(`/sales/delivery-routes/${row.id}`)}
              >
                <TableCell>{row.number ?? row.id}</TableCell>
                <TableCell>{row.routeDate}</TableCell>
                <TableCell>{row.vehicleNumber || '—'}</TableCell>
                <TableCell>{row.driverName || '—'}</TableCell>
                <TableCell>
                  <StatusChip tone={documentStatusTone(row.status ?? 'PLANNED')} labelKey={statusLabelKey(row.status ?? 'PLANNED')} />
                </TableCell>
                <TableCell align="right">{formatMoney(toNumber(row.rollup?.expectedProfit))}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('routes.create')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={form.routeDate} onChange={(e) => setForm((f) => ({ ...f, routeDate: e.target.value }))} />
            <TextField size="small" label={t('routes.vehicle')} value={form.vehicleNumber} onChange={(e) => setForm((f) => ({ ...f, vehicleNumber: e.target.value }))} />
            <TextField size="small" label={t('routes.driver')} value={form.driverName} onChange={(e) => setForm((f) => ({ ...f, driverName: e.target.value }))} />
            <Typography variant="subtitle2">{t('routes.addOrders')}</Typography>
            {(orders.data ?? []).map((o) => (
              <Stack key={o.id} direction="row" alignItems="center" spacing={1}>
                <Checkbox
                  checked={selectedOrders.includes(o.id)}
                  onChange={(e) =>
                    setSelectedOrders((prev) =>
                      e.target.checked ? [...prev, o.id] : prev.filter((id) => id !== o.id),
                    )
                  }
                />
                <Typography variant="body2">
                  {o.number ?? o.id} · {o.customerName ?? ''}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={create.isPending} onClick={() => create.mutate()}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

function DeliveryRouteDetail({ id }: { id: number }) {
  const { user } = useAuth();
  useFeatureFlagEpoch();
  const routeOpt = isRuntimeFlagEnabled('ENABLE_ROUTE_OPTIMIZATION');
  const canWrite = canCreateSales(user);
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState('');
  const [otp, setOtp] = useState('');
  const [receivedBy, setReceivedBy] = useState('');
  const [fromOffice, setFromOffice] = useState(false);
  const [stopCap, setStopCap] = useState('');
  const [suggestion, setSuggestion] = useState<{ sequenced: Array<{ stopId: number }>; unassigned: Array<{ stopId: number; reason: string }> } | null>(null);
  const suggest = useMutation({
    mutationFn: async () => {
      const body = stopCap.trim() ? { stop_cap: Number(stopCap) } : {};
      const { data } = await apiClient.post(`/sales/delivery-routes/${id}/suggest-sequence/`, body);
      return unwrapData<typeof suggestion>(data);
    },
    onSuccess: (data) => {
      setError(null);
      if (data && !Array.isArray(data) && data.unassigned) setSuggestion(data);
      else setSuggestion(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const query = useQuery({
    queryKey: ['delivery-route', id],
    queryFn: () => getDeliveryRoute(id) as Promise<RouteRow>,
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['delivery-route', id] });
  const start = useMutation({
    mutationFn: () => startDeliveryRoute(id),
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err)),
  });
  const complete = useMutation({
    mutationFn: () => completeDeliveryRoute(id, cost ? { actualLogisticsCost: cost } : undefined),
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err)),
  });
  const setStop = useMutation({
    mutationFn: async ({ stopId, status }: { stopId: number; status: string }) => {
      let podNote = '';
      if (status === 'DELIVERED' && !fromOffice) {
        const photo = await capturePodPhoto();
        if (photo) {
          await queuePodPhoto(`${id}-${stopId}`, photo, { routeId: id, stopId, receivedByName: receivedBy });
          podNote = 'photo';
        }
      }
      return setDeliveryRouteStopStatus(id, stopId, status, {
        completionSource: fromOffice ? 'OFFICE' : 'PHONE',
        otp: otp || undefined,
        podNote: podNote || undefined,
        receivedByName: status === 'DELIVERED' ? receivedBy : undefined,
      });
    },
    onSuccess: () => {
      // otp/receivedBy are shared inputs above the stop list (not per-row), so
      // they must be cleared after each use — otherwise the next stop marked
      // via the row dropdown silently reuses this stop's OTP/recipient name.
      setOtp('');
      setReceivedBy('');
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const remove = useMutation({
    mutationFn: (stopId: number) => removeDeliveryRouteStop(id, stopId),
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const route = query.data;
  if (!route) return null;
  const planned = route.status === 'PLANNED';
  const inTransit = route.status === 'IN_TRANSIT';

  return (
    <Stack spacing={2}>
      <PageTitle>{route.number ?? t('nav.deliveryRoutes')}</PageTitle>
      {error ? <HelpErrorAlert message={error} /> : null}
      <Alert severity="info">{t('routes.expectedProfitHelp')}</Alert>
      {routeOpt ? <Alert severity="info">{t('routes.heuristic')}</Alert> : null}
      {routeOpt && canWrite ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField size="small" type="number" label={t('routes.stopCap')} value={stopCap} onChange={(e) => setStopCap(e.target.value)} />
          <Button size="small" variant="outlined" disabled={suggest.isPending} onClick={() => suggest.mutate()}>{t('routes.suggestOrder')}</Button>
        </Stack>
      ) : null}
      {suggestion && suggestion.unassigned.length > 0 ? (
        <Alert severity="warning">
          {t('routes.unassignedStops')}: {suggestion.unassigned.map((stop) => stop.stopId).join(', ')} · {t('routes.overStopCap')}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <Typography>{t('common.date')}: {route.routeDate}</Typography>
          <Typography>{t('routes.vehicle')}: {route.vehicleNumber || '—'}</Typography>
          <Typography>{t('routes.driver')}: {route.driverName || '—'}</Typography>
          <StatusChip tone={documentStatusTone(route.status ?? 'PLANNED')} labelKey={statusLabelKey(route.status ?? 'PLANNED')} />
          <Typography>
            {t('routes.expectedProfit')}: {formatMoney(toNumber(route.rollup?.expectedProfit))}
          </Typography>
          {route.realizedProfit != null ? (
            <Typography>
              {t('routes.tripProfit')}: {formatMoney(toNumber(route.realizedProfit))}
              {' '}({t('routes.stopsInvoiced')}: {route.invoicedStopCount ?? 0}/{route.stopCount ?? 0})
            </Typography>
          ) : null}
          <Typography>
            {t('routes.phoneCompletions')}: {(route.stops ?? []).filter((stop) => stop.completionSource === 'PHONE').length}/{(route.stops ?? []).length}
          </Typography>
          <Button
            size="small"
            variant="outlined"
            onClick={() => {
              void downloadDeliveryRouteManifest(route.id)
                .then((blob) => triggerBlobDownload(blob, `${route.number || route.id}_manifest.pdf`))
                .catch((err) => setError(getErrorMessage(err)));
            }}
          >
            {t('routes.manifest')}
          </Button>
        </Stack>
      </Paper>
      {canWrite && planned ? (
        <Button variant="contained" onClick={() => start.mutate()} disabled={start.isPending}>
          {t('routes.start')}
        </Button>
      ) : null}
      {canWrite && inTransit ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField size="small" type="number" label={t('routes.actualCost')} value={cost} onChange={(e) => setCost(e.target.value)} />
          <TextField size="small" label={t('routes.otp')} value={otp} onChange={(e) => setOtp(e.target.value)} />
          <TextField size="small" label={t('routes.receivedBy')} value={receivedBy} onChange={(e) => setReceivedBy(e.target.value)} />
          <FormControlLabel
            control={<Checkbox checked={fromOffice} onChange={(e) => setFromOffice(e.target.checked)} />}
            label={t('routes.fromOffice')}
          />
          <Button variant="contained" onClick={() => complete.mutate()} disabled={complete.isPending}>
            {t('common.complete')}
          </Button>
        </Stack>
      ) : null}
      <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('nav.salesOrders')}</TableCell>
              <TableCell>{t('billing.customer')}</TableCell>
              <TableCell>{t('billing.deliveryAddress')}</TableCell>
              <TableCell>{t('common.status')}</TableCell>
              {canWrite ? <TableCell /> : null}
            </TableRow>
          </TableHead>
          <TableBody>
            {(route.stops ?? []).map((stop) => (
              <TableRow key={stop.id}>
                <TableCell>{stop.orderNumber ?? stop.salesOrder}</TableCell>
                <TableCell>{stop.customerName ?? '—'}</TableCell>
                <TableCell>{stop.deliveryAddress || '—'}</TableCell>
                <TableCell>
                  <StatusChip tone={documentStatusTone(stop.status ?? 'PENDING')} labelKey={statusLabelKey(stop.status ?? 'PENDING')} />
                  {stop.receivedByName ? <Typography variant="caption" display="block">{stop.receivedByName}</Typography> : null}
                  {stop.status === 'DELIVERED' ? (
                    <Button size="small" onClick={() => {
                      void apiClient.get(`/sales/delivery-routes/${id}/stops/${stop.id}/pod.pdf`, { responseType: 'blob' })
                        .then((res) => triggerBlobDownload(res.data as Blob, `pod-${stop.id}.pdf`))
                        .catch((err) => setError(getErrorMessage(err)));
                    }}>{t('routes.printSlip')}</Button>
                  ) : null}
                </TableCell>
                {canWrite ? (
                  <TableCell align="right">
                    {planned ? (
                      <Button size="small" onClick={() => remove.mutate(stop.id)}>
                        {t('common.remove')}
                      </Button>
                    ) : null}
                    {inTransit ? (
                      <TextField
                        select
                        size="small"
                        value={stop.status ?? ''}
                        onChange={(e) => setStop.mutate({ stopId: stop.id, status: e.target.value })}
                        sx={{ minWidth: 140 }}
                      >
                        <MenuItem value="PENDING">{t('status.PENDING')}</MenuItem>
                        <MenuItem value="DELIVERED" disabled={!receivedBy.trim()}>{t('status.DELIVERED')}</MenuItem>
                        <MenuItem value="FAILED">{t('status.FAILED')}</MenuItem>
                        <MenuItem value="RETURNED">{t('status.RETURNED')}</MenuItem>
                      </TextField>
                    ) : null}
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
