/* eslint-disable react-refresh/only-export-components -- shared helpers and small presentational pieces for the manufacturing screens */
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { errorCode, searchBatches, type BatchHit } from '@/api/mfg';
import { listCustomers, listProducts, listSuppliers, listWarehouses } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { ErrorState, LoadingState } from '@/components/PageState';
import { ModuleGate } from '@/pages/erp/erpShared';
import { PageShell } from '@/pages/phase/phaseShared';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { formatDocumentDate, todayIsoInTimeZone } from '@/utils/documentDate';
import { formatMoney, toNumber } from '@/utils/money';
import {
  canPlanManufacturing,
  canSeeMfgCosts,
  canWorkManufacturing,
} from '@/utils/permissions';

/** A quantity from the server ("12.500") shown without the trailing zeros. */
export function qty(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

export function money(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  return formatMoney(toNumber(v));
}

export function day(v: string | null | undefined): string {
  if (!v) return '—';
  // A date without a time is shown as written; parsing it as a moment would shift it by the viewer's zone.
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return formatDocumentDate(v);
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString();
}

export function stamp(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString();
}

/** Today's date in India, the books' calendar (not UTC, which is yesterday for the first five hours of an Indian day). */
export const todayIso = () => todayIsoInTimeZone('Asia/Kolkata');

/** The year the current financial year (April to March) started in: January to March belong to the year before. */
export function fyStartYear(today: string = todayIso()): number {
  const [y, m] = today.split('-').map(Number);
  return m >= 4 ? y : y - 1;
}

/** What the signed-in user may do here; the server enforces the same rules. */
export function useMfgRights() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  return {
    user,
    canWork: canWorkManufacturing(user) && !writesBlocked,
    canPlan: canPlanManufacturing(user) && !writesBlocked,
    canCosts: canSeeMfgCosts(user),
    writesBlocked,
  };
}

/** One shared fetch of the lists every picker needs. */
export function useMasters() {
  const products = useQuery({ queryKey: ['mfg-products'], queryFn: () => listProducts(), staleTime: 60_000 });
  const warehouses = useQuery({ queryKey: ['mfg-warehouses'], queryFn: () => listWarehouses(), staleTime: 60_000 });
  const suppliers = useQuery({ queryKey: ['mfg-suppliers'], queryFn: () => listSuppliers(), staleTime: 60_000 });
  const customers = useQuery({ queryKey: ['mfg-customers'], queryFn: () => listCustomers(), staleTime: 60_000 });
  const productName = useMemo(() => {
    const m = new Map<number, string>();
    (products.data ?? []).forEach((p) => m.set(p.id, p.name));
    return (id: number | null | undefined) => (id == null ? '—' : (m.get(id) ?? `#${id}`));
  }, [products.data]);
  const warehouseName = useMemo(() => {
    const m = new Map<number, string>();
    (warehouses.data ?? []).forEach((w) => m.set(w.id, w.name));
    return (id: number | null | undefined) => (id == null ? '—' : (m.get(id) ?? `#${id}`));
  }, [warehouses.data]);
  return {
    products: products.data ?? [],
    warehouses: warehouses.data ?? [],
    suppliers: suppliers.data ?? [],
    customers: customers.data ?? [],
    productName,
    warehouseName,
  };
}

type Opt = { id: number; name: string; sub?: string };

function Pick({
  label,
  value,
  onChange,
  options,
  disabled,
  required,
  size = 'small',
}: {
  label: string;
  value: number | '' | null;
  onChange: (id: number | '') => void;
  options: Opt[];
  disabled?: boolean;
  required?: boolean;
  size?: 'small' | 'medium';
}) {
  const current = options.find((o) => o.id === value) ?? null;
  return (
    <Autocomplete
      size={size}
      options={options}
      value={current}
      disabled={disabled}
      getOptionLabel={(o) => (o.sub ? `${o.name} (${o.sub})` : o.name)}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onChange={(_, o) => onChange(o ? o.id : '')}
      renderInput={(params) => <TextField {...params} label={label} required={required} />}
      sx={{ minWidth: 200 }}
    />
  );
}

export function ProductPick(props: {
  label?: string;
  value: number | '' | null;
  onChange: (id: number | '') => void;
  disabled?: boolean;
  required?: boolean;
  role?: string;
}) {
  const { products } = useMasters();
  const options = useMemo(
    () =>
      products
        .filter((p) => !props.role || (p as { mfgRole?: string }).mfgRole === props.role)
        .map((p) => ({ id: p.id, name: p.name, sub: p.sku })),
    [products, props.role],
  );
  return <Pick {...props} label={props.label ?? t('mfg.common.item')} options={options} />;
}

/** Type to find a lot by its number; optionally only lots of one item. */
export function BatchPick({
  label,
  value,
  onChange,
  product,
}: {
  label?: string;
  value: BatchHit | null;
  onChange: (hit: BatchHit | null) => void;
  product?: number | null;
}) {
  const [text, setText] = useState('');
  const found = useQuery({
    queryKey: ['mfg-batch-search', text, product ?? null],
    queryFn: () => searchBatches(text, product ?? undefined),
    staleTime: 15_000,
  });
  return (
    <Autocomplete
      size="small"
      sx={{ minWidth: 260 }}
      options={found.data ?? []}
      value={value}
      getOptionLabel={(o) => `${o.batchNo} · ${o.productName}`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      filterOptions={(x) => x}
      onInputChange={(_, v) => setText(v)}
      onChange={(_, v) => onChange(v)}
      renderInput={(p) => <TextField {...p} label={label ?? t('mfg.common.batchNo')} />}
    />
  );
}

export function WarehousePick(props: {
  label?: string;
  value: number | '' | null;
  onChange: (id: number | '') => void;
  disabled?: boolean;
}) {
  const { warehouses } = useMasters();
  const options = useMemo(() => warehouses.map((w) => ({ id: w.id, name: w.name })), [warehouses]);
  return <Pick {...props} label={props.label ?? t('mfg.common.warehouse')} options={options} />;
}

export function SupplierPick(props: { label?: string; value: number | '' | null; onChange: (id: number | '') => void }) {
  const { suppliers } = useMasters();
  const options = useMemo(() => suppliers.map((s) => ({ id: s.id, name: s.name })), [suppliers]);
  return <Pick {...props} label={props.label ?? t('mfg.common.supplier')} options={options} />;
}

export function CustomerPick(props: { label?: string; value: number | '' | null; onChange: (id: number | '') => void }) {
  const { customers } = useMasters();
  const options = useMemo(() => customers.map((c) => ({ id: c.id, name: c.name })), [customers]);
  return <Pick {...props} label={props.label ?? t('mfg.common.customer')} options={options} />;
}

/** Run a server call, keep its error (with the code the server put on it) for display. */
export function useRun() {
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    setCode('');
    try {
      return await fn();
    } catch (err) {
      setError(getErrorMessage(err));
      setCode(errorCode(err));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  const clear = useCallback(() => {
    setError(null);
    setCode('');
  }, []);
  return { run, busy, error, code, clear };
}

export function ErrorLine({ error, onClose }: { error: string | null; onClose?: () => void }) {
  if (!error) return null;
  return (
    <Alert severity="error" onClose={onClose}>
      {error}
    </Alert>
  );
}

/** The page frame every manufacturing screen uses: module switch, then title bar. */
export function MfgPage({
  title,
  subtitle,
  actions,
  flag,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /** A sub-module switch (for example MFG_QUALITY); the screen explains itself when it is off. */
  flag?: string;
  children: ReactNode;
}) {
  return (
    <ModuleGate module="manufacturing" title={title}>
      {flag && !isRuntimeFlagEnabled(flag) ? (
        <PageShell title={title}>
          <Alert severity="info">{t('mfg.common.subModuleOff')}</Alert>
        </PageShell>
      ) : (
        <PageShell title={title} subtitle={subtitle} actions={actions}>
          {children}
        </PageShell>
      )}
    </ModuleGate>
  );
}

export type Col<R> = {
  key: string;
  label: string;
  render: (row: R) => ReactNode;
  align?: 'left' | 'right';
  hide?: boolean;
};

/** The parts of a react-query result the grid needs to tell loading and failure apart from "none". */
export type GridQuery = { isLoading: boolean; isError: boolean; error: unknown; refetch: () => unknown };

export function Grid<R>({
  rows,
  cols,
  rowKey,
  empty,
  onRow,
  dense = true,
  query,
}: {
  rows: R[];
  cols: Col<R>[];
  rowKey: (r: R) => string | number;
  empty?: string;
  onRow?: (r: R) => void;
  dense?: boolean;
  /** The query the rows come from (QOS-0098): shows loading and a retryable error instead of "nothing yet". */
  query?: GridQuery;
}) {
  const shown = cols.filter((c) => !c.hide);
  if (query?.isLoading) return <LoadingState />;
  if (query?.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!rows.length) {
    return (
      <Typography color="text.secondary" sx={{ py: 2 }}>
        {empty ?? t('mfg.common.nothingYet')}
      </Typography>
    );
  }
  return (
    <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
      <Table size={dense ? 'small' : 'medium'}>
        <TableHead>
          <TableRow>
            {shown.map((c) => (
              <TableCell key={c.key} align={c.align ?? 'left'} sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                {c.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={rowKey(r)} hover={!!onRow} onClick={onRow ? () => onRow(r) : undefined} sx={onRow ? { cursor: 'pointer' } : undefined}>
              {shown.map((c) => (
                <TableCell key={c.key} align={c.align ?? 'left'}>
                  {c.render(r)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}

/** A labelled number or text on a summary strip. */
export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: 'warn' | 'bad' | 'good' }) {
  const color = tone === 'bad' ? 'error.main' : tone === 'warn' ? 'warning.main' : tone === 'good' ? 'success.main' : 'text.primary';
  return (
    <Paper variant="outlined" sx={{ px: 2, py: 1.25, minWidth: 140 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6" sx={{ color, fontWeight: 600 }}>
        {value}
      </Typography>
    </Paper>
  );
}

export function Pill({ value, tone }: { value: string; tone?: 'default' | 'success' | 'warning' | 'error' | 'info' }) {
  const text = t(`mfg.status.${value}`);
  const label = text === `mfg.status.${value}` ? value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, ' ') : text;
  const auto: Record<string, 'default' | 'success' | 'warning' | 'error' | 'info'> = {
    DRAFT: 'default',
    RELEASED: 'info',
    IN_PROGRESS: 'info',
    COMPLETED: 'success',
    CLOSED: 'success',
    POSTED: 'success',
    CANCELLED: 'error',
    REVERSED: 'default',
    ACTIVE: 'success',
    ARCHIVED: 'default',
    PASS: 'success',
    FAIL: 'error',
    HOLD: 'warning',
    REWORK: 'warning',
    PENDING: 'default',
    OPEN: 'warning',
    OVERDUE: 'error',
    ALERT: 'warning',
    OK: 'success',
    ISSUED: 'info',
    FILED: 'success',
    EXPORTED: 'info',
    RELEASED_LOT: 'success',
    QUARANTINE: 'warning',
    REJECTED: 'error',
    DONE: 'success',
    PLANNED: 'default',
    PAUSED: 'warning',
  };
  return <Chip size="small" label={label} color={tone ?? auto[value] ?? 'default'} variant={(tone ?? auto[value]) ? 'filled' : 'outlined'} />;
}

/** Tabs that keep their choice in the page, with the panels rendered lazily. */
export function TabPanels({
  tabs,
  initial = 0,
}: {
  tabs: Array<{ key: string; label: string; hide?: boolean; node: () => ReactNode }>;
  initial?: number;
}) {
  const visible = tabs.filter((x) => !x.hide);
  const [idx, setIdx] = useState(Math.min(initial, Math.max(visible.length - 1, 0)));
  const current = visible[Math.min(idx, visible.length - 1)];
  return (
    <Stack spacing={2}>
      <Tabs value={Math.min(idx, visible.length - 1)} onChange={(_, v) => setIdx(v)} variant="scrollable" scrollButtons="auto">
        {visible.map((x) => (
          <Tab key={x.key} label={x.label} />
        ))}
      </Tabs>
      <Box>{current?.node()}</Box>
    </Stack>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  size = 'small',
  disabled,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
  size?: 'small' | 'medium';
  disabled?: boolean;
}) {
  return (
    <TextField select size={size} label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value as T)} sx={{ minWidth: 160 }}>
      {options.map((o) => (
        <MenuItem key={o.value} value={o.value}>
          {o.label}
        </MenuItem>
      ))}
    </TextField>
  );
}

/** A decimal field that only lets digits and one point through. */
export function NumField({
  label,
  value,
  onChange,
  disabled,
  width = 120,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  width?: number;
  helperText?: string;
}) {
  return (
    <TextField
      size="small"
      label={label}
      value={value}
      disabled={disabled}
      helperText={helperText}
      inputProps={{ inputMode: 'decimal' }}
      onChange={(e) => {
        const v = e.target.value;
        if (v === '' || /^\d*\.?\d{0,4}$/.test(v)) onChange(v);
      }}
      sx={{ width }}
    />
  );
}
