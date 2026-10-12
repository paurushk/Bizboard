import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Menu from '@mui/material/Menu';
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
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  deleteCustomer,
  exportCustomersCsv,
  getCustomersHealth,
  getCustomersSummary,
  listCollectionRisk,
  listCustomersPage,
  setPosWalkInCustomer,
  updateCustomer,
  verifyCustomerGstin,
  verifyCustomersGstinBulk,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreditHoldChip } from '@/components/CreditHoldChip';
import {
  HistoryFilterBar,
  EMPTY_HISTORY_FILTERS,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { PageTitle } from '@/contextHelp';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { HelpEmptyLink } from '@/pages/help/HelpEmptyLink';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import type { Customer } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';
import { isCollectionHoldStatus } from '@/utils/collectionHold';
import { gstinStatusColor, gstinStatusLabelKey } from '@/utils/gstinStatus';
import { formatMoney } from '@/utils/money';
import { canCreateSales, canExport, canViewFinancialReports, isOwner } from '@/utils/permissions';
import { customerStatusTone, statusLabelKey } from '@/utils/status';
import { CustomerFormDialog } from './CustomerFormDialog';
import { invalidateCustomerQueries } from './customerQueries';

const PAGE_SIZE = 50;
const BULK_VERIFY_MAX = 10;
// Text for screen readers only (the actions column has no visible heading).
const visuallyHidden = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;
const HIDE_ON_PHONE = { display: { xs: 'none', md: 'table-cell' } } as const;

type Confirm = { kind: 'block' | 'archive' | 'walkIn'; customer: Customer } | null;

function num(value: string | number | undefined | null): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export function CustomersPage() {
  const { user } = useAuth();
  useFeatureFlagEpoch();
  const show360 = isRuntimeFlagEnabled('ENABLE_CUSTOMER_360');
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const debouncedQ = useDebouncedValue(filters.q, 300);
  const [sort, setSort] = useState('name');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; customer: Customer } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);

  const canMutate = canCreateSales(user) && !writesBlocked;
  const canLedger = canViewFinancialReports(user);
  const canExportList = canLedger && canExport(user);
  const userIsOwner = !!user && isOwner(user.role);
  // Archiving, and lifting a block or an archive, are owner/manager decisions; blocking is open to sales.
  const canArchive = canMutate && !!user && ['OWNER', 'MANAGER'].includes(user.role);
  const canLiftBlock = canArchive;

  const query = useQuery({
    queryKey: ['customers', page, filters.status, debouncedQ, sort],
    queryFn: () =>
      listCustomersPage({
        page,
        pageSize: PAGE_SIZE,
        status: filters.status || undefined,
        q: debouncedQ || undefined,
        sort,
      }),
  });
  const summary = useQuery({
    queryKey: ['customers-summary', filters.status, debouncedQ],
    queryFn: () => getCustomersSummary({ status: filters.status || undefined, q: debouncedQ || undefined }),
    enabled: canLedger,
    retry: false,
  });
  const health = useQuery({
    queryKey: ['customers-health'],
    queryFn: getCustomersHealth,
    enabled: canArchive,
    retry: false,
    staleTime: 10 * 60_000,
  });
  const collectionRisk = useQuery({
    queryKey: ['collection-risk'],
    queryFn: listCollectionRisk,
    retry: false,
  });
  const holdByCustomer = useMemo(() => {
    const map = new Map<number, boolean>();
    for (const row of collectionRisk.data ?? []) {
      if (isCollectionHoldStatus(row.status)) map.set(row.customerId, true);
    }
    return map;
  }, [collectionRisk.data]);
  const rows = query.data?.results ?? [];
  const verifiableIds = rows.filter((c) => c.gstin).map((c) => c.id);

  const fail = (err: unknown) => {
    setNotice(null);
    setError(getErrorMessage(err));
  };

  const statusMutation = useMutation({
    mutationFn: ({ customer, status }: { customer: Customer; status: 'ACTIVE' | 'BLOCKED' }) =>
      updateCustomer(customer.id, { status, version: customer.version }),
    onSuccess: (_saved, vars) => {
      setError(null);
      setConfirm(null);
      invalidateCustomerQueries(qc, vars.customer.id);
    },
    onError: (err) => {
      setConfirm(null);
      fail(err);
    },
  });

  const verifyMutation = useMutation({
    mutationFn: (id: number) => verifyCustomerGstin(id),
    onSuccess: (saved) => {
      setError(null);
      setNotice(saved.verificationNotice || null);
      invalidateCustomerQueries(qc, saved.id);
    },
    onError: fail,
  });

  const bulkVerifyMutation = useMutation({
    mutationFn: (ids: number[]) => verifyCustomersGstinBulk(ids),
    onSuccess: (data) => {
      const failed = data.results.filter((row) => row.error);
      setError(null);
      setNotice(
        failed.length
          ? t('customers.bulkVerifyPartial', {
              done: data.results.length - failed.length,
              failed: failed.length,
              reason: failed[0].error,
            })
          : t('customers.bulkVerifyDone', { count: data.results.length }),
      );
      setSelected([]);
      invalidateCustomerQueries(qc);
    },
    onError: fail,
  });

  const archiveMutation = useMutation({
    mutationFn: (customer: Customer) => deleteCustomer(customer.id),
    onSuccess: (result, customer) => {
      setError(null);
      setConfirm(null);
      setNotice(result.archived ? t('customers.archivedNotice') : t('customers.deletedNotice'));
      invalidateCustomerQueries(qc, customer.id);
    },
    onError: (err) => {
      setConfirm(null);
      fail(err);
    },
  });

  const walkInMutation = useMutation({
    mutationFn: (customer: Customer) => setPosWalkInCustomer(customer.id),
    onSuccess: (saved) => {
      setError(null);
      setConfirm(null);
      setNotice(t('customers.walkInDone', { name: saved.name }));
      invalidateCustomerQueries(qc);
    },
    onError: (err) => {
      setConfirm(null);
      fail(err);
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => exportCustomersCsv({ status: filters.status || undefined, q: debouncedQ || undefined, sort }),
    onSuccess: (blob) => {
      triggerBlobDownload(blob, 'customers.csv');
      setError(null);
      setNotice(t('customers.exportStarted'));
    },
    onError: fail,
  });

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const openEdit = (c: Customer) => {
    setEditing(c);
    setFormOpen(true);
  };

  const walkInEligible = (c: Customer) =>
    c.status === 'ACTIVE' && !c.isPosWalkIn && !(c.gstin ?? '').trim() && num(c.creditLimit) === 0;

  const confirmCopy = (() => {
    if (!confirm) return null;
    const name = confirm.customer.name;
    if (confirm.kind === 'block') {
      const due = num(confirm.customer.outstanding);
      return {
        title: t('customers.blockTitle'),
        body: due > 0
          ? t('customers.blockBodyWithBalance', { name, amount: formatMoney(due) })
          : t('customers.blockBody', { name }),
        label: t('common.block'),
        color: 'warning' as const,
        pending: statusMutation.isPending,
        run: () => statusMutation.mutate({ customer: confirm.customer, status: 'BLOCKED' }),
      };
    }
    if (confirm.kind === 'archive') {
      return {
        title: t('customers.archiveTitle'),
        body: t('customers.archiveBody', { name }),
        label: t('customers.archive'),
        color: 'error' as const,
        pending: archiveMutation.isPending,
        run: () => archiveMutation.mutate(confirm.customer),
      };
    }
    return {
      title: t('customers.walkInTitle'),
      body: t('customers.walkInBody', { name }),
      label: t('customers.setWalkIn'),
      color: 'primary' as const,
      pending: walkInMutation.isPending,
      run: () => walkInMutation.mutate(confirm.customer),
    };
  })();

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <PageTitle>{t('nav.customers')}</PageTitle>
        <Stack direction="row" spacing={1}>
          {canMutate && selected.length > 0 ? (
            <Button
              variant="outlined"
              disabled={bulkVerifyMutation.isPending || selected.length > BULK_VERIFY_MAX}
              onClick={() => bulkVerifyMutation.mutate(selected)}
            >
              {selected.length > BULK_VERIFY_MAX
                ? t('customers.bulkVerifyTooMany', { max: BULK_VERIFY_MAX })
                : t('customers.bulkVerify', { count: selected.length })}
            </Button>
          ) : null}
          {canExportList ? (
            <Button variant="outlined" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
              {t('customers.exportCsv')}
            </Button>
          ) : null}
          {canMutate ? (
            <Button variant="contained" onClick={openCreate}>
              {t('common.add')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {notice ? (
        <Alert severity="info" onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      ) : null}
      {health.data && health.data.total > 0 ? (
        <Alert severity="warning">
          {t('customers.healthBanner', {
            count: health.data.total,
            detail: health.data.checks.map((row) => `${row.count} ${t(`customers.health.${row.check}`)}`).join('; '),
          })}
        </Alert>
      ) : null}
      {summary.data ? (
        <Box
          display="grid"
          gridTemplateColumns={{ xs: '1fr 1fr', sm: 'repeat(4, 1fr)' }}
          gap={2}
          role="group"
          aria-label={t('customers.summaryLabel')}
        >
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">{t('customers.kpiActive')}</Typography>
            <Typography variant="h6" component="p">{summary.data.activeCount}</Typography>
            {summary.data.inactiveCount > 0 ? (
              <Button
                size="small"
                onClick={() => {
                  setFilters({ ...filters, status: 'INACTIVE' });
                  setPage(1);
                }}
              >
                {t('customers.showArchived', { count: summary.data.inactiveCount })}
              </Button>
            ) : null}
          </Paper>
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">{t('customers.kpiOutstanding')}</Typography>
            <Typography variant="h6" component="p">{formatMoney(summary.data.totalOutstanding)}</Typography>
          </Paper>
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">{t('customers.kpiAdvances')}</Typography>
            <Typography variant="h6" component="p" color="info.main">
              {formatMoney(summary.data.totalUnallocatedAdvance)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('customers.kpiNetExposure', { amount: formatMoney(summary.data.netCreditExposure) })}
            </Typography>
          </Paper>
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">{t('customers.kpiAttention')}</Typography>
            <Typography
              variant="h6"
              component="p"
              color={summary.data.overCreditLimitCount > 0 ? 'error.main' : undefined}
            >
              {t('customers.kpiAttentionValue', {
                over: summary.data.overCreditLimitCount,
                blocked: summary.data.blockedCount,
              })}
            </Typography>
          </Paper>
        </Box>
      ) : null}
      {!query.isError ? (
        <Stack spacing={1}>
          <HistoryFilterBar
            value={filters}
            onChange={(next) => {
              setFilters(next);
              setPage(1);
            }}
            showDateRange={false}
            statusOptions={[
              { value: 'ACTIVE', label: t('status.active') },
              { value: 'BLOCKED', label: t('status.blocked') },
              { value: 'INACTIVE', label: t('status.inactive') },
            ]}
          />
          <TextField
            select
            size="small"
            label={t('common.sortBy')}
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setPage(1);
            }}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="name">{t('common.name')}</MenuItem>
            <MenuItem value="recent">{t('ledger.recent')}</MenuItem>
            <MenuItem value="balance">{t('reports.dueBalance')}</MenuItem>
          </TextField>
        </Stack>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError && !filters.status && !debouncedQ ? (
        <EmptyState
          description={t('empty.customers')}
          action={
            <HelpEmptyLink intent="add-gstin">
              {canMutate ? (
                <Button variant="contained" onClick={openCreate}>
                  {t('common.add')} {t('nav.customers')}
                </Button>
              ) : null}
            </HelpEmptyLink>
          }
        />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError && (filters.status || debouncedQ) ? (
        <EmptyState title={t('common.noResults')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto', position: 'relative' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {canMutate ? (
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      inputProps={{ 'aria-label': t('customers.selectAllVerifiable') }}
                      checked={verifiableIds.length > 0 && verifiableIds.every((id) => selected.includes(id))}
                      indeterminate={selected.length > 0 && !verifiableIds.every((id) => selected.includes(id))}
                      disabled={verifiableIds.length === 0}
                      onChange={(e) => setSelected(e.target.checked ? verifiableIds : [])}
                    />
                  </TableCell>
                ) : null}
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.phone')}</TableCell>
                <TableCell sx={HIDE_ON_PHONE}>{t('common.email')}</TableCell>
                <TableCell>GSTIN</TableCell>
                <TableCell sx={HIDE_ON_PHONE}>{t('customers.gstinStatus')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('sweep2.outstanding')}</TableCell>
                <TableCell>
                  <Box component="span" sx={visuallyHidden}>{t('common.actions')}</Box>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((c) => {
                const limit = num(c.creditLimit);
                const exposure = num(c.creditExposure ?? c.outstanding);
                const owed = num(c.outstanding);
                return (
                  <TableRow key={c.id}>
                    {canMutate ? (
                      <TableCell padding="checkbox">
                        {c.gstin ? (
                          <Checkbox
                            size="small"
                            inputProps={{ 'aria-label': t('customers.selectToVerify', { name: c.name }) }}
                            checked={selected.includes(c.id)}
                            onChange={(e) =>
                              setSelected((prev) => (e.target.checked ? [...prev, c.id] : prev.filter((id) => id !== c.id)))
                            }
                          />
                        ) : null}
                      </TableCell>
                    ) : null}
                    <TableCell
                      sx={{
                        position: { xs: 'sticky', md: 'static' },
                        left: 0,
                        zIndex: 1,
                        bgcolor: 'background.paper',
                        minWidth: 120,
                      }}
                    >
                      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                        {show360 ? (
                          <Link component={RouterLink} to={`/sales/customers/${c.id}`} underline="hover">
                            {c.name}
                          </Link>
                        ) : (
                          <span>{c.name}</span>
                        )}
                        {c.isPosWalkIn ? <Chip size="small" color="info" label={t('customers.posWalkIn')} /> : null}
                        {holdByCustomer.get(c.id) ? <CreditHoldChip /> : null}
                      </Stack>
                      {c.gstin ? (
                        <Chip
                          size="small"
                          sx={{ mt: 0.5, display: { xs: 'inline-flex', md: 'none' } }}
                          label={t(gstinStatusLabelKey(c.gstinVerificationStatus))}
                          color={gstinStatusColor(c.gstinVerificationStatus)}
                        />
                      ) : null}
                    </TableCell>
                    <TableCell>{c.phone || '—'}</TableCell>
                    <TableCell sx={HIDE_ON_PHONE}>{c.email || '—'}</TableCell>
                    <TableCell>
                      {c.gstin || '—'}
                      {c.gstinLegalName ? (
                        <Typography variant="caption" display="block" color="text.secondary">
                          {c.gstinLegalName}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell sx={HIDE_ON_PHONE}>
                      {c.gstin ? (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <Chip
                            size="small"
                            label={t(gstinStatusLabelKey(c.gstinVerificationStatus))}
                            color={gstinStatusColor(c.gstinVerificationStatus)}
                          />
                          {canMutate ? (
                            <Button
                              size="small"
                              disabled={verifyMutation.isPending && verifyMutation.variables === c.id}
                              onClick={() => verifyMutation.mutate(c.id)}
                            >
                              {t('sweep2.verify')}
                            </Button>
                          ) : null}
                        </Stack>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusChip tone={customerStatusTone(c.status)} labelKey={statusLabelKey(c.status)} />
                    </TableCell>
                    <TableCell align="right">
                      {formatMoney(c.outstanding ?? 0)}
                      {limit > 0 ? (
                        <Typography
                          variant="caption"
                          display="block"
                          color={exposure > limit ? 'error.main' : 'text.secondary'}
                        >
                          {t('customers.limitCaption', { amount: formatMoney(limit) })}
                        </Typography>
                      ) : null}
                      {c.creditExposure != null && exposure < owed ? (
                        <Typography variant="caption" display="block" color="info.main">
                          {t('customers.netExposureCaption', { amount: formatMoney(exposure) })}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end" sx={{ whiteSpace: 'nowrap' }}>
                        {canLedger ? (
                          <Button
                            size="small"
                            component={RouterLink}
                            to={`/reports/customer-ledger?customer=${c.id}`}
                          >
                            {t('billing.viewLedger')}
                          </Button>
                        ) : null}
                        {canMutate ? (
                          <>
                            <Button size="small" onClick={() => openEdit(c)}>
                              {t('common.edit')}
                            </Button>
                            {!c.isPosWalkIn ? (
                              c.status === 'ACTIVE' ? (
                                <Button
                                  size="small"
                                  disabled={statusMutation.isPending}
                                  onClick={() => setConfirm({ kind: 'block', customer: c })}
                                >
                                  {t('common.block')}
                                </Button>
                              ) : canLiftBlock ? (
                                <Button
                                  size="small"
                                  disabled={statusMutation.isPending}
                                  onClick={() => statusMutation.mutate({ customer: c, status: 'ACTIVE' })}
                                >
                                  {c.status === 'INACTIVE' ? t('customers.activate') : t('common.unblock')}
                                </Button>
                              ) : null
                            ) : null}
                            {(Boolean(c.gstin) && canMutate) || (!c.isPosWalkIn && canArchive) || userIsOwner ? (
                              <Button
                                size="small"
                                aria-label={t('customers.moreActions', { name: c.name })}
                                aria-haspopup="menu"
                                onClick={(e) => setMenu({ anchor: e.currentTarget, customer: c })}
                              >
                                {t('customers.more')}
                              </Button>
                            ) : null}
                          </>
                        ) : null}
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
            {query.data.count ? ` / ${Math.max(1, Math.ceil(query.data.count / PAGE_SIZE))}` : ''}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button variant="outlined" size="small" disabled={!query.data.next} onClick={() => setPage((p) => p + 1)}>
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Menu anchorEl={menu?.anchor ?? null} open={Boolean(menu)} onClose={() => setMenu(null)}>
        {menu?.customer.gstin && canMutate ? (
          <MenuItem
            // On a wide screen the GSTIN column already has Verify; this is the way to it on a phone.
            sx={{ display: { md: 'none' } }}
            disabled={verifyMutation.isPending}
            onClick={() => {
              verifyMutation.mutate(menu.customer.id);
              setMenu(null);
            }}
          >
            {t('customers.verifyGstin')}
          </MenuItem>
        ) : null}
        {menu && !menu.customer.isPosWalkIn && canArchive ? (
          <MenuItem
            onClick={() => {
              setConfirm({ kind: 'archive', customer: menu.customer });
              setMenu(null);
            }}
          >
            {t('customers.archive')}
          </MenuItem>
        ) : null}
        {menu && userIsOwner ? (
          <MenuItem
            disabled={!walkInEligible(menu.customer)}
            onClick={() => {
              setConfirm({ kind: 'walkIn', customer: menu.customer });
              setMenu(null);
            }}
          >
            {t('customers.setWalkIn')}
          </MenuItem>
        ) : null}
      </Menu>

      <ConfirmDialog
        open={Boolean(confirmCopy)}
        title={confirmCopy?.title ?? ''}
        body={confirmCopy?.body ?? ''}
        confirmLabel={confirmCopy?.label}
        confirmColor={confirmCopy?.color}
        confirming={confirmCopy?.pending}
        onConfirm={() => confirmCopy?.run()}
        onClose={() => setConfirm(null)}
      />

      <CustomerFormDialog
        open={formOpen}
        customer={editing}
        onClose={() => setFormOpen(false)}
        onSaved={(saved) => {
          setError(null);
          invalidateCustomerQueries(qc, saved.id);
        }}
      />
    </Stack>
  );
}
