import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listRouteCandidates } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { AcknowledgeDialog } from './AcknowledgeDialog';
import { OrderDrawer } from './OrderDrawer';
import {
  acknowledgementPayload,
  groupByArea,
  risksToAccept,
  totalsFor,
  whyNotSelectable,
  type Acknowledgements,
  type PlanRisk,
  type PlanSummary,
} from './planningTypes';

const PAGE_SIZE = 25;

export interface PlanningSelection {
  orderIds: number[];
  acknowledgements: Array<{ order: number; code: string; reason: string }>;
}

interface Props {
  /** Load the candidate list only while the screen that hosts the table is open. */
  open: boolean;
  /** Orders already on the route being edited are not offered again. */
  excludeIds?: number[];
  /** Show only these orders (the ones picked on the sales order list). */
  onlyIds?: number[];
  onChange: (selection: PlanningSelection) => void;
}

const LEVEL_COLOR: Record<string, 'error' | 'warning' | 'default'> = { block: 'error', warn: 'warning', info: 'default' };

function RiskChips({ risks }: { risks: PlanRisk[] }) {
  const shown = risks.filter((r) => r.level !== 'info' || risks.length <= 2).slice(0, 3);
  const hidden = risks.length - shown.length;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
      {shown.map((r) => (
        <Tooltip key={r.code} title={r.message}>
          <Chip size="small" color={LEVEL_COLOR[r.level]} variant={r.level === 'info' ? 'outlined' : 'filled'} label={t(`routes.risk.${r.code}`)} />
        </Tooltip>
      ))}
      {hidden > 0 ? <Chip size="small" variant="outlined" label={`+${hidden}`} /> : null}
    </Stack>
  );
}

/**
 * The planning table: what a dispatcher needs to pick orders for a van, in one place (hardening plan PL-20..PL-25).
 * Each row shows the customer and area, when it is wanted, what is on it, the value and what to collect, whether
 * the stock is there, the bill, and the risks in plain words. A row that cannot go cannot be ticked and says why;
 * a row with warnings asks for a reason before it is ticked, and the reason travels with the request. The server
 * checks all of it again.
 */
export function PlanningTable({ open, excludeIds = [], onlyIds, onChange }: Props) {
  const { user } = useAuth();
  const role = user?.role;
  const isOwner = role === 'OWNER';
  const [q, setQ] = useState('');
  const [pincode, setPincode] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showUnavailable, setShowUnavailable] = useState(false);
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [groupArea, setGroupArea] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [acks, setAcks] = useState<Acknowledgements>({});
  const [pending, setPending] = useState<PlanSummary | null>(null);
  const [detail, setDetail] = useState<PlanSummary | null>(null);
  // Summaries of ticked rows are kept so totals stay right when the list pages or filters change.
  const [known, setKnown] = useState<Record<number, PlanSummary>>({});

  const debouncedQ = useDebouncedValue(q, 300);
  const debouncedPin = useDebouncedValue(pincode, 300);
  const query = useQuery({
    queryKey: ['route-candidates', debouncedQ, debouncedPin, dateFrom, dateTo, showUnavailable, includeDrafts, page, onlyIds?.join(',') ?? ''],
    queryFn: async () =>
      (await listRouteCandidates({
        q: debouncedQ.trim() || undefined,
        pincode: debouncedPin.trim() || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        show_unavailable: showUnavailable || undefined,
        include_drafts: includeDrafts || undefined,
        ids: onlyIds && onlyIds.length ? onlyIds.join(',') : undefined,
        page,
        page_size: PAGE_SIZE,
      })) as unknown as { count: number; page: number; pageSize: number; results: PlanSummary[] },
    enabled: open,
    placeholderData: keepPreviousData,
  });

  const rows = (query.data?.results ?? []).filter((r) => !excludeIds.includes(r.order));
  const count = query.data?.count ?? 0;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  const publish = (nextSelected: number[], nextAcks: Acknowledgements) => {
    setSelected(nextSelected);
    setAcks(nextAcks);
    onChange({ orderIds: nextSelected, acknowledgements: acknowledgementPayload(nextAcks) });
  };

  const toggle = (row: PlanSummary, checked: boolean) => {
    if (!checked) {
      const { [row.order]: _dropped, ...rest } = acks;
      void _dropped;
      publish(selected.filter((id) => id !== row.order), rest);
      return;
    }
    setKnown((prev) => ({ ...prev, [row.order]: row }));
    if (risksToAccept(row, role).length > 0) {
      setPending(row);
      return;
    }
    publish([...selected, row.order], acks);
  };

  const accept = (row: PlanSummary, reason: string) => {
    const codes = Object.fromEntries(risksToAccept(row, role).map((r) => [r.code, reason]));
    publish([...selected.filter((id) => id !== row.order), row.order], { ...acks, [row.order]: codes });
    setPending(null);
  };

  // Everything on this page that can go without anyone having to accept a risk.
  const clean = rows.filter((r) => whyNotSelectable(r, role) === null && risksToAccept(r, role).length === 0 && !selected.includes(r.order));
  const selectClean = () => {
    setKnown((prev) => ({ ...prev, ...Object.fromEntries(clean.map((r) => [r.order, r])) }));
    publish([...selected, ...clean.map((r) => r.order)], acks);
  };

  const chosen = selected.map((id) => known[id] ?? rows.find((r) => r.order === id)).filter(Boolean) as PlanSummary[];
  const totals = totalsFor(chosen);
  const warned = Object.values(acks).reduce((n, codes) => n + Object.keys(codes).length, 0);

  const sections = useMemo(
    () => (groupArea ? groupByArea(rows) : [{ pincode: '', rows }]),
    [groupArea, rows],
  );

  const renderRow = (row: PlanSummary) => {
    const stopper = whyNotSelectable(row, role);
    const checked = selected.includes(row.order);
    const blockedMessage = stopper?.message;
    const out = row.lines.some((l) => Number(l.short) > 0);
    return (
      <TableRow key={row.order} hover selected={checked} data-testid={`plan-row-${row.order}`}>
        <TableCell padding="checkbox">
          <Checkbox
            checked={checked}
            disabled={stopper !== null}
            onChange={(e) => toggle(row, e.target.checked)}
            inputProps={{ 'aria-label': t('routes.plan.select', { order: row.number || row.order }) }}
          />
        </TableCell>
        <TableCell>
          <Typography variant="body2" fontWeight={600}>{row.number || `#${row.order}`}</Typography>
          <Typography variant="body2">{row.customer.name}</Typography>
          <Typography variant="caption" color="text.secondary">
            {[row.customer.pincode, row.customer.phone].filter(Boolean).join(' · ') || '—'}
            {row.customer.hasLocation === false ? ` · ${t('routes.plan.noLocation')}` : ''}
          </Typography>
          {blockedMessage ? (
            <Typography variant="caption" color="error" display="block">
              {t('routes.plan.cannotRoute')}: {blockedMessage}
            </Typography>
          ) : null}
        </TableCell>
        <TableCell>{row.expectedDelivery ?? row.orderDate ?? '—'}</TableCell>
        <TableCell align="right">{row.lineCount} / {row.totalQuantity}</TableCell>
        <TableCell align="right">{formatMoney(toNumber(row.grandTotal))}</TableCell>
        <TableCell align="right">
          {row.bill.onCredit ? t('routes.plan.credit') : formatMoney(toNumber(row.bill.amountToCollect))}
        </TableCell>
        <TableCell>
          <Chip size="small" color={out ? 'warning' : 'success'} variant="outlined" label={out ? t('routes.plan.stockShort') : t('routes.plan.stockOk')} />
        </TableCell>
        <TableCell>{t(`routes.bill.${row.bill.billStatus}`)}</TableCell>
        <TableCell><RiskChips risks={row.risks} /></TableCell>
        <TableCell align="right">
          <Button size="small" sx={{ minHeight: 44 }} onClick={() => setDetail(row)}>{t('routes.plan.details')}</Button>
        </TableCell>
      </TableRow>
    );
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField size="small" label={t('common.search')} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} fullWidth />
        <TextField size="small" label={t('routes.plan.pincode')} value={pincode} onChange={(e) => { setPincode(e.target.value); setPage(1); }} sx={{ minWidth: 120 }} />
        <TextField size="small" type="date" label={t('common.from')} InputLabelProps={{ shrink: true }} value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
        <TextField size="small" type="date" label={t('common.to')} InputLabelProps={{ shrink: true }} value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
      </Stack>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <FormControlLabel control={<Checkbox checked={groupArea} onChange={(e) => setGroupArea(e.target.checked)} />} label={t('routes.plan.groupArea')} />
        <FormControlLabel control={<Checkbox checked={showUnavailable} onChange={(e) => { setShowUnavailable(e.target.checked); setPage(1); }} />} label={t('routes.plan.showUnavailable')} />
        <Button size="small" variant="outlined" sx={{ minHeight: 44 }} disabled={clean.length === 0} onClick={selectClean}>
          {t('routes.plan.selectClean', { n: clean.length })}
        </Button>
        {isOwner ? (
          <FormControlLabel control={<Checkbox checked={includeDrafts} onChange={(e) => { setIncludeDrafts(e.target.checked); setPage(1); }} />} label={t('routes.plan.includeDrafts')} />
        ) : null}
      </Stack>
      {query.isError ? <Alert severity="error">{getErrorMessage(query.error)}</Alert> : null}
      <Paper variant="outlined" sx={{ overflow: 'auto' }} tabIndex={0} role="region" aria-label={t('common.scrollableTable')}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox" />
              <TableCell>{t('routes.plan.orderCustomer')}</TableCell>
              <TableCell>{t('routes.plan.wanted')}</TableCell>
              <TableCell align="right">{t('routes.plan.itemsQty')}</TableCell>
              <TableCell align="right">{t('routes.orderTotal')}</TableCell>
              <TableCell align="right">{t('routes.toCollect')}</TableCell>
              <TableCell>{t('routes.plan.stock')}</TableCell>
              <TableCell>{t('routes.billLabel')}</TableCell>
              <TableCell>{t('routes.plan.risks')}</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && !query.isLoading ? (
              <TableRow><TableCell colSpan={10}><Typography variant="body2" color="text.secondary">{t('routes.noOrdersToAdd')}</Typography></TableCell></TableRow>
            ) : null}
            {sections.map((section) => [
              groupArea ? (
                <TableRow key={`g-${section.pincode}`}>
                  <TableCell colSpan={10} sx={{ bgcolor: 'action.hover' }}>
                    <Typography variant="subtitle2">
                      {t('routes.plan.area', { pincode: section.pincode, n: section.rows.length })}
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : null,
              ...section.rows.map(renderRow),
            ])}
          </TableBody>
        </Table>
      </Paper>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography variant="body2" data-testid="plan-totals">
          {t('routes.plan.selected', {
            n: totals.orders,
            qty: totals.quantity,
            value: formatMoney(totals.value),
            collect: formatMoney(totals.toCollect),
          })}
          {warned > 0 ? ` · ${t('routes.plan.acceptedCount', { n: warned })}` : ''}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Button size="small" sx={{ minHeight: 44 }} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
          <Typography variant="body2">{page} / {pages}</Typography>
          <Button size="small" sx={{ minHeight: 44 }} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </Stack>
      </Stack>

      <AcknowledgeDialog
        open={pending !== null}
        title={pending?.number || `#${pending?.order ?? ''}`}
        risks={pending ? risksToAccept(pending, role) : []}
        onCancel={() => setPending(null)}
        onConfirm={(reason) => pending && accept(pending, reason)}
      />
      <OrderDrawer summary={detail} onClose={() => setDetail(null)} />
    </Stack>
  );
}
