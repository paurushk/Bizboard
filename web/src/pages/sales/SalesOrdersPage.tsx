import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { checkSalesOrderGate, confirmSalesOrder, type GateCheck } from '@/api/osPlan';
import {
  addOrdersToDeliveryRoute,
  cancelSalesOrder,
  convertSalesOrder,
  convertSalesOrderToChallan,
  createDeliveryRoute,
  listSalesOrdersPage,
} from '@/api/resources';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { useAuth } from '@/auth/AuthContext';
import { todayIso } from '@/components/billing';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import {
  EMPTY_HISTORY_FILTERS,
  HistoryFilterBar,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { canCancelDocuments, canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function SalesOrdersPage() {
  const { user } = useAuth();
  useFeatureFlagEpoch();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canWrite = canCreateSales(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const debouncedQ = useDebouncedValue(filters.q, 300);
  const [selected, setSelected] = useState<number[]>([]);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const [gate, setGate] = useState<(GateCheck & { id: number }) | null>(null);
  const statusParam =
    filters.status === 'OPEN' ? 'DRAFT' : filters.status === 'CLOSED' ? 'COMPLETED' : filters.status || undefined;
  const query = useQuery({
    queryKey: ['sales-orders', page, statusParam, debouncedQ, filters.dateFrom, filters.dateTo],
    queryFn: () =>
      listSalesOrdersPage({
        page,
        pageSize: PAGE_SIZE,
        status: statusParam,
        q: debouncedQ || undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      }),
  });

  const convertMutation = useMutation({
    mutationFn: (id: number) => convertSalesOrder(id),
    onSuccess: () => {
      setConvertingId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void navigate('/sales/history');
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const convertToChallanMutation = useMutation({
    mutationFn: (id: number) => convertSalesOrderToChallan(id),
    onSuccess: () => {
      setConvertingId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
      void navigate('/sales/delivery-challans');
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const confirmOrder = useMutation({
    mutationFn: (id: number) => confirmSalesOrder(id),
    onSuccess: () => {
      setGate(null);
      setConvertingId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const startConfirm = async (id: number) => {
    setConvertingId(id);
    setError(null);
    if (!isRuntimeFlagEnabled('ENABLE_ORDER_GATES')) {
      confirmOrder.mutate(id);
      return;
    }
    try {
      const result = await checkSalesOrderGate(id);
      setGate({ ...result, id });
      setConvertingId(null);
    } catch (err) {
      setConvertingId(null);
      setError(getErrorMessage(err));
    }
  };

  const cancel = useMutation({
    mutationFn: (id: number) => cancelSalesOrder(id),
    onSuccess: () => {
      setConfirmCancelId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const toRoute = useMutation({
    mutationFn: async () => {
      const route = await createDeliveryRoute({ routeDate: todayIso() });
      return addOrdersToDeliveryRoute(Number(route.id), selected);
    },
    onSuccess: (route) => {
      setSelected([]);
      void qc.invalidateQueries({ queryKey: ['delivery-routes'] });
      navigate(`/sales/delivery-routes/${route.id}`);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const converting = convertMutation.isPending || convertToChallanMutation.isPending || confirmOrder.isPending;
  const rows = query.data?.results ?? [];

  return (
    <>
      <DocumentListPage
        titleKey="nav.salesOrders"
        newPath="/sales/orders/new"
        createLabelKey="phase1.newSalesOrder"
        detailPath={(id) => `/sales/orders/${id}`}
        partyLabelKey="billing.customer"
        loading={query.isLoading}
        error={error ?? (query.isError ? getErrorMessage(query.error) : null)}
        onRetry={() => void query.refetch()}
        showCreate={canWrite}
        page={page}
        pageSize={PAGE_SIZE}
        count={query.data?.count}
        hasNext={Boolean(query.data?.next)}
        hasPrevious={Boolean(query.data?.previous) || page > 1}
        onPageChange={setPage}
        selectedIds={selected}
        onToggleSelect={(id) =>
          setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
        }
        onToggleSelectAll={() =>
          setSelected((prev) => (prev.length === rows.length ? [] : rows.map((o) => o.id)))
        }
        filters={
          <HistoryFilterBar
            value={filters}
            onChange={(next) => {
              setFilters(next);
              setPage(1);
            }}
            dateRangePresets
            statusOptions={[
              { value: 'OPEN', label: t('status.OPEN') },
              { value: 'CLOSED', label: t('status.completed') },
            ]}
          />
        }
        bulkBar={
          selected.length > 0 && canWrite ? (
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="outlined" disabled={toRoute.isPending} onClick={() => toRoute.mutate()}>
                {t('routes.addOrdersFromList')}
              </Button>
            </Stack>
          ) : null
        }
        rows={rows.map((o) => ({
          id: o.id,
          number: o.number,
          date: o.orderDate,
          partyName: o.customerName,
          status: o.status,
          grandTotal: o.grandTotal,
        }))}
        extraColumn={(row) => {
          const gatesOn = isRuntimeFlagEnabled('ENABLE_ORDER_GATES');
          const showConfirm = row.status === 'DRAFT' && canWrite;
          const showConvert = canWrite && (gatesOn ? row.status === 'CONFIRMED' : row.status === 'DRAFT');
          if (showConfirm || showConvert) {
            return (
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                {showConfirm ? (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={converting && convertingId === row.id}
                    onClick={() => void startConfirm(row.id)}
                  >
                    {t('osPlan.confirmOrder')}
                  </Button>
                ) : null}
                {showConvert ? (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={converting && convertingId === row.id}
                    onClick={() => {
                      setConvertingId(row.id);
                      convertToChallanMutation.mutate(row.id);
                    }}
                  >
                    {t('phase1.toChallan')}
                  </Button>
                ) : null}
                {showConvert ? (
                  <Button
                    size="small"
                    disabled={converting && convertingId === row.id}
                    onClick={() => {
                      setConvertingId(row.id);
                      convertMutation.mutate(row.id);
                    }}
                  >
                    {t('common.convert')}
                  </Button>
                ) : null}
              </Stack>
            );
          }
          if (row.status === 'COMPLETED' && canCancel) {
            return (
              <Button size="small" color="warning" onClick={() => setConfirmCancelId(row.id)}>
                {t('common.cancel')}
              </Button>
            );
          }
          return null;
        }}
      />
      <Dialog open={gate !== null} onClose={() => setGate(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('osPlan.confirmOrderTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1}>
            <Typography variant="body2">{t('osPlan.confirmOrderBody')}</Typography>
            {gate?.creditBlocked ? <Typography color="error">{gate.creditMessage || t('osPlan.creditBlocked')}</Typography> : null}
            {(gate?.marginWarnings ?? []).map((warning) => (
              <Typography key={warning.productId} variant="body2">
                {t('osPlan.marginWarning', { name: warning.productName, margin: warning.margin })}
              </Typography>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGate(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!gate || gate.creditBlocked || confirmOrder.isPending}
            onClick={() => gate && confirmOrder.mutate(gate.id)}
          >
            {t('osPlan.continueConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirmCancelId !== null}
        title={t('common.confirm')}
        body={t('history.confirmCancelSalesOrder')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
