import { useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
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
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getPurchasePlan, type PlanningLine } from '@/api/osPlan';
import { listSuppliersPage, listWarehouses } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { canCreatePurchases } from '@/utils/permissions';

function rowKey(row: PlanningLine) {
  return `${row.productId}-${row.warehouseId}`;
}

export function PurchasePlanningPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canDraft = canCreatePurchases(user);
  const [warehouse, setWarehouse] = useState('');
  const [supplier, setSupplier] = useState('');
  const [urgency, setUrgency] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Array<{ label: string; href: string }>>([]);
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const suppliers = useQuery({
    queryKey: ['suppliers', 'planning'],
    queryFn: () => listSuppliersPage({ page: 1, pageSize: 200 }),
  });
  const plan = useQuery({
    queryKey: ['purchase-plan', warehouse, supplier, urgency],
    queryFn: () => getPurchasePlan({
      warehouse: warehouse || undefined,
      supplier: supplier || undefined,
      urgency: urgency || undefined,
    }),
  });
  const rows = plan.data?.rows ?? [];
  const selectedRows = useMemo(
    () => rows.filter((row) => selected.includes(rowKey(row))),
    [rows, selected],
  );

  const openDrafts = () => {
    const purchases = new Map<string, PlanningLine[]>();
    const transfers = new Map<string, PlanningLine[]>();
    for (const row of selectedRows) {
      if (row.transferFromWarehouseId) {
        const key = `${row.transferFromWarehouseId}:${row.warehouseId}`;
        transfers.set(key, [...(transfers.get(key) ?? []), row]);
      } else {
        const key = String(row.supplierId ?? 'none');
        purchases.set(key, [...(purchases.get(key) ?? []), row]);
      }
    }
    const next: Array<{ label: string; href: string }> = [];
    for (const [supplierKey, lines] of purchases) {
      const encoded = encodeURIComponent(JSON.stringify(lines.map((line) => ({
        productId: line.productId,
        qty: line.suggestedQty,
      }))));
      const supplierQuery = supplierKey === 'none' ? '' : `supplier=${supplierKey}&`;
      next.push({
        label: `${t('osPlan.purchaseFromSupplier')} · ${lines.length}`,
        href: `/purchases/orders/new?${supplierQuery}lines=${encoded}`,
      });
    }
    for (const [key, lines] of transfers) {
      const [from, to] = key.split(':');
      const encoded = encodeURIComponent(JSON.stringify(lines.map((line) => ({
        productId: line.productId,
        qty: line.suggestedQty,
        warehouseId: line.warehouseId,
      }))));
      next.push({
        label: `${t('osPlan.transferFrom', { name: lines[0]?.transferFromWarehouseName || from })} · ${lines.length}`,
        href: `/inventory/transfers?from=${from}&to=${to}&lines=${encoded}`,
      });
    }
    if (next.length === 1) {
      navigate(next[0].href);
      return;
    }
    setDrafts(next);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.purchasePlanning')}</PageTitle>
        {canDraft ? (
          <Button variant="contained" disabled={selectedRows.length === 0} onClick={openDrafts}>
            {t('osPlan.openDraft')}
          </Button>
        ) : null}
      </Stack>
      <Typography variant="body2" color="text.secondary">{t('osPlan.planningHelp')}</Typography>
      {drafts.length > 1 ? (
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {drafts.map((draft) => (
            <Button key={draft.href} variant="outlined" onClick={() => navigate(draft.href)}>{draft.label}</Button>
          ))}
        </Stack>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField select label={t('nav.warehouses')} value={warehouse} onChange={(e) => setWarehouse(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(warehouses.data ?? []).map((row) => (
            <MenuItem key={row.id} value={String(row.id)}>{row.name}</MenuItem>
          ))}
        </TextField>
        <TextField select label={t('nav.suppliers')} value={supplier} onChange={(e) => setSupplier(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(suppliers.data?.results ?? []).map((row) => (
            <MenuItem key={row.id} value={String(row.id)}>{row.name}</MenuItem>
          ))}
        </TextField>
        <TextField
          label={t('osPlan.urgencyDays')}
          value={urgency}
          onChange={(e) => setUrgency(e.target.value.replace(/[^\d]/g, ''))}
          sx={{ maxWidth: 160 }}
        />
      </Stack>
      {plan.isLoading ? <LoadingState /> : null}
      {plan.isError ? (
        <ErrorState message={getErrorMessage(plan.error)} error={plan.error} onRetry={() => void plan.refetch()} />
      ) : null}
      {!plan.isLoading && !plan.isError && rows.length === 0 ? (
        <EmptyState description={t('osPlan.planningEmpty')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>{t('supplierPrices.product')}</TableCell>
                <TableCell>{t('nav.warehouses')}</TableCell>
                <TableCell align="right">{t('supplierPrices.qty')}</TableCell>
                <TableCell align="right">{t('osPlan.daysToStockout')}</TableCell>
                <TableCell>{t('osPlan.supply')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => {
                const key = rowKey(row);
                return (
                  <TableRow key={key} hover>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selected.includes(key)}
                        onChange={() => setSelected((prev) => (
                          prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
                        ))}
                      />
                    </TableCell>
                    <TableCell>{row.productName}</TableCell>
                    <TableCell>{row.warehouseName}</TableCell>
                    <TableCell align="right">{row.suggestedQty}</TableCell>
                    <TableCell align="right">{row.daysToStockout ?? '—'}</TableCell>
                    <TableCell>
                      {row.transferFromWarehouseName
                        ? t('osPlan.transferFrom', { name: row.transferFromWarehouseName })
                        : t('osPlan.purchaseFromSupplier')}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
