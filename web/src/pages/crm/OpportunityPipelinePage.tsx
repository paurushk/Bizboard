import { useState, type DragEvent } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { createInvoiceFromOpportunity } from '@/api/crm';
import {
  createOpportunityLine,
  deleteOpportunityLine,
  getForecast,
  getWonVersusInvoices,
  listOpportunitiesPage,
  listOpportunityLines,
  patchOpportunity,
  type OpportunityRow,
} from '@/api/growth';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { PageTitle } from '@/contextHelp';
import { formatMoney } from '@/utils/money';
import { enumLabel } from '@/utils/enumLabels';
import { t } from '@/i18n';
import { ModuleGate } from '@/pages/erp/erpShared';
import { ProductField } from '@/pages/growth/widgets';
import type { Product } from '@/types/domain';
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

function PipelineInner() {
  const qc = useQueryClient();
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const [selected, setSelected] = useState<number | null>(null);
  const [pendingStage, setPendingStage] = useState<{ id: number; stage: string; title: string } | null>(null);
  const [error, setError] = useState('');
  const list = useQuery({ queryKey: ['opportunities-board'], queryFn: () => listOpportunitiesPage({ pageSize: 100 }) });
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const forecast = useQuery({ queryKey: ['forecast'], queryFn: getForecast });
  const wonVersus = useQuery({
    queryKey: ['won-versus-invoices', month],
    queryFn: () => getWonVersusInvoices(month),
  });
  const move = useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: string }) => patchOpportunity(id, { stage }),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
      void qc.invalidateQueries({ queryKey: ['forecast'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const rows = list.data?.results ?? [];
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
        {wonVersus.data ? (
          <Stack spacing={0.5} sx={{ mt: 1 }}>
            <Typography>{t('growth.wonAmount')}: {wonVersus.data.wonAmount}</Typography>
            <Typography>{t('growth.invoicedAmount')}: {wonVersus.data.invoicedAmount}</Typography>
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
            <Typography variant="subtitle2">{enumLabel('opportunityStage', stage)}</Typography>
            {rows.filter((row) => row.stage === stage).length === 0 ? (
              <Typography variant="caption" color="text.secondary">{t('cog.emptyPipeline')}</Typography>
            ) : null}
            {rows.filter((row) => row.stage === stage).map((row) => (
              <Paper
                key={row.id}
                variant="outlined"
                draggable={!narrow && OPEN_STAGES.has(row.stage)}
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
                {OPEN_STAGES.has(row.stage) ? (
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
          </Paper>
        ))}
      </Stack>
      {selectedRow ? <OpportunityDetail key={selectedRow.id} row={selectedRow} onError={setError} /> : null}
      <ConfirmDialog
        open={Boolean(pendingStage)}
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
      <Typography variant="caption" sx={{ width: 80 }}>{amount}</Typography>
    </Stack>
  );
}

function OpportunityDetail({ row, onError }: { row: OpportunityRow; onError: (message: string) => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
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
      void qc.invalidateQueries({ queryKey: ['opportunities-board'] });
      void qc.invalidateQueries({ queryKey: ['forecast'] });
    },
    onError: (err) => onError(getErrorMessage(err)),
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
      {row.stage === 'WON' ? (
        <Button size="small" sx={{ mt: 1 }} onClick={() => {
          void createInvoiceFromOpportunity(row.id)
            .then((invoice) => navigate(`/sales/history/${invoice.id}`))
            .catch((err) => onError(getErrorMessage(err)));
        }}>{t('growth.createDraftInvoice')}</Button>
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ md: 'center' }}>
        <TextField size="small" type="number" label={t('growth.probability')} value={probability} onChange={(e) => setProbability(e.target.value)} inputProps={{ min: 0, max: 100 }} />
        <TextField size="small" type="date" label={t('growth.closeDate')} value={closeDate} onChange={(e) => setCloseDate(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" label={t('growth.competitor')} value={competitor} onChange={(e) => setCompetitor(e.target.value)} inputProps={{ maxLength: 120 }} />
        <Button variant="contained" onClick={() => save.mutate()}>{t('growth.save')}</Button>
      </Stack>
      <Typography variant="subtitle2" sx={{ mt: 2 }}>{t('growth.lines')}</Typography>
      {(lines.data?.results ?? []).map((line) => (
        <Stack key={line.id} direction="row" spacing={1} alignItems="center">
          <Typography variant="body2">#{line.product} · {line.quantity} × {line.unitPrice}</Typography>
          <Button size="small" onClick={() => removeLine.mutate(line.id)}>{t('growth.remove')}</Button>
        </Stack>
      ))}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ md: 'center' }}>
        <ProductField value={product} onChange={setProduct} />
        <TextField size="small" label={t('growth.quantity')} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <TextField size="small" label={t('growth.unitPrice')} value={price} onChange={(e) => setPrice(e.target.value)} />
        <Button disabled={!product} onClick={() => addLine.mutate()}>{t('growth.addLine')}</Button>
      </Stack>
    </Paper>
  );
}
