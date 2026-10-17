import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
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
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiClient, getErrorMessage, unwrapData } from '@/api/client';
import { listRouteCombineSuggestions } from '@/api/osPlan';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import {
  addOrdersToDeliveryRoute,
  cancelDeliveryRoute,
  completeDeliveryRoute,
  createDeliveryRoute,
  downloadDeliveryRouteManifest,
  getDeliveryRoute,
  listDeliveryRoutesPage,
  removeDeliveryRouteStop,
  searchSalespeople,
  updateDeliveryRoute,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { todayIso } from '@/components/billing';
import { ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { triggerBlobDownload } from '@/utils/blob';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreateSales } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { CashierPanel } from './routes/CashierPanel';
import { LinkReceiptDialog } from './routes/LinkReceiptDialog';
import { PlanningTable, type PlanningSelection } from './routes/PlanningTable';
import { PreflightPanel } from './routes/PreflightPanel';
import { StopCard } from './routes/StopCard';
import { ATTENTION_LABEL_KEYS, sortRoutes, type RouteRow, type RouteStop } from './routes/routeTypes';

const TOUCH = { minHeight: 44 } as const;

export function DeliveryRoutesPage() {
  const { id } = useParams();
  if (id) return <DeliveryRouteDetail id={Number(id)} />;
  return <DeliveryRouteList />;
}

/** The people a route can be given to: the same employee list the order screens use for a salesperson. */
function useDriverOptions() {
  return useQuery({ queryKey: ['salespeople', ''], queryFn: () => searchSalespeople() });
}

function AttentionChips({ row }: { row: RouteRow }) {
  const items = (row.progress?.needsAttention ?? []).filter((a) => ATTENTION_LABEL_KEYS[a]);
  if (items.length === 0) return null;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
      {items.map((a) => (
        <Chip key={a} size="small" color={a === 'ready_to_close' ? 'info' : 'warning'} label={t(ATTENTION_LABEL_KEYS[a])} />
      ))}
    </Stack>
  );
}

function DeliveryRouteList() {
  const { user } = useAuth();
  useFeatureFlagEpoch();
  const routeOpt = isRuntimeFlagEnabled('ENABLE_ROUTE_OPTIMIZATION');
  const canWrite = canCreateSales(user);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const drivers = useDriverOptions();
  const location = useLocation();
  // Orders picked on the sales order list arrive here: open the planner with just those.
  const pickedOnList = ((location.state as { orderIds?: number[] } | null)?.orderIds ?? []).filter(Number.isFinite);
  const [open, setOpen] = useState(pickedOnList.length > 0);
  const [form, setForm] = useState({ routeDate: todayIso(), vehicleNumber: '', driverName: '', driver: null as number | null, notes: '' });
  const [plan, setPlan] = useState<PlanningSelection>({ orderIds: [], acknowledgements: [] });
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const debouncedSearch = useDebouncedValue(search, 300);
  const query = useQuery({
    queryKey: ['delivery-routes', debouncedSearch, statusFilter],
    queryFn: async () =>
      (await listDeliveryRoutesPage({ pageSize: 100, q: debouncedSearch.trim() || undefined, status: statusFilter || undefined }))
        .results as RouteRow[],
    // Typing in the search box must not blank the page while the new list loads.
    placeholderData: keepPreviousData,
  });
  const combine = useQuery({
    queryKey: ['route-combine'],
    queryFn: listRouteCombineSuggestions,
    enabled: routeOpt,
  });

  const create = useMutation({
    mutationFn: async () =>
      createDeliveryRoute({ ...form, driver: form.driver, orderIds: plan.orderIds, acknowledgements: plan.acknowledgements }),
    onSuccess: (route) => {
      setError(null);
      setOpen(false);
      setPlan({ orderIds: [], acknowledgements: [] });
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
  const rows = sortRoutes(query.data ?? []);
  // Expected profit is cost-based: only people who may see it get a column and the note about it.
  const showProfit = rows.some((r) => r.rollup != null);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap spacing={1}>
        <PageTitle>{t('nav.deliveryRoutes')}</PageTitle>
        {canWrite ? (
          <Button variant="contained" sx={TOUCH} onClick={() => setOpen(true)}>
            {t('routes.create')}
          </Button>
        ) : null}
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {showProfit ? <Alert severity="info">{t('routes.expectedProfitHelp')}</Alert> : null}
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
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField size="small" label={t('common.search')} value={search} onChange={(e) => setSearch(e.target.value)} fullWidth />
        <TextField select size="small" label={t('common.status')} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {['PLANNED', 'IN_TRANSIT', 'COMPLETED', 'CANCELLED'].map((s) => (
            <MenuItem key={s} value={s}>{t(`status.${s}`)}</MenuItem>
          ))}
        </TextField>
      </Stack>
      <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('common.number')}</TableCell>
              <TableCell>{t('common.date')}</TableCell>
              <TableCell>{t('routes.vehicle')}</TableCell>
              <TableCell>{t('routes.driver')}</TableCell>
              <TableCell>{t('common.status')}</TableCell>
              <TableCell>{t('routes.progress')}</TableCell>
              <TableCell align="right">{t('routes.collected')}</TableCell>
              <TableCell>{t('routes.needsAttention')}</TableCell>
              {showProfit ? <TableCell align="right">{t('routes.expectedProfit')}</TableCell> : null}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
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
                <TableCell>
                  {row.progress
                    ? t('routes.progressText', { done: row.progress.delivered, total: row.progress.stopsTotal })
                    : '—'}
                  {row.progress && row.progress.failed > 0 ? ` · ${t('routes.failedCount', { n: row.progress.failed })}` : ''}
                </TableCell>
                <TableCell align="right">{formatMoney(toNumber(row.progress?.collected))}</TableCell>
                <TableCell><AttentionChips row={row} /></TableCell>
                {showProfit ? <TableCell align="right">{formatMoney(toNumber(row.rollup?.expectedProfit))}</TableCell> : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="lg">
        <DialogTitle>{t('routes.create')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={form.routeDate} onChange={(e) => setForm((f) => ({ ...f, routeDate: e.target.value }))} />
            <TextField size="small" label={t('routes.vehicle')} value={form.vehicleNumber} onChange={(e) => setForm((f) => ({ ...f, vehicleNumber: e.target.value }))} />
            <DriverField
              options={drivers.data ?? []}
              name={form.driverName}
              driverId={form.driver}
              onChange={(driverName, driver) => setForm((f) => ({ ...f, driverName, driver }))}
            />
            <Typography variant="subtitle2">{t('routes.addOrders')}</Typography>
            {open ? <PlanningTable open={open} onlyIds={pickedOnList} onChange={setPlan} /> : null}
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

/** A driver picked from the staff list, or typed when they are not on it. */
function DriverField({
  options,
  name,
  driverId,
  onChange,
}: {
  options: Array<{ id: number; name: string; code?: string }>;
  name: string;
  driverId: number | null;
  onChange: (name: string, driver: number | null) => void;
}) {
  const selected = options.find((o) => o.id === driverId) ?? null;
  return (
    <Autocomplete
      freeSolo
      size="small"
      options={options}
      getOptionLabel={(o) => (typeof o === 'string' ? o : o.name)}
      value={selected ?? (name || null)}
      inputValue={name}
      onInputChange={(_, text, reason) => {
        if (reason === 'input' || reason === 'clear') onChange(text, null);
      }}
      onChange={(_, value) => {
        if (value && typeof value !== 'string') onChange(value.name, value.id);
      }}
      renderInput={(params) => <TextField {...params} label={t('routes.driver')} />}
    />
  );
}

function DeliveryRouteDetail({ id }: { id: number }) {
  const { user } = useAuth();
  useFeatureFlagEpoch();
  const routeOpt = isRuntimeFlagEnabled('ENABLE_ROUTE_OPTIMIZATION');
  const canWrite = canCreateSales(user);
  const qc = useQueryClient();
  const drivers = useDriverOptions();
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState('');
  const [stopCap, setStopCap] = useState('');
  const [suggestion, setSuggestion] = useState<{ sequenced: Array<{ stopId: number }>; unassigned: Array<{ stopId: number; reason: string }> } | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addPlan, setAddPlan] = useState<PlanningSelection>({ orderIds: [], acknowledgements: [] });
  const [editOpen, setEditOpen] = useState(false);
  const [edit, setEdit] = useState({ routeDate: '', vehicleNumber: '', driverName: '', driver: null as number | null, notes: '' });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [linkStop, setLinkStop] = useState<RouteStop | null>(null);

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

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['delivery-route', id] });
    void qc.invalidateQueries({ queryKey: ['delivery-routes'] });
    void qc.invalidateQueries({ queryKey: ['route-preflight', id] });
    void qc.invalidateQueries({ queryKey: ['route-candidates'] });
  };
  const fail = (err: unknown) => setError(getErrorMessage(err));
  const complete = useMutation({
    mutationFn: () => completeDeliveryRoute(id, cost ? { actualLogisticsCost: cost } : undefined),
    onSuccess: () => { setError(null); invalidate(); },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (stopId: number) => removeDeliveryRouteStop(id, stopId),
    onSuccess: invalidate,
    onError: fail,
  });
  const addOrders = useMutation({
    mutationFn: () => addOrdersToDeliveryRoute(id, addPlan.orderIds, addPlan.acknowledgements),
    onSuccess: () => { setAddOpen(false); setAddPlan({ orderIds: [], acknowledgements: [] }); setError(null); invalidate(); },
    onError: fail,
  });
  const save = useMutation({
    mutationFn: () => updateDeliveryRoute(id, edit),
    onSuccess: () => { setEditOpen(false); setError(null); invalidate(); },
    onError: fail,
  });
  const cancel = useMutation({
    mutationFn: () => cancelDeliveryRoute(id, cancelReason.trim() || undefined),
    onSuccess: () => { setCancelOpen(false); setCancelReason(''); setError(null); invalidate(); },
    onError: (err) => { setCancelOpen(false); fail(err); },
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const route = query.data;
  if (!route) return null;
  const planned = route.status === 'PLANNED';
  const inTransit = route.status === 'IN_TRANSIT';
  const live = planned || inTransit;
  const stops = route.stops ?? [];
  const pendingStops = stops.filter((s) => (s.status ?? 'PENDING') === 'PENDING');
  const collected = toNumber(route.progress?.collected);
  const closeBlockedByStops = inTransit && pendingStops.length > 0;
  const showProfit = route.rollup != null;

  return (
    <Stack spacing={2}>
      <PageTitle>{route.number ?? t('nav.deliveryRoutes')}</PageTitle>
      {error ? <HelpErrorAlert message={error} /> : null}
      {showProfit ? <Alert severity="info">{t('routes.expectedProfitHelp')}</Alert> : null}
      {routeOpt ? <Alert severity="info">{t('routes.heuristic')}</Alert> : null}
      {(route.warnings ?? []).map((w) => (
        <Alert key={`${w.code}-${w.route}`} severity="warning">{w.message}</Alert>
      ))}
      {routeOpt && canWrite && planned ? (
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

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <StatusChip tone={documentStatusTone(route.status ?? 'PLANNED')} labelKey={statusLabelKey(route.status ?? 'PLANNED')} />
            <AttentionChips row={route} />
          </Stack>
          <Typography>{t('common.date')}: {route.routeDate}</Typography>
          <Typography>{t('routes.vehicle')}: {route.vehicleNumber || '—'}</Typography>
          <Typography>{t('routes.driver')}: {route.driverName || '—'}</Typography>
          {route.progress ? (
            <Typography>
              {t('routes.progress')}: {t('routes.progressText', { done: route.progress.delivered, total: route.progress.stopsTotal })}
              {route.progress.failed ? ` · ${t('routes.failedCount', { n: route.progress.failed })}` : ''}
              {route.progress.pending ? ` · ${t('routes.pendingCount', { n: route.progress.pending })}` : ''}
              {collected > 0 ? ` · ${t('routes.collected')}: ${formatMoney(collected)}` : ''}
            </Typography>
          ) : null}
          {showProfit ? (
            <Typography>{t('routes.expectedProfit')}: {formatMoney(toNumber(route.rollup?.expectedProfit))}</Typography>
          ) : null}
          {route.realizedProfit != null ? (
            <Typography>
              {t('routes.tripProfit')}: {formatMoney(toNumber(route.realizedProfit))}
              {' '}({t('routes.stopsInvoiced')}: {route.invoicedStopCount ?? 0}/{route.stopCount ?? 0})
            </Typography>
          ) : null}
          {route.notes ? <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>{route.notes}</Typography> : null}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              size="small"
              variant="outlined"
              sx={TOUCH}
              onClick={() => {
                void downloadDeliveryRouteManifest(route.id)
                  .then((blob) => triggerBlobDownload(blob, `${route.number || route.id}_manifest.pdf`))
                  .catch((err) => setError(getErrorMessage(err)));
              }}
            >
              {t('routes.manifest')}
            </Button>
            {canWrite && planned ? (
              <>
                <Button size="small" sx={TOUCH} onClick={() => { setEdit({ routeDate: route.routeDate ?? '', vehicleNumber: route.vehicleNumber ?? '', driverName: route.driverName ?? '', driver: route.driver ?? null, notes: route.notes ?? '' }); setEditOpen(true); }}>
                  {t('common.edit')}
                </Button>
                <Button size="small" sx={TOUCH} onClick={() => setAddOpen(true)}>{t('routes.addOrdersAction')}</Button>
              </>
            ) : null}
            {canWrite && live ? (
              <Button size="small" color="warning" sx={TOUCH} onClick={() => setCancelOpen(true)}>{t('routes.cancelRoute')}</Button>
            ) : null}
          </Stack>
        </Stack>
      </Paper>

      {planned && stops.length > 0 ? (
        <PreflightPanel routeId={route.id} canWrite={canWrite} onStarted={invalidate} onError={setError} />
      ) : null}

      {closeBlockedByStops ? (
        <Alert severity="warning">
          {t('routes.pendingBlock', { n: pendingStops.length, orders: pendingStops.map((s) => s.orderNumber ?? s.salesOrder).join(', ') })}
        </Alert>
      ) : null}
      {canWrite && inTransit ? (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <TextField size="small" type="number" label={t('routes.actualCost')} value={cost} onChange={(e) => setCost(e.target.value)} />
          <Button variant="contained" sx={TOUCH} onClick={() => complete.mutate()} disabled={complete.isPending || closeBlockedByStops}>
            {t('routes.closeRoute')}
          </Button>
        </Stack>
      ) : null}

      {stops.length === 0 ? <Alert severity="info">{t('routes.noStops')}</Alert> : null}
      <Stack spacing={1.5}>
        {stops.map((stop) => (
          <Stack key={stop.id} spacing={0.5}>
            <StopCard
              routeId={route.id}
              routeStatus={route.status ?? 'PLANNED'}
              stop={stop}
              canWrite={canWrite}
              canLinkReceipt={canWrite && (inTransit || route.status === 'COMPLETED')}
              onChanged={invalidate}
              onError={setError}
              onLinkReceipt={setLinkStop}
              triggerBlobDownload={triggerBlobDownload}
            />
            {canWrite && planned ? (
              <Button size="small" color="warning" sx={{ ...TOUCH, alignSelf: 'flex-start' }} onClick={() => remove.mutate(stop.id)}>
                {t('common.remove')}
              </Button>
            ) : null}
          </Stack>
        ))}
      </Stack>

      <CashierPanel route={route} canCount={canWrite && (inTransit || route.status === 'COMPLETED')} onChanged={invalidate} />
      <LinkReceiptDialog routeId={route.id} stop={linkStop} onClose={() => setLinkStop(null)} onLinked={() => { setLinkStop(null); invalidate(); }} />

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} fullWidth maxWidth="lg">
        <DialogTitle>{t('routes.addOrdersAction')}</DialogTitle>
        <DialogContent>
          {addOpen ? <PlanningTable open={addOpen} excludeIds={stops.map((s) => s.salesOrder)} onChange={setAddPlan} /> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={addOrders.isPending || addPlan.orderIds.length === 0} onClick={() => addOrders.mutate()}>
            {t('common.add')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editOpen} onClose={() => setEditOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('routes.editRoute')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={edit.routeDate} onChange={(e) => setEdit((f) => ({ ...f, routeDate: e.target.value }))} />
            <TextField size="small" label={t('routes.vehicle')} value={edit.vehicleNumber} onChange={(e) => setEdit((f) => ({ ...f, vehicleNumber: e.target.value }))} />
            <DriverField
              options={drivers.data ?? []}
              name={edit.driverName}
              driverId={edit.driver}
              onChange={(driverName, driver) => setEdit((f) => ({ ...f, driverName, driver }))}
            />
            <TextField size="small" multiline minRows={2} label={t('billing.addNotes')} value={edit.notes} onChange={(e) => setEdit((f) => ({ ...f, notes: e.target.value }))} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>{t('common.save')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={cancelOpen} onClose={() => setCancelOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('routes.cancelRoute')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <Typography variant="body2">{t(inTransit ? 'routes.cancelHelpStarted' : 'routes.cancelHelpPlanned')}</Typography>
            <TextField
              size="small"
              required={inTransit}
              label={t('routes.cancelReason')}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelOpen(false)}>{t('common.cancel')}</Button>
          <Button
            color="warning"
            variant="contained"
            disabled={cancel.isPending || (inTransit && cancelReason.trim().length < 3)}
            onClick={() => cancel.mutate()}
          >
            {t('routes.cancelRoute')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
