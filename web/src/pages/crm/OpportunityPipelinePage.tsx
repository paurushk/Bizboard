import { useState, type DragEvent, type KeyboardEvent } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { draftOpportunityInvoice } from '@/api/crm';
import {
  createOpportunityLine,
  deleteOpportunityLine,
  getForecast,
  getPipelineBoard,
  getWonVersusInvoices,
  listOpportunitiesByStage,
  listOpportunityLines,
  LOST_REASONS,
  patchOpportunity,
  reopenOpportunity,
  type OpportunityRow,
} from '@/api/growth';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { PageTitle } from '@/contextHelp';
import { formatMoney } from '@/utils/money';
import { enumLabel } from '@/utils/enumLabels';
import { t } from '@/i18n';
import { ModuleGate } from '@/pages/erp/erpShared';
import { CustomerField, ProductField } from '@/pages/growth/widgets';
import type { Customer, Product } from '@/types/domain';
import { ErrorState, LoadingState } from '@/components/PageState';

const STAGES = ['OPEN', 'QUALIFIED', 'NEGOTIATION', 'WON', 'LOST'] as const;
const OPEN_STAGES = new Set(['OPEN', 'QUALIFIED', 'NEGOTIATION']);
const NEXT: Record<string, string[]> = {
  OPEN: ['QUALIFIED', 'WON', 'LOST'],
  QUALIFIED: ['NEGOTIATION', 'WON', 'LOST'],
  NEGOTIATION: ['WON', 'LOST'],
};

export function OpportunityPipelinePage() {
  return (
    <ModuleGate module="crm" title={t('nav.pipeline')}>
      <PipelineInner />
    </ModuleGate>
  );
}

/** The month the user is in, by their own clock (toISOString would give the UTC month). */
function currentLocalMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function onActivate(handler: () => void) {
  return (event: KeyboardEvent) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handler();
    }
  };
}

function PipelineInner() {
  const qc = useQueryClient();
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const [selected, setSelected] = useState<number | null>(null);
  const [pendingStage, setPendingStage] = useState<{ id: number; stage: string; title: string } | null>(null);
  const [error, setError] = useState('');
  const [lostReason, setLostReason] = useState('');
  const [lostNote, setLostNote] = useState('');
  const { writesBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  const canReopen = user?.role === 'OWNER' || user?.role === 'MANAGER';
  // Won/Lost show the last 90 days; "Show older" widens the window. Open deals are never windowed.
  const [closedDays, setClosedDays] = useState(90);
  // "Load more" rows belong to the board fetch they were loaded against; a fresh fetch drops them.
  const [more, setMore] = useState<{ at: number; rows: Record<string, OpportunityRow[]>; pages: Record<string, number> }>(
    { at: 0, rows: {}, pages: {} },
  );
  const list = useQuery({
    queryKey: ['opportunities-board', closedDays],
    queryFn: () => getPipelineBoard(closedDays),
  });
  const live = more.at === list.dataUpdatedAt ? more : { at: list.dataUpdatedAt, rows: {}, pages: {} };
  const [month, setMonth] = useState(currentLocalMonth);
  const forecast = useQuery({ queryKey: ['forecast'], queryFn: getForecast });
  const wonVersus = useQuery({
    queryKey: ['won-versus-invoices', month],
    queryFn: () => getWonVersusInvoices(month),
  });
  const move = useMutation({
    mutationFn: ({ id, stage, reason, note }: { id: number; stage: string; reason?: string; note?: string }) =>
      patchOpportunity(id, reason ? { stage, lost_reason: reason, lost_reason_note: note ?? '' } : { stage }),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
      void qc.invalidateQueries({ queryKey: ['forecast'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const loadMore = useMutation({
    mutationFn: async (stage: string) => {
      const page = (live.pages[stage] ?? 1) + 1;
      const result = await listOpportunitiesByStage({ stage, page, closedDays });
      return { stage, page, rows: result.results };
    },
    onSuccess: ({ stage, page, rows: added }) => {
      setMore({
        at: live.at,
        pages: { ...live.pages, [stage]: page },
        rows: { ...live.rows, [stage]: [...(live.rows[stage] ?? []), ...added] },
      });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const stageRows: Record<string, OpportunityRow[]> = {};
  for (const stage of STAGES) {
    const seen = new Set<number>();
    stageRows[stage] = [...(list.data?.stages?.[stage]?.results ?? []), ...(live.rows[stage] ?? [])].filter((row) => {
      if (seen.has(row.id)) return false;
      seen.add(row.id);
      return true;
    });
  }
  const rows = STAGES.flatMap((stage) => stageRows[stage]);
  const selectedRow = rows.find((row) => row.id === selected) ?? null;
  const months = forecast.data?.months ?? [];
  const max = Math.max(1, ...months.map((row) => Number(row.amount) || 0), Number(forecast.data?.unscheduled) || 0);

  const dropOn = (stage: string, event: DragEvent) => {
    event.preventDefault();
    const id = Number(event.dataTransfer.getData('text/plain'));
    const row = rows.find((item) => item.id === id);
    if (!row || !OPEN_STAGES.has(row.stage) || stage === row.stage) return;
    if (stage === 'WON' || stage === 'LOST') {
      // Same confirmation (and the "won needs a customer" check) as the buttons.
      setPendingStage({ id, stage, title: row.title });
      return;
    }
    move.mutate({ id, stage });
  };

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.pipeline')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.pipelineHonesty')}</Typography>
      <Typography variant="body2" color="text.secondary">{t('growth.stageDefaults')}</Typography>
      <Typography variant="caption" color="text.secondary">{t('growth.dragHint')}</Typography>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2">{t('growth.forecast')}</Typography>
        {forecast.isError ? (
          <ErrorState message={getErrorMessage(forecast.error)} error={forecast.error} onRetry={() => void forecast.refetch()} />
        ) : null}
        {months.map((row) => (
          <ForecastBar key={row.month} label={row.month} amount={row.amount} max={max} />
        ))}
        <ForecastBar label={t('growth.unscheduled')} amount={forecast.data?.unscheduled ?? '0'} max={max} />
        <TextField
          size="small"
          type="month"
          label={t('common.date')}
          value={month}
          onChange={(event) => setMonth(event.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ mt: 1 }}
        />
        {wonVersus.isError ? (
          <ErrorState message={getErrorMessage(wonVersus.error)} error={wonVersus.error} onRetry={() => void wonVersus.refetch()} />
        ) : null}
        {wonVersus.data ? (
          <Stack spacing={0.5} sx={{ mt: 1 }}>
            <Typography>{t('growth.wonAmount')}: {formatMoney(wonVersus.data.wonAmount)}</Typography>
            <Typography>{t('growth.invoicedAmount')}: {formatMoney(wonVersus.data.invoicedAmount)}</Typography>
          </Stack>
        ) : null}
      </Paper>
      {error ? <Typography color="error">{error}</Typography> : null}
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? (
        <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} />
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        {STAGES.map((stage) => (
          <Paper
            key={stage}
            variant="outlined"
            sx={{ p: 1.5, flex: 1, minHeight: 180 }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => dropOn(stage, event)}
          >
            <Typography variant="subtitle2">
              {enumLabel('opportunityStage', stage)} · {list.data?.stages?.[stage]?.count ?? 0}
              {Number(list.data?.stages?.[stage]?.totalAmount) > 0
                ? ` · ${formatMoney(list.data?.stages?.[stage]?.totalAmount)}`
                : ''}
            </Typography>
            {stageRows[stage].length === 0 ? (
              <Typography variant="caption" color="text.secondary">{t('cog.emptyPipeline')}</Typography>
            ) : null}
            {stageRows[stage].map((row) => (
              <Paper
                key={row.id}
                variant="outlined"
                role="button"
                tabIndex={0}
                aria-label={row.title}
                onKeyDown={onActivate(() => setSelected(row.id))}
                draggable={!narrow && !writesBlocked && OPEN_STAGES.has(row.stage)}
                onDragStart={(event) => event.dataTransfer.setData('text/plain', String(row.id))}
                onClick={() => setSelected(row.id)}
                sx={{ p: 1, mt: 1, cursor: OPEN_STAGES.has(row.stage) ? 'grab' : 'pointer' }}
              >
                <Typography variant="body2">{row.title}</Typography>
                <Typography variant="caption" display="block">
                  {formatMoney(row.amount)} · {row.probability}%{row.expectedCloseDate ? ` · ${new Date(row.expectedCloseDate).toLocaleDateString('en-IN')}` : ''}
                </Typography>
                {row.competitor ? (
                  <Typography variant="caption" display="block">{t('growth.competitor')}: {row.competitor}</Typography>
                ) : null}
                {OPEN_STAGES.has(row.stage) && !writesBlocked ? (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {(NEXT[row.stage] ?? []).map((next) => (
                      <Button key={next} size="small" onClick={(event) => {
                        event.stopPropagation();
                        if (next === 'WON' || next === 'LOST') {
                          setPendingStage({ id: row.id, stage: next, title: row.title });
                          return;
                        }
                        move.mutate({ id: row.id, stage: next });
                      }}>
                        {t('growth.moveTo')} {enumLabel('opportunityStage', next)}
                      </Button>
                    ))}
                  </Stack>
                ) : null}
              </Paper>
            ))}
            {stageRows[stage].length < (list.data?.stages?.[stage]?.count ?? 0) ? (
              <Button size="small" sx={{ mt: 1 }} disabled={loadMore.isPending} onClick={() => loadMore.mutate(stage)}>
                {t('growth.loadMore')}
              </Button>
            ) : null}
            {(list.data?.stages?.[stage]?.older ?? 0) > 0 && closedDays > 0 ? (
              <Button size="small" sx={{ mt: 1 }} onClick={() => setClosedDays(0)}>
                {t('growth.showOlder', { count: String(list.data?.stages?.[stage]?.older ?? 0) })}
              </Button>
            ) : null}
          </Paper>
        ))}
      </Stack>
      {selectedRow ? (
        <OpportunityDetail
          key={selectedRow.id}
          row={selectedRow}
          onError={setError}
          readOnly={writesBlocked}
          canReopen={canReopen}
        />
      ) : null}
      <Dialog
        open={pendingStage?.stage === 'LOST'}
        onClose={() => { setPendingStage(null); setLostReason(''); setLostNote(''); }}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>{t('cog.confirmLost', { name: pendingStage?.title ?? '' })}</DialogTitle>
        <DialogContent>
          <TextField
            select
            required
            fullWidth
            margin="dense"
            label={t('growth.lostReason')}
            value={lostReason}
            onChange={(e) => setLostReason(e.target.value)}
          >
            {LOST_REASONS.map((reason) => (
              <MenuItem key={reason} value={reason}>{t(`growth.lostReason${reason}`)}</MenuItem>
            ))}
          </TextField>
          {lostReason === 'OTHER' ? (
            <TextField
              fullWidth
              margin="dense"
              label={t('growth.lostReasonNote')}
              value={lostNote}
              onChange={(e) => setLostNote(e.target.value)}
              inputProps={{ maxLength: 200 }}
            />
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setPendingStage(null); setLostReason(''); setLostNote(''); }}>{t('common.cancel')}</Button>
          <Button
            color="warning"
            variant="contained"
            disabled={!lostReason || (lostReason === 'OTHER' && !lostNote.trim()) || move.isPending}
            onClick={() => {
              if (pendingStage) {
                move.mutate({ id: pendingStage.id, stage: 'LOST', reason: lostReason, note: lostNote.trim() });
              }
              setPendingStage(null);
              setLostReason('');
              setLostNote('');
            }}
          >
            {t('growth.confirmLostAction')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={Boolean(pendingStage) && pendingStage?.stage !== 'LOST'}
        title={pendingStage?.stage === 'LOST' ? t('cog.confirmLost', { name: pendingStage?.title ?? '' }) : t('cog.confirmWon', { name: pendingStage?.title ?? '' })}
        body={pendingStage?.title ?? ''}
        onClose={() => setPendingStage(null)}
        onConfirm={() => {
          if (pendingStage) {
            if (pendingStage.stage === 'WON') {
              const deal = rows.find((row) => row.id === pendingStage.id);
              if (!deal?.customer) {
                setError(t('growth.wonNeedsCustomer'));
                setPendingStage(null);
                return;
              }
            }
            move.mutate({ id: pendingStage.id, stage: pendingStage.stage });
          }
          setPendingStage(null);
        }}
      />
    </Stack>
  );
}

function ForecastBar({ label, amount, max }: { label: string; amount: string; max: number }) {
  const width = `${Math.max(4, (Number(amount) / max) * 100)}%`;
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
      <Typography variant="caption" sx={{ width: 110 }}>{label}</Typography>
      <Box sx={{ flex: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
        <Box sx={{ width, bgcolor: 'primary.main', height: 10, borderRadius: 1 }} />
      </Box>
      <Typography variant="caption" sx={{ width: 90 }}>{formatMoney(amount)}</Typography>
    </Stack>
  );
}

function OpportunityDetail({
  row,
  onError,
  readOnly,
  canReopen,
}: {
  row: OpportunityRow;
  onError: (message: string) => void;
  readOnly: boolean;
  canReopen: boolean;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const closed = row.stage === 'WON' || row.stage === 'LOST';
  const [saved, setSaved] = useState(false);
  const [confirmReopen, setConfirmReopen] = useState(false);
  const [pendingLine, setPendingLine] = useState<number | null>(null);
  const [customerPick, setCustomerPick] = useState<Customer | null>(null);
  const setCustomer = useMutation({
    mutationFn: (customer: Customer) => patchOpportunity(row.id, { customer: customer.id }),
    onSuccess: () => {
      onError('');
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
    },
    onError: (err) => {
      setCustomerPick(null);
      onError(getErrorMessage(err));
    },
  });
  const reopen = useMutation({
    mutationFn: () => reopenOpportunity(row.id),
    onSuccess: () => {
      setConfirmReopen(false);
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
      void qc.invalidateQueries({ queryKey: ['forecast'] });
    },
    onError: (err) => {
      setConfirmReopen(false);
      onError(getErrorMessage(err));
    },
  });
  const [probability, setProbability] = useState(String(row.probability ?? 0));
  const [closeDate, setCloseDate] = useState(row.expectedCloseDate ?? '');
  const [competitor, setCompetitor] = useState(row.competitor ?? '');
  const [product, setProduct] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('0');
  const lines = useQuery({
    queryKey: ['opportunity-lines', row.id],
    queryFn: () => listOpportunityLines(row.id),
  });
  const save = useMutation({
    mutationFn: () => {
      const next = Number(probability);
      if (!Number.isInteger(next) || next < 0 || next > 100) {
        return Promise.reject(new Error(t('growth.probabilityRange')));
      }
      return patchOpportunity(row.id, {
        probability: next,
        expected_close_date: closeDate || null,
        competitor: competitor.trim(),
      });
    },
    onSuccess: () => {
      onError('');
      setSaved(true);
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
      void qc.invalidateQueries({ queryKey: ['forecast'] });
    },
    onError: (err) => {
      setSaved(false);
      onError(getErrorMessage(err));
    },
  });
  const addLine = useMutation({
    mutationFn: () => createOpportunityLine(row.id, {
      product: product?.id,
      quantity,
      unit_price: price,
    }),
    onSuccess: () => {
      setProduct(null);
      void qc.invalidateQueries({ queryKey: ['opportunity-lines', row.id] });
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
      void qc.invalidateQueries({ queryKey: ['forecast'] });
    },
    onError: (err) => onError(getErrorMessage(err)),
  });
  const removeLine = useMutation({
    mutationFn: (lineId: number) => deleteOpportunityLine(row.id, lineId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['opportunity-lines', row.id] });
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2">{row.title}</Typography>
      {closed ? <Typography variant="body2" color="text.secondary">{t('growth.closedDealNote')}</Typography> : null}
      {closed && canReopen && !readOnly ? (
        <Button size="small" color="warning" sx={{ mt: 1 }} disabled={reopen.isPending} onClick={() => setConfirmReopen(true)}>
          {t('growth.reopenDeal')}
        </Button>
      ) : null}
      <ConfirmDialog
        open={pendingLine !== null}
        title={t('growth.removeLineConfirmTitle')}
        body={t('growth.removeLineConfirmBody')}
        confirmColor="warning"
        onClose={() => setPendingLine(null)}
        onConfirm={() => {
          if (pendingLine !== null) removeLine.mutate(pendingLine);
          setPendingLine(null);
        }}
      />
      <ConfirmDialog
        open={confirmReopen}
        title={t('growth.reopenConfirmTitle', { name: row.title })}
        body={t('growth.reopenConfirmBody')}
        confirming={reopen.isPending}
        onClose={() => setConfirmReopen(false)}
        onConfirm={() => reopen.mutate()}
      />
      {!closed && !readOnly ? (
        <Stack sx={{ mt: 1, maxWidth: 360 }}>
          <CustomerField
            value={customerPick}
            onChange={(customer) => {
              setCustomerPick(customer);
              if (customer) setCustomer.mutate(customer);
            }}
          />
          <Typography variant="caption" color="text.secondary">
            {row.customer ? t('growth.customerLinked') : t('growth.customerNeededToWin')}
          </Typography>
        </Stack>
      ) : null}
      {row.stage === 'WON' ? (
        <Button size="small" sx={{ mt: 1 }} onClick={() => {
          void draftOpportunityInvoice(row.id)
            .then((invoice) => navigate(`/sales/history/${invoice.id}`))
            .catch((err) => onError(getErrorMessage(err)));
        }}>{t('growth.createDraftInvoice')}</Button>
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ md: 'center' }}>
        <TextField size="small" type="number" label={t('growth.probability')} value={probability} onChange={(e) => { setSaved(false); setProbability(e.target.value); }} inputProps={{ min: 0, max: 100 }} disabled={closed || readOnly} />
        <TextField size="small" type="date" label={t('growth.closeDate')} value={closeDate} onChange={(e) => { setSaved(false); setCloseDate(e.target.value); }} InputLabelProps={{ shrink: true }} disabled={closed || readOnly} />
        <TextField size="small" label={t('growth.competitor')} value={competitor} onChange={(e) => { setSaved(false); setCompetitor(e.target.value); }} inputProps={{ maxLength: 120 }} disabled={readOnly} />
        <Button variant="contained" disabled={readOnly || save.isPending} onClick={() => save.mutate()}>{t('growth.save')}</Button>
        {saved ? <Typography variant="caption" role="status">{t('growth.dealSaved')}</Typography> : null}
      </Stack>
      <Typography variant="subtitle2" sx={{ mt: 2 }}>{t('growth.lines')}</Typography>
      {(lines.data?.results ?? []).map((line) => (
        <Stack key={line.id} direction="row" spacing={1} alignItems="center">
          <Typography variant="body2">{line.productName || `#${line.product}`} · {line.quantity} × {line.unitPrice}</Typography>
          <Button size="small" disabled={closed || readOnly} onClick={() => setPendingLine(line.id)}>{t('growth.remove')}</Button>
        </Stack>
      ))}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ md: 'center' }}>
        <ProductField value={product} onChange={setProduct} />
        <TextField size="small" label={t('growth.quantity')} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <TextField size="small" label={t('growth.unitPrice')} value={price} onChange={(e) => setPrice(e.target.value)} />
        <Button disabled={!product || closed || readOnly || addLine.isPending} onClick={() => addLine.mutate()}>{t('growth.addLine')}</Button>
      </Stack>
    </Paper>
  );
}
