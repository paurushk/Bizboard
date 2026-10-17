import { useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
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
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { ChipTabs, chipPanelId, chipTabId } from '@/components/ChipTabs';
import { AttemptKeys } from '@/pages/inventory/attemptKeys';
import * as api from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import {
  qtyFor,
  qtyProblem,
  rowKey,
  splitByExpired,
  supplierReturnHref,
  totalValue,
  writeOffable,
  type ExpiryRow,
} from '@/pages/inventory/expiryHelpers';
import { PageShell } from '@/pages/phase/phaseShared';
import { formatMoney, toNumber } from '@/utils/money';
import { Link as RouterLink } from 'react-router-dom';

type Tab = 'expired' | 'soon';
type Reason = 'EXPIRED' | 'DAMAGED';

export function ExpiryAlertsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [days, setDays] = useState(30);
  const [warehouseId, setWarehouseId] = useState('');
  const [tab, setTab] = useState<Tab>('expired');
  const [touched, setTouched] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [target, setTarget] = useState<ExpiryRow[] | null>(null);
  const [reason, setReason] = useState<Reason>('EXPIRED');
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ done: number; pending: number; failed: string[] } | null>(null);
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const query = useQuery({
    queryKey: ['expiry-alerts', days, warehouseId],
    queryFn: () => api.getExpiryAlerts(days, warehouseId ? Number(warehouseId) : undefined),
    // Keep the list and the filters on screen while another filter loads.
    placeholderData: keepPreviousData,
  });
  // One key per row and attempt: kept while the outcome is unknown, dropped once the server answered.
  const attemptKeys = useRef(new AttemptKeys());
  const rows = useMemo(() => (query.data ?? []) as unknown as ExpiryRow[], [query.data]);
  const { expired, soon } = useMemo(() => splitByExpired(rows), [rows]);
  // Open on whichever list has something in it, until the user picks one.
  const activeTab: Tab = touched ? tab : expired.length === 0 && soon.length > 0 ? 'soon' : 'expired';
  const shown = activeTab === 'expired' ? expired : soon;
  const selectedRows = shown.filter((r) => selected.includes(rowKey(r)));
  const canSelect = (r: ExpiryRow) => writeOffable(r) > 0;

  const openWriteOff = (list: ExpiryRow[]) => {
    setTyped({});
    setResult(null);
    // Stock that has not gone off yet is a different reason from stock that has.
    setReason(list.every((r) => r.expired) ? 'EXPIRED' : 'DAMAGED');
    setTarget(list);
  };

  const confirmWriteOff = async () => {
    if (!target) return;
    setRunning(true);
    const failed: string[] = [];
    const failedRows: ExpiryRow[] = [];
    let done = 0;
    let pending = 0;
    for (const row of target) {
      const name = `${rowKey(row)}:${reason}`;
      try {
        const outcome = await api.writeOffExpiry(
          {
            product: row.product,
            warehouse: row.warehouse,
            batch: row.batch,
            quantity: Number(qtyFor(row, typed)),
            reason,
          },
          { idempotencyKey: attemptKeys.current.get(name) },
        );
        attemptKeys.current.settle(name);
        // 202: the owner has to approve it first; nothing was written off yet.
        if ((outcome as { status?: string } | null)?.status === 'PENDING') pending += 1;
        else done += 1;
      } catch (err) {
        attemptKeys.current.settle(name, err);
        failed.push(`${row.productName} ${row.batchNo}: ${getErrorMessage(err)}`);
        failedRows.push(row);
      }
    }
    setRunning(false);
    setResult({ done, pending, failed });
    setSelected([]);
    for (const key of ['expiry-alerts', 'stock', 'low-stock', 'inventory-summary', 'stock-ledger']) {
      void qc.invalidateQueries({ queryKey: [key] });
    }
    // Rows that went through leave the dialog, so pressing the button again cannot repeat them.
    setTarget(failedRows.length === 0 ? null : failedRows);
  };

  if (query.isLoading && !query.data) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const writeOffTotal = target ? totalValue(target, typed) : null;
  const blocked = !target || target.some((r) => qtyProblem(r, typed));
  const toggle = (key: string) => setSelected((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));
  const allKeys = shown.filter(canSelect).map(rowKey);
  const allSelected = allKeys.length > 0 && allKeys.every((k) => selected.includes(k));

  return (
    <PageShell
      title={t('phase.expiryAlerts')}
      subtitle={t('phase.expiryAlertsSubtitle')}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {[7, 30, 60, 90].map((d) => (
            <Chip
              key={d}
              label={t('inventory.expiryDays', { count: String(d) })}
              color={days === d ? 'primary' : 'default'}
              onClick={() => setDays(d)}
              variant={days === d ? 'filled' : 'outlined'}
            />
          ))}
          <TextField
            select
            size="small"
            label={t('sweep.godown')}
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">{t('sweep2.allGodowns')}</MenuItem>
            {(warehouses.data ?? []).map((warehouse) => (
              <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                {warehouse.name}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      }
    >
      {result ? (
        <Alert severity={result.failed.length ? 'warning' : 'success'} sx={{ mb: 2 }} onClose={() => setResult(null)}>
          {t('inventory.expiryWrittenOff', { count: String(result.done) })}
          {result.pending ? ` ${t('inventory.expiryPending', { count: String(result.pending) })}` : ''}
          {result.failed.length ? ` ${t('inventory.expiryFailed', { count: String(result.failed.length) })} ${result.failed.join(' · ')}` : ''}
        </Alert>
      ) : null}
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <ChipTabs
          idPrefix="expiry"
          label={t('phase.expiryAlerts')}
          value={activeTab}
          onChange={(next) => {
            setTab(next);
            setTouched(true);
          }}
          tabs={[
            { value: 'expired', label: t('inventory.expiryTabExpired', { count: String(expired.length) }) },
            { value: 'soon', label: t('inventory.expiryTabSoon', { count: String(soon.length), days: String(days) }) },
          ]}
        />
        <Button
          variant="contained"
          color="warning"
          size="small"
          disabled={writesBlocked || selectedRows.length === 0}
          onClick={() => openWriteOff(selectedRows)}
        >
          {t('inventory.expiryWriteOffSelected', { count: String(selectedRows.length) })}
        </Button>
      </Stack>
      <div role="tabpanel" id={chipPanelId('expiry')} aria-labelledby={chipTabId('expiry', activeTab)}>
      {shown.length === 0 ? (
        <EmptyState description={activeTab === 'expired' ? t('inventory.expiryNoneExpired') : t('inventory.expiryNoneSoon', { days: String(days) })} />
      ) : (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={allSelected}
                    indeterminate={selectedRows.length > 0 && !allSelected}
                    onChange={() => setSelected(allSelected ? [] : allKeys)}
                    inputProps={{ 'aria-label': t('inventory.expirySelectAll') }}
                  />
                </TableCell>
                <TableCell>{t('common.product')}</TableCell>
                <TableCell>{t('inventory.transferBatch')}</TableCell>
                <TableCell>{t('sweep.godown')}</TableCell>
                <TableCell>{t('inventory.expiryColExpiry')}</TableCell>
                <TableCell align="right">{t('inventory.expiryColOnHand')}</TableCell>
                <TableCell align="right">{t('inventory.expiryColHeld')}</TableCell>
                <TableCell align="right">{t('inventory.expiryColFree')}</TableCell>
                {shown.some((r) => r.value != null) ? <TableCell align="right">{t('inventory.expiryColValue')}</TableCell> : null}
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {shown.map((row) => {
                const key = rowKey(row);
                const free = writeOffable(row);
                return (
                  <TableRow key={key} hover>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selected.includes(key)}
                        disabled={!canSelect(row)}
                        onChange={() => toggle(key)}
                        inputProps={{ 'aria-label': `${row.productName} ${row.batchNo}` }}
                      />
                    </TableCell>
                    <TableCell>{row.productName}</TableCell>
                    <TableCell>{row.batchNo}</TableCell>
                    <TableCell>{row.warehouseName}</TableCell>
                    <TableCell>
                      {row.expiryDate}{' '}
                      <Chip
                        size="small"
                        color={row.expired ? 'error' : 'warning'}
                        label={
                          row.expired
                            ? t('inventory.expiryAgo', { count: String(Math.abs(row.daysToExpiry)) })
                            : t('inventory.expiryLeft', { count: String(row.daysToExpiry) })
                        }
                      />
                    </TableCell>
                    <TableCell align="right">{toNumber(row.onHand)}</TableCell>
                    <TableCell align="right">{toNumber(row.reserved)}</TableCell>
                    <TableCell align="right">{free}</TableCell>
                    {shown.some((r) => r.value != null) ? (
                      <TableCell align="right">{row.value == null ? '—' : formatMoney(row.value)}</TableCell>
                    ) : null}
                    <TableCell align="right">
                      {!row.expired && free > 0 ? (
                        <Button size="small" component={RouterLink} to={`/sales/quick-entry?product=${row.product}`}>
                          {t('inventory.expirySellFirst')}
                        </Button>
                      ) : null}
                      {free > 0 ? (
                        <Button size="small" component={RouterLink} to={supplierReturnHref(row)}>
                          {t('inventory.expiryReturnSupplier')}
                        </Button>
                      ) : null}
                      <Button
                        size="small"
                        color="warning"
                        disabled={writesBlocked || free <= 0}
                        onClick={() => openWriteOff([row])}
                      >
                        {t('sweep2.writeOff')}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      )}
      </div>

      <Dialog open={Boolean(target)} onClose={() => (running ? undefined : setTarget(null))} fullWidth maxWidth="sm">
        <DialogTitle>{t('inventory.expiryDialogTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('inventory.expiryReason')}
              value={reason}
              onChange={(e) => setReason(e.target.value as Reason)}
            >
              <MenuItem value="EXPIRED">{t('inventory.expiryReasonExpired')}</MenuItem>
              <MenuItem value="DAMAGED">{t('inventory.expiryReasonDamaged')}</MenuItem>
            </TextField>
            {target?.some((r) => !r.expired) ? (
              <Alert severity="warning">{t('inventory.expiryNotYet')}</Alert>
            ) : null}
            {(target ?? []).map((row) => {
              const key = rowKey(row);
              const bad = qtyProblem(row, typed);
              return (
                <Stack key={key} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                  <Typography sx={{ flex: 1 }}>
                    {row.productName} · {row.batchNo} · {row.warehouseName}
                  </Typography>
                  <TextField
                    size="small"
                    type="number"
                    label={t('phase.quantity')}
                    value={qtyFor(row, typed)}
                    inputProps={{ min: 0, step: 'any' }}
                    error={bad}
                    helperText={bad ? t('inventory.expiryQtyMax', { qty: String(writeOffable(row)) }) : undefined}
                    onChange={(e) => setTyped((cur) => ({ ...cur, [key]: e.target.value }))}
                    sx={{ width: 150 }}
                  />
                </Stack>
              );
            })}
            {writeOffTotal != null ? (
              <Typography variant="subtitle2">{t('inventory.expiryTotal', { amount: formatMoney(writeOffTotal) })}</Typography>
            ) : null}
            <Typography variant="caption" color="text.secondary">{t('inventory.confirmWriteoff')}</Typography>
            {result?.failed.length ? <Alert severity="error">{result.failed.join(' · ')}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTarget(null)} disabled={running}>{t('common.cancel')}</Button>
          <Button variant="contained" color="warning" disabled={blocked || running || writesBlocked} onClick={() => void confirmWriteOff()}>
            {t('sweep2.writeOff')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
