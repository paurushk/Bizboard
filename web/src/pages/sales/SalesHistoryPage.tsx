import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import CancelOutlinedIcon from '@mui/icons-material/CancelOutlined';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined';
import PictureAsPdfOutlinedIcon from '@mui/icons-material/PictureAsPdfOutlined';
import ShareOutlinedIcon from '@mui/icons-material/ShareOutlined';
import { ShareInvoiceDialog } from '@/components/ShareInvoiceDialog';
import { RecordInvoicePaymentDialog } from '@/components/RecordInvoicePaymentDialog';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { getErrorCode, getErrorMessage, newIdempotencyKey } from '@/api/client';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import {
  cancelSalesInvoice,
  completeSalesInvoice,
  deleteSalesInvoice,
  downloadInvoicePdf,
  downloadInvoiceThermalPdf,
  getCustomer,
  listSalesInvoicesPage,
  getInvoicePaymentStats,
  bulkInvoicePdfZip,
  downloadBulkInvoicePdfZip,
  exportSalesRegisterCsv,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { isSetupWizardEnabled } from '@/config/features';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { HelpEmptyLink } from '@/pages/help/HelpEmptyLink';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { StatusChip } from '@/components/StatusChip';
import {
  HistoryFilterBar,
  EMPTY_HISTORY_FILTERS,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { formatMoney, toNumber } from '@/utils/money';
import { ProfitDetailsDialog } from '@/components/ProfitDetailsDialog';
import { canCreateSales, canCancelDocuments, canCreatePayments, canViewFinancialReports } from '@/utils/permissions';
import { documentStatusTone, invoiceDisplayStatus, statusLabelKey } from '@/utils/status';
import { documentSearchQuery, shortDocumentNumber } from '@/utils/documentNumber';
import { formatDocumentDate, isOverdueDueDate, todayIsoInTimeZone } from '@/utils/documentDate';
import { invalidateInvoiceSideEffects } from '@/pages/sales/invalidateInvoiceSideEffects';

const SORTS = ['date_desc', 'date_asc', 'total_desc', 'total_asc', 'due_desc', 'due_asc'] as const;
type HistorySort = (typeof SORTS)[number];
const HEADER_CHROME = 56;

function readSort(raw: string | null): HistorySort {
  return (SORTS as readonly string[]).includes(raw ?? '') ? (raw as HistorySort) : 'date_desc';
}

const PAGE_SIZE = 50;

function invoiceNumberLabel(inv: SalesInvoice): string {
  if (inv.number && inv.number.trim()) return inv.number;
  return `Draft #${inv.id}`;
}

function writeHistoryParams(
  filters: HistoryFilters,
  page: number,
  sort: HistorySort,
  customerId: number | '',
): URLSearchParams {
  const next = new URLSearchParams();
  if (filters.q) next.set('q', filters.q);
  if (filters.status) next.set('status', filters.status);
  if (filters.paymentStatus) next.set('payment', filters.paymentStatus);
  if (filters.overdue) next.set('overdue', '1');
  if (customerId) next.set('customer', String(customerId));
  if (filters.dateFrom) next.set('from', filters.dateFrom);
  if (filters.dateTo) next.set('to', filters.dateTo);
  if (sort !== 'date_desc') next.set('sort', sort);
  if (page > 1) next.set('page', String(page));
  return next;
}

export function SalesHistoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();
  const narrow = useMediaQuery('(max-width:599px)');
  const [page, setPage] = useState(() => {
    const raw = Number(searchParams.get('page') || '1');
    return Number.isInteger(raw) && raw > 0 ? raw : 1;
  });
  const [sort, setSort] = useState<HistorySort>(() => readSort(searchParams.get('sort')));
  const [filters, setFilters] = useState<HistoryFilters>(() => ({
    ...EMPTY_HISTORY_FILTERS,
    q: searchParams.get('q') ?? '',
    status: searchParams.get('status') ?? '',
    paymentStatus: searchParams.get('payment') ?? '',
    overdue: searchParams.get('overdue') === '1',
    dateFrom: searchParams.get('from') ?? '',
    dateTo: searchParams.get('to') ?? '',
  }));
  const [customerId, setCustomerId] = useState<number | ''>(() => {
    const raw = searchParams.get('customer') ?? '';
    return /^\d+$/.test(raw) ? Number(raw) : '';
  });
  const selectedCustomer = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: typeof customerId === 'number',
  });
  const customerSearch = useCustomerSearch({ selected: selectedCustomer.data ?? null });
  const debouncedQ = useDebouncedValue(filters.q, 300);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const menuButtonRef = useRef<HTMLElement | null>(null);
  const [active, setActive] = useState<SalesInvoice | null>(null);
  const [shareTarget, setShareTarget] = useState<SalesInvoice | null>(null);
  const [profitTarget, setProfitTarget] = useState<SalesInvoice | null>(null);
  const [payTarget, setPayTarget] = useState<SalesInvoice | null>(null);
  const [completeTarget, setCompleteTarget] = useState<SalesInvoice | null>(null);
  const [cancelTarget, setCancelTarget] = useState<SalesInvoice | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  const [pdfRetry, setPdfRetry] = useState<{ id: number; mode: 'print' | 'download' | 80 | 58 } | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [cancelBlocked, setCancelBlocked] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const completeKey = useRef('');
  const [lastWritten, setLastWritten] = useState(() => searchParams.toString());
  const [seenUrl, setSeenUrl] = useState(() => searchParams.toString());
  const prevPage = useRef(page);
  const prevVisible = useRef<number[]>([]);
  const [messageTone, setMessageTone] = useState<'success' | 'warning'>('success');
  const [message, setMessage] = useState<string | null>(() => {
    const flash = location.state as { message?: unknown } | null;
    return typeof flash?.message === 'string' ? flash.message : null;
  });
  const [error, setError] = useState<string | null>(() => {
    const flash = location.state as { paymentWarning?: unknown } | null;
    return typeof flash?.paymentWarning === 'string' ? flash.paymentWarning : null;
  });

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
  }, []);
  const publish = (
    nextFilters: HistoryFilters,
    nextPage: number,
    nextSort: HistorySort,
    nextCustomer: number | '',
    replace = false,
  ) => {
    if (searchTimer.current) {
      clearTimeout(searchTimer.current);
      searchTimer.current = null;
    }
    const params = writeHistoryParams(nextFilters, nextPage, nextSort, nextCustomer);
    setLastWritten(params.toString());
    setPage(nextPage);
    setSearchParams(params, { replace });
  };

  const togglePaymentBucket = (event: MouseEvent<HTMLElement>) => {
    const bucket = event.currentTarget.dataset.bucket ?? '';
    const next = bucket === 'OVERDUE'
      ? { ...filters, overdue: !filters.overdue }
      : { ...filters, paymentStatus: filters.paymentStatus === bucket ? '' : bucket };
    setFilters(next);
    publish(next, 1, sort, customerId);
  };

  const urlSig = searchParams.toString();
  if (urlSig !== seenUrl) setSeenUrl(urlSig);
  if (urlSig !== seenUrl && urlSig !== lastWritten) {
    setLastWritten(urlSig);
    const rawPage = Number(searchParams.get('page') || '1');
    const nextSort = readSort(searchParams.get('sort'));
    const nextFilters: HistoryFilters = {
      ...EMPTY_HISTORY_FILTERS,
      q: searchParams.get('q') ?? '',
      status: searchParams.get('status') ?? '',
      paymentStatus: searchParams.get('payment') ?? '',
      overdue: searchParams.get('overdue') === '1',
      dateFrom: searchParams.get('from') ?? '',
      dateTo: searchParams.get('to') ?? '',
    };
    const rawCustomer = searchParams.get('customer') ?? '';
    const nextCustomer = /^\d+$/.test(rawCustomer) ? Number(rawCustomer) : '';
    setPage(Number.isInteger(rawPage) && rawPage > 0 ? rawPage : 1);
    setSort(nextSort);
    setFilters(nextFilters);
    setCustomerId(nextCustomer);
  }

  const query = useQuery({
    queryKey: ['sales-invoices', page, sort, filters.status, filters.paymentStatus, filters.overdue ?? false, debouncedQ, filters.dateFrom, filters.dateTo, customerId],
    queryFn: () =>
      listSalesInvoicesPage({
        page,
        pageSize: PAGE_SIZE,
        status: filters.status || undefined,
        q: debouncedQ ? documentSearchQuery(debouncedQ) : undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
        payment_status: filters.paymentStatus || undefined,
        overdue: filters.overdue ? 1 : undefined,
        customer: customerId || undefined,
        sort,
      }),
    placeholderData: keepPreviousData,
    staleTime: 0,
    refetchOnMount: 'always',
  });
  const hidePaymentChips = filters.status === 'DRAFT' || filters.status === 'CANCELLED';
  const stats = useQuery({
    queryKey: ['sales-invoice-payment-stats', filters.status, debouncedQ, filters.dateFrom, filters.dateTo, customerId],
    queryFn: () =>
      getInvoicePaymentStats({
        status: filters.status || undefined,
        q: debouncedQ ? documentSearchQuery(debouncedQ) : undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
        customer: customerId || undefined,
      }),
    enabled: !hidePaymentChips,
  });

  const closeMenu = (restoreFocus = true) => {
    setMenuAnchor(null);
    setActive(null);
    if (restoreFocus) menuButtonRef.current?.focus();
  };

  const invalidate = (invoiceId?: number) => invalidateInvoiceSideEffects(qc, invoiceId);

  const completeMutation = useMutation({
    // One key for the confirm dialog and every confirm-flag retry of that gesture.
    mutationFn: (id: number) =>
      completeWithConfirms((extra) =>
        completeSalesInvoice(id, { ...extra, idempotencyKey: completeKey.current }),
      ),
    onSuccess: (inv) => {
      setMessageTone('success');
      setMessage(t('history.completed', { label: invoiceNumberLabel(inv) }));
      setCompleteTarget(null);
      invalidate(inv.id);
    },
    onError: (err, id) => {
      // Close the dialog first: an alert behind its backdrop is not a shown error.
      setCompleteTarget(null);
      const code = getErrorCode(err);
      const text = getErrorMessage(err);
      if (code === 'below_cost' || code === 'gst_guard_blocked' || /schedule\s*h|patient|prescriber|prescription/i.test(text)) {
        navigate(`/sales/history/${id}/edit`, { state: { message: text } });
        return;
      }
      setError(text);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (row: SalesInvoice) => cancelSalesInvoice(row.id, { reason: cancelReason.trim() }),
    onSuccess: (result, row) => {
      if (result.outcome === 'pending') {
        setMessageTone('warning');
        setMessage(t('history.cancelPending', { label: invoiceNumberLabel(row) }));
      } else {
        setMessageTone('success');
        setMessage(t('history.cancelled', { label: invoiceNumberLabel(result.invoice) }));
      }
      setCancelTarget(null);
      setCancelReason('');
      invalidate(row.id);
    },
    onError: (err) => {
      setCancelTarget(null);
      setCancelReason('');
      const text = getErrorMessage(err);
      setCancelBlocked(/allocation|online payment|receipt/i.test(text));
      setError(text);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteSalesInvoice(id),
    onSuccess: (_data, id) => {
      setMessageTone('success');
      setMessage(t('history.draftDeleted'));
      setSelected((prev) => prev.filter((item) => item !== id));
      invalidate(id);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const notePdfFailure = (err: unknown, id: number, mode: 'print' | 'download' | 80 | 58) => {
    if (axios.isAxiosError(err) && err.response?.status === 409) {
      setPdfRetry({ id, mode });
      setMessage(t('history.pdfGenerating'));
      return;
    }
    setPdfRetry(null);
    setError(getErrorMessage(err));
  };

  const runPdf = async (mode: 'print' | 'download', row: SalesInvoice = active!) => {
    if (!row) return;
    const id = row.id;
    const label = invoiceNumberLabel(row);
    closeMenu(false);
    try {
      const blob = await downloadInvoicePdf(id, { copy: 'ORIGINAL' });
      setPdfRetry(null);
      if (mode === 'print') printBlob(blob);
      else triggerBlobDownload(blob, `${label}.pdf`);
    } catch (err) {
      notePdfFailure(err, id, mode);
    }
  };

  const runThermalPrint = async (width: 80 | 58, row: SalesInvoice = active!) => {
    if (!row) return;
    const id = row.id;
    closeMenu(false);
    try {
      const blob = await downloadInvoiceThermalPdf(id, width);
      setPdfRetry(null);
      printBlob(blob);
    } catch (err) {
      notePdfFailure(err, id, width);
    }
  };

  // Date, Total and Due headers cycle newest/highest first, then the other way, then the default.
  const columnSort = (column: 'date' | 'total' | 'due'): 'asc' | 'desc' | null => {
    if (sort === `${column}_desc`) return 'desc';
    if (sort === `${column}_asc`) return 'asc';
    return null;
  };
  const ariaSort = (column: 'date' | 'total' | 'due') => {
    const dir = columnSort(column);
    return dir === 'desc' ? 'descending' : dir === 'asc' ? 'ascending' : 'none';
  };
  const cycleSort = (column: 'date' | 'total' | 'due') => {
    const dir = columnSort(column);
    const next: HistorySort = dir === null ? `${column}_desc` : dir === 'desc' ? `${column}_asc` : 'date_desc';
    setSort(next);
    publish(filters, 1, next, customerId);
  };
  const sortHeader = (column: 'date' | 'total' | 'due', label: string) => (
    <TableSortLabel active={columnSort(column) !== null} direction={columnSort(column) ?? 'desc'} onClick={() => cycleSort(column)}>
      {label}
    </TableSortLabel>
  );

  const busy =
    completeMutation.isPending || cancelMutation.isPending || deleteMutation.isPending;

  const rows = useMemo(() => query.data?.results ?? [], [query.data]);
  const filtersActive = Boolean(
    filters.status || filters.paymentStatus || filters.overdue || debouncedQ || filters.dateFrom || filters.dateTo || customerId,
  );
  const filterSig = [filters.status, filters.paymentStatus ?? '', filters.overdue ? 'o' : '', debouncedQ, filters.dateFrom, filters.dateTo, customerId, sort].join('|');
  const [selectionSig, setSelectionSig] = useState(filterSig);
  if (selectionSig !== filterSig) {
    setSelectionSig(filterSig);
    setSelected([]);
  }
  useEffect(() => {
    const visible = rows.map((row) => row.id);
    if (prevPage.current === page) {
      const gone = new Set(prevVisible.current.filter((id) => !visible.includes(id)));
      if (gone.size) setSelected((prev) => prev.filter((id) => !gone.has(id)));
    }
    prevPage.current = page;
    prevVisible.current = visible;
  }, [rows, page]);
  // A saved or shared link can point past the last page after bills are removed.
  const pageGone = query.isError && page > 1 && axios.isAxiosError(query.error) && query.error.response?.status === 404;
  useEffect(() => {
    // Moving the address bar in answer to a server result is a real side effect, not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (pageGone) publish(filters, 1, sort, customerId, true);
    // publish closes over current state; only the 404 transition should fire it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageGone]);
  const showLoading = query.isPending || (query.isFetching && rows.length === 0);
  const showEmpty = !showLoading && !query.isError && rows.length === 0 && !filtersActive;
  const showNoMatches =
    !showLoading && !query.isError && rows.length === 0 && filtersActive;
  const allowCreate = canCreateSales(user);
  const allowPay = canCreatePayments(user);
  const allowCancel = canCancelDocuments(user);
  const today = todayIsoInTimeZone('Asia/Kolkata');
  const count = query.data?.count ?? 0;
  const rangeStart = count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, count);
  const columnCount = narrow ? 8 : 9;
  const canContinueSetup =
    isSetupWizardEnabled() &&
    user?.role === 'OWNER' &&
    !user.company?.onboarding?.activationDone;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Stack>
          <PageTitle>{t('nav.salesHistory')}</PageTitle>
          <Typography variant="body2" color="text.secondary">{t('history.subtitle')}</Typography>
        </Stack>
        {allowCreate ? (
          <Button component={RouterLink} to="/sales/new" variant="contained">
            {t('nav.newInvoice')}
          </Button>
        ) : null}
      </Stack>

      {message ? (
        <Alert
          severity={pdfRetry ? 'info' : messageTone}
          onClose={() => { setMessage(null); setPdfRetry(null); }}
          action={pdfRetry ? (
            <Button color="inherit" size="small" onClick={() => {
              const row = rows.find((item) => item.id === pdfRetry.id);
              if (!row) return;
              if (pdfRetry.mode === 'print' || pdfRetry.mode === 'download') void runPdf(pdfRetry.mode, row);
              else void runThermalPrint(pdfRetry.mode, row);
            }}
            >
              {t('history.retryPdf')}
            </Button>
          ) : undefined}
        >
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} onClose={() => { setError(null); setCancelBlocked(false); }} />
      ) : null}
      {error && cancelBlocked ? (
        <Button component={RouterLink} to="/sales/receipts" size="small" variant="outlined" sx={{ alignSelf: 'flex-start' }}>
          {t('history.openReceipts')}
        </Button>
      ) : null}

      {/* Filters stay up when the list fails, so the user can change them instead of only retrying. */}
      <>
        <HistoryFilterBar
          party={
            <Autocomplete
              options={customerSearch.options}
              filterOptions={(options) => options}
              loading={customerSearch.isFetching}
              value={selectedCustomer.data ?? null}
              inputValue={customerSearch.query || selectedCustomer.data?.name || ''}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              getOptionLabel={(option) => option.name}
              noOptionsText={customerSearch.query.trim().length === 1 ? t('history.typeTwoCharacters') : t('common.noResults')}
              onInputChange={(_, value, reason) => {
                if (reason === 'input') customerSearch.setQuery(value);
                if (reason === 'clear') {
                  customerSearch.setQuery('');
                  setCustomerId('');
                  setPage(1);
                  publish(filters, 1, sort, '');
                }
              }}
              onChange={(_, option) => {
                const nextId = option?.id ?? '';
                setCustomerId(nextId);
                setPage(1);
                publish(filters, 1, sort, nextId);
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  size="small"
                  label={t('cog.customerFilter')}
                  helperText={customerSearch.query.trim().length === 1 ? t('history.typeTwoCharacters') : undefined}
                />
              )}
              sx={{ maxWidth: 320 }}
            />
          }
          value={filters}
          onChange={(next) => {
            const onlySearch = next.status === filters.status
              && (next.paymentStatus ?? '') === (filters.paymentStatus ?? '')
              && next.dateFrom === filters.dateFrom
              && next.dateTo === filters.dateTo
              && next.q !== filters.q;
            setFilters(next);
            if (onlySearch) {
              if (searchTimer.current) clearTimeout(searchTimer.current);
              // The address bar changes at once on Back; the rendered location can lag behind it.
              const scheduledAt = window.location.href;
              searchTimer.current = setTimeout(() => {
                // Back or Forward while typing wins over the pending search.
                if (window.location.href !== scheduledAt) return;
                publish(next, 1, sort, customerId, true);
              }, 300);
              return;
            }
            publish(next, 1, sort, customerId);
          }}
          searchLabel={t('history.searchLabel')}
          dateControl="preset"
          statusOptions={[
            { value: 'DRAFT', label: t('status.draft') },
            { value: 'COMPLETED', label: t('status.completed') },
            { value: 'CANCELLED', label: t('status.cancelled') },
            { value: 'RETURNED', label: t('status.returned') },
          ]}
          dateRangePresets
          bulkSelectedCount={selected.length}
          bulkActions={!allowCreate ? undefined : (
            <Button
              size="small"
              variant="outlined"
              disabled={bulkBusy || selected.length === 0}
              onClick={async () => {
                setBulkBusy(true);
                setError(null);
                try {
                  const res = await bulkInvoicePdfZip(selected);
                  const included = res.included ?? [];
                  if (!included.length || !res.fileId) {
                    setError(t('history.bulkNone'));
                    return;
                  }
                  triggerBlobDownload(await downloadBulkInvoicePdfZip(res.fileId), 'invoices.zip');
                  const skipped = res.skipped ?? [];
                  const named = skipped.filter((row) => row.number).map((row) => row.number);
                  const unavailable = skipped.filter((row) => !row.number).length;
                  const parts = [t('history.bulkDone', { count: included.length })];
                  if (named.length) parts.push(t('history.bulkSkipped', { numbers: named.join(', ') }));
                  if (unavailable) parts.push(t('history.bulkUnavailable', { count: unavailable }));
                  setMessageTone(skipped.length ? 'warning' : 'success');
                  setMessage(parts.join(' '));
                } catch (err) {
                  setError(getErrorMessage(err));
                } finally {
                  setBulkBusy(false);
                }
              }}
            >
              {t('history.bulkDownload')}
            </Button>
          )}
          onClearBulk={() => setSelected([])}
          layout="compact"
          controls={(
          <TextField
            select
            size="small"
            label={t('history.sortBy')}
            value={sort}
            onChange={(event) => {
              const next = event.target.value as HistorySort;
              setSort(next);
              setPage(1);
              publish(filters, 1, next, customerId);
            }}
            fullWidth
          >
            {SORTS.map((id) => (
              <MenuItem key={id} value={id}>{t(`history.sort.${id}`)}</MenuItem>
            ))}
          </TextField>
          )}
          footer={hidePaymentChips ? null : (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          {hidePaymentChips ? null : (['UNPAID', 'PARTIAL', 'PAID'] as const).map((bucket) => {
            const stat = stats.data?.[bucket === 'PAID' ? 'paid' : bucket === 'PARTIAL' ? 'partial' : 'unpaid'];
            const amount = formatMoney(stat?.amount);
            const label = bucket === 'PAID'
              ? t('history.paymentBilled', { name: t('status.PAID'), count: stat?.count ?? 0, amount })
              : t('history.paymentDue', { name: t(`status.${bucket}`), count: stat?.count ?? 0, amount });
            return (
              <Chip
                key={bucket}
                label={label}
                color={filters.paymentStatus === bucket ? 'primary' : 'default'}
                variant={filters.paymentStatus === bucket ? 'filled' : 'outlined'}
                data-bucket={bucket}
                onClick={togglePaymentBucket}
              />
            );
          })}
          {hidePaymentChips ? null : (
            <Chip
              label={t('history.overdue')}
              color={filters.overdue ? 'warning' : 'default'}
              variant={filters.overdue ? 'filled' : 'outlined'}
              data-bucket="OVERDUE"
              onClick={togglePaymentBucket}
            />
          )}
            </Stack>
          )}
          actions={(
          <Button
            variant="outlined"
            disabled={exportBusy}
            onClick={async () => {
              setExportBusy(true);
              setError(null);
              try {
                const blob = await exportSalesRegisterCsv({
                  status: filters.status || undefined,
                  q: debouncedQ ? documentSearchQuery(debouncedQ) : undefined,
                  date_from: filters.dateFrom || undefined,
                  date_to: filters.dateTo || undefined,
                  payment_status: filters.paymentStatus || undefined,
                  overdue: filters.overdue ? 1 : undefined,
                  customer: customerId || undefined,
                  sort,
                });
                triggerBlobDownload(blob, 'sales-register.csv');
              } catch (err) {
                setError(getErrorMessage(err));
              } finally {
                setExportBusy(false);
              }
            }}
          >
            {t('history.exportCsv')}
          </Button>
          )}
        />
      </>

      {showLoading ? <LoadingState /> : null}
      {showNoMatches ? (
        <Alert severity="info">{t('common.noResults')}</Alert>
      ) : null}
      {query.isError ? (
        <ErrorState
          message={getErrorMessage(query.error)}
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {query.isError && page > 1 ? (
        <Button size="small" onClick={() => { setPage(1); publish(filters, 1, sort, customerId); }}>
          {t('history.firstPage')}
        </Button>
      ) : null}
      {showEmpty ? (
        <EmptyState
          description={t('empty.invoices')}
          action={
            <HelpEmptyLink intent="cannot-complete-invoice">
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                {canContinueSetup ? (
                  <Button component={RouterLink} to="/setup?step=first_bill" variant="contained">
                    {t('setup.continueSetup')}
                  </Button>
                ) : null}
                {allowCreate ? (
                  <Button component={RouterLink} to="/sales/new" variant={canContinueSetup ? 'outlined' : 'contained'}>
                    {t('nav.newInvoice')}
                  </Button>
                ) : null}
              </Stack>
            </HelpEmptyLink>
          }
        />
      ) : null}
      {rows.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={52} chromeHeight={HEADER_CHROME}>
            {({ rows: virtualRows, totalSize, measureElement }) => (
          <Table size="small" aria-rowcount={rows.length}>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    inputProps={{ 'aria-label': t('common.selectAllRows') }}
                    checked={rows.length > 0 && rows.every((r) => selected.includes(r.id))}
                    indeterminate={rows.some((r) => selected.includes(r.id)) && rows.some((r) => !selected.includes(r.id))}
                    onChange={() => {
                      const pageIds = rows.map((r) => r.id);
                      const allOnPage = pageIds.every((id) => selected.includes(id));
                      setSelected((prev) => (
                        allOnPage
                          ? prev.filter((id) => !pageIds.includes(id))
                          : [...new Set([...prev, ...pageIds])]
                      ));
                    }}
                  />
                </TableCell>
                <TableCell aria-sort={ariaSort('date')}>{sortHeader('date', t('common.date'))}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right" aria-sort={ariaSort('total')}>{sortHeader('total', t('common.total'))}</TableCell>
                <TableCell align="right" aria-sort={ariaSort('due')}>{sortHeader('due', t('history.due'))}</TableCell>
                {narrow ? null : <TableCell>{t('history.dueDate')}</TableCell>}
                <TableCell align="right" width={56}>
                  {t('common.actions')}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {/* Companion fix to UXW2B-007: VirtualizedTable's outer spacer reserves the
                  full scrollable height, but only the current window of rows is rendered
                  in normal flow — without these leading/trailing spacer rows they'd always
                  render right after the header, so scrolling past the first screenful showed
                  blank space instead of the (correctly computed) later rows.
                  F3-042: spacer heights derive from the virtualizer's real
                  measured totalSize, not `rows.length * rowHeight`. */}
              {virtualRows.length > 0 && virtualRows[0].start > 0 ? (
                <TableRow
                  style={{ height: virtualRows[0].start, padding: 0, border: 0 }}
                  aria-hidden
                  role="presentation"
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={columnCount} />
                </TableRow>
              ) : null}
              {virtualRows.map((vRow) => {
                const inv = rows[vRow.index];
                if (!inv) return null;
                return (
                <TableRow
                  key={inv.id}
                  hover
                  data-index={vRow.index}
                  ref={measureElement}
                  style={{ height: vRow.size }}
                >
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      inputProps={{ 'aria-label': t('common.selectRow', { name: invoiceNumberLabel(inv) }) }}
                      checked={selected.includes(inv.id)}
                      onChange={() =>
                        setSelected((prev) =>
                          prev.includes(inv.id) ? prev.filter((id) => id !== inv.id) : [...prev, inv.id],
                        )
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <time dateTime={(inv.invoiceDate || '').slice(0, 10)}>{formatDocumentDate(inv.invoiceDate)}</time>
                  </TableCell>
                  <TableCell>
                    <Typography
                      component={RouterLink}
                      to={`/sales/history/${inv.id}`}
                      fontWeight={600}
                      title={invoiceNumberLabel(inv)}
                      sx={{ color: 'primary.main', textDecoration: 'none' }}
                    >
                      {inv.number ? shortDocumentNumber(inv.number, inv.invoiceDate) : invoiceNumberLabel(inv)}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {inv.customer ? (
                      <Typography component={RouterLink} to={`/sales/customers/${inv.customer}`} sx={{ color: 'inherit', textDecoration: 'none' }}>
                        {inv.customerName ?? '—'}
                      </Typography>
                    ) : (inv.customerName ?? '—')}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      <StatusChip
                        tone={documentStatusTone(invoiceDisplayStatus(inv))}
                        labelKey={statusLabelKey(invoiceDisplayStatus(inv))}
                      />
                      {inv.returnState === 'PARTIAL' ? (
                        <StatusChip tone="warning" labelKey="status.PARTIALLY_RETURNED" />
                      ) : null}
                      {inv.cancelApprovalPending ? <Chip size="small" label={t('history.cancelPendingChip')} /> : null}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">{formatMoney(inv.grandTotal)}</TableCell>
                  <TableCell align="right">
                    {inv.status === 'COMPLETED' || inv.status === 'RETURNED' ? formatMoney(inv.balance) : '—'}
                  </TableCell>
                  {narrow ? null : (
                    <TableCell>
                      {inv.dueDate ? (
                        <Typography
                          component="span"
                          variant="body2"
                          color={
                            inv.status === 'COMPLETED' && toNumber(inv.balance) > 0 && isOverdueDueDate(inv.dueDate, today)
                              ? 'warning.main'
                              : 'text.primary'
                          }
                        >
                          <time dateTime={inv.dueDate.slice(0, 10)}>{formatDocumentDate(inv.dueDate)}</time>
                          {inv.status === 'COMPLETED' && toNumber(inv.balance) > 0 && isOverdueDueDate(inv.dueDate, today)
                            ? ` · ${t('history.overdue')}`
                            : ''}
                        </Typography>
                      ) : '—'}
                    </TableCell>
                  )}
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      aria-label={t('common.actions')}
                      sx={{ minWidth: 40, minHeight: 40 }}
                      disabled={busy}
                      onClick={(e) => {
                        menuButtonRef.current = e.currentTarget;
                        setActive(inv);
                        setMenuAnchor(e.currentTarget);
                      }}
                    >
                      <MoreVertIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
                );
              })}
              {virtualRows.length > 0 &&
              Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end) > 0 ? (
                <TableRow
                  style={{
                    height: Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end),
                    padding: 0,
                    border: 0,
                  }}
                  aria-hidden
                  role="presentation"
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={columnCount} />
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
            )}
          </VirtualizedTable>
        </Paper>
      ) : null}
      {query.data && count > 0 ? (
        <Stack direction="row" spacing={1} justifyContent="space-between" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('history.range', { start: rangeStart, end: rangeEnd, count })}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => {
            const next = page - 1;
            setPage(next);
            publish(filters, next, sort, customerId);
          }}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => {
              const next = page + 1;
              setPage(next);
              publish(filters, next, sort, customerId);
            }}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor) && Boolean(active)}
        onClose={() => closeMenu()}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem
          onClick={() => {
            if (active) navigate(`/sales/history/${active.id}`);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <OpenInNewIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.open')}</ListItemText>
        </MenuItem>

        {allowCreate && (active?.status === 'DRAFT' || active?.status === 'COMPLETED') ? (
          <MenuItem
            onClick={() => {
              if (active) navigate(`/sales/history/${active.id}/edit`);
              closeMenu();
            }}
          >
            <ListItemIcon>
              <EditOutlinedIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>{active?.status === 'COMPLETED' ? t('history.amend') : t('common.edit')}</ListItemText>
          </MenuItem>
        ) : null}

        {allowCreate && active?.status === 'DRAFT' ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              completeKey.current = newIdempotencyKey();
              setCompleteTarget(active);
              closeMenu(false);
            }}
          >
            <ListItemIcon>
              <CheckCircleOutlineIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>{t('common.complete')}</ListItemText>
          </MenuItem>
        ) : null}

        {active?.status === 'COMPLETED' || active?.status === 'RETURNED' ? (
          <>
            <MenuItem onClick={() => void runPdf('print')}>
              <ListItemIcon>
                <PrintOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('common.print')}</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => void runPdf('download')}>
              <ListItemIcon>
                <PictureAsPdfOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('common.download')}</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => void runThermalPrint(80)}>
              <ListItemIcon>
                <PrintOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('sweep2.printReceipt80')}</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => void runThermalPrint(58)}>
              <ListItemIcon>
                <PrintOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('sweep2.printReceipt58')}</ListItemText>
            </MenuItem>
            {canViewFinancialReports(user) ? (
              <MenuItem
                onClick={() => {
                  if (active) setProfitTarget(active);
                  closeMenu();
                }}
              >
                <ListItemText>{t('invoiceDetail.profitDetails')}</ListItemText>
              </MenuItem>
            ) : null}
            {allowCreate ? <MenuItem
              onClick={() => {
                if (active) setShareTarget(active);
                closeMenu(false);
              }}
            >
              <ListItemIcon>
                <ShareOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('common.share')}</ListItemText>
            </MenuItem> : null}
            {allowPay && toNumber(active?.balance) > 0 ? (
              <MenuItem
                onClick={() => {
                  if (active) setPayTarget(active);
                  closeMenu();
                }}
              >
                <ListItemText>{t('history.recordPayment')}</ListItemText>
              </MenuItem>
            ) : null}
            {allowCreate && active?.status === 'COMPLETED' ? (
              <MenuItem
                onClick={() => {
                  if (active) navigate(`/sales/returns?create=1&invoice=${active.id}`);
                  closeMenu();
                }}
              >
                <ListItemText>{t('history.salesReturn')}</ListItemText>
              </MenuItem>
            ) : null}
          </>
        ) : null}

        {active?.status === 'COMPLETED' && allowCancel && !active.cancelApprovalPending ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              setCancelReason('');
              setCancelTarget(active);
              closeMenu(false);
            }}
          >
            <ListItemIcon>
              <CancelOutlinedIcon fontSize="small" color="error" />
            </ListItemIcon>
            <ListItemText>{t('common.cancel')}</ListItemText>
          </MenuItem>
        ) : null}

        {allowCreate && active?.status === 'DRAFT' ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              const id = active.id;
              const label = invoiceNumberLabel(active);
              closeMenu();
              if (window.confirm(t('history.confirmDeleteDraft', { label }))) {
                deleteMutation.mutate(id);
              }
            }}
          >
            <ListItemIcon>
              <DeleteOutlineIcon fontSize="small" color="error" />
            </ListItemIcon>
            <ListItemText>{t('common.delete')}</ListItemText>
          </MenuItem>
        ) : null}
      </Menu>
      <ConfirmDialog
        open={Boolean(completeTarget)}
        title={t('history.confirmCompleteTitle', { label: completeTarget ? invoiceNumberLabel(completeTarget) : '' })}
        body={t('history.confirmCompleteBody')}
        confirmLabel={t('history.confirmCompleteAction')}
        confirming={completeMutation.isPending}
        onClose={() => setCompleteTarget(null)}
        onConfirm={() => { if (completeTarget) completeMutation.mutate(completeTarget.id); }}
      />
      <Dialog
        open={Boolean(cancelTarget)}
        onClose={() => {
          if (cancelMutation.isPending) return;
          setCancelTarget(null);
          setCancelReason('');
          menuButtonRef.current?.focus();
        }}
        aria-labelledby="cancel-invoice-title"
        aria-describedby="cancel-invoice-body"
      >
        <DialogTitle id="cancel-invoice-title">
          {t('history.confirmCancelTitle', { label: cancelTarget ? invoiceNumberLabel(cancelTarget) : '' })}
        </DialogTitle>
        <DialogContent>
          <Typography id="cancel-invoice-body" variant="body2" sx={{ mb: 2 }}>
            {t('history.confirmCancelBody')}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            required
            label={t('history.cancelReason')}
            value={cancelReason}
            onChange={(event) => setCancelReason(event.target.value.slice(0, 500))}
            inputProps={{ maxLength: 500 }}
          />
        </DialogContent>
        <DialogActions>
          <Button disabled={cancelMutation.isPending} onClick={() => {
            setCancelTarget(null);
            setCancelReason('');
            menuButtonRef.current?.focus();
          }}>{t('common.close')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={!cancelReason.trim() || cancelMutation.isPending}
            onClick={() => { if (cancelTarget) cancelMutation.mutate(cancelTarget); }}
          >
            {t('history.confirmCancelInvoice')}
          </Button>
        </DialogActions>
      </Dialog>
      <ProfitDetailsDialog
        open={Boolean(profitTarget)}
        invoiceId={profitTarget?.id ?? null}
        onClose={() => setProfitTarget(null)}
      />
      <ShareInvoiceDialog
        open={Boolean(shareTarget)}
        invoiceId={shareTarget?.id ?? null}
        defaultPhone={shareTarget?.whatsappOffer?.phone || ''}
        defaultEmail=""
        onClose={() => setShareTarget(null)}
        onSuccess={(msg) => {
          setMessageTone('success');
          setMessage(msg);
          setError(null);
        }}
        onError={(msg) => setError(msg)}
      />
      <RecordInvoicePaymentDialog
        open={Boolean(payTarget)}
        invoice={payTarget}
        onClose={() => setPayTarget(null)}
        onSuccess={() => {
          const target = payTarget;
          setPayTarget(null);
          setMessageTone('success');
          setMessage(target ? t('history.paymentRecorded', { label: invoiceNumberLabel(target) }) : null);
          invalidate(target?.id);
        }}
      />
    </Stack>
  );
}
