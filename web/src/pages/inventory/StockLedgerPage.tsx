import { useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
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
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { exportStockLedger, getProduct, listStockLedger, listWarehouses } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t, useLocale } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { describeReference, MOVEMENT_TYPES, typeLabel } from '@/pages/inventory/ledgerHelpers';
import type { Product } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canExport } from '@/utils/permissions';

export function StockLedgerPage() {
  useLocale();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [product, setProduct] = useState<Product | null>(null);
  // A link from Current stock or Products carries the item and godown in the address.
  const [seeded, setSeeded] = useState(false);
  const linkedProduct = params.get('product');
  const [warehouse, setWarehouse] = useState(params.get('warehouse') ?? '');
  const [movementType, setMovementType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebouncedValue(search, 300);
  const productSearch = useProductSearch({ selected: product });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });

  if (!seeded && linkedProduct) {
    setSeeded(true);
    void getProduct(linkedProduct).then((p) => setProduct(p));
  }

  const filters = {
    product: product?.id,
    warehouse: warehouse ? Number(warehouse) : undefined,
    movementType: movementType || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
  };
  const query = useQuery({
    queryKey: ['stock-ledger', filters, page],
    queryFn: () => listStockLedger(filters, page),
    placeholderData: (previous) => previous,
  });
  const exportCsv = useMutation({
    mutationFn: () => exportStockLedger(filters),
    onSuccess: ({ url }) => {
      const a = document.createElement('a');
      a.href = url;
      a.download = 'stock-ledger.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    },
  });

  const rows = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  const pageSize = 50;
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const showCost = rows.some((row) => row.unitCost != null);
  const showBalance = Boolean(product);
  const change = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setPage(1);
  };

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
        <div>
          <PageTitle>{t('inventory.ledgerTitle')}</PageTitle>
          <Typography variant="body2" color="text.secondary">{t('inventory.ledgerSubtitle')}</Typography>
        </div>
        {canExport(user) ? (
          <Button variant="outlined" size="small" disabled={exportCsv.isPending} onClick={() => exportCsv.mutate()}>
            {t('inventory.ledgerExport')}
          </Button>
        ) : null}
      </Stack>
      {exportCsv.isError ? <HelpErrorAlert error={exportCsv.error} /> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} flexWrap="wrap" useFlexGap>
        <Autocomplete<Product>
          sx={{ minWidth: 260, flex: 1 }}
          options={productSearch.options}
          loading={productSearch.isFetching}
          filterOptions={(opts) => opts}
          inputValue={productSearch.productQuery}
          onInputChange={(_, v, reason) => {
            if (reason === 'input' || reason === 'clear' || reason === 'reset') productSearch.setProductQuery(v);
          }}
          getOptionLabel={(o) => `${o.name} · ${o.sku}`}
          value={product}
          onChange={(_, v) => change(setProduct)(v)}
          renderInput={(p) => <TextField {...p} size="small" label={t('inventory.ledgerItem')} helperText={product ? undefined : t('inventory.ledgerBalanceHint')} />}
        />
        <TextField
          select
          size="small"
          label={t('inventory.ledgerGodown')}
          value={warehouse}
          onChange={(e) => change(setWarehouse)(e.target.value)}
          sx={{ minWidth: 170 }}
        >
          <MenuItem value="">{t('inventory.ledgerAllGodowns')}</MenuItem>
          {(warehouses.data ?? []).map((w) => (
            <MenuItem key={w.id} value={String(w.id)}>{w.name}</MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label={t('inventory.ledgerType')}
          value={movementType}
          onChange={(e) => change(setMovementType)(e.target.value)}
          sx={{ minWidth: 190 }}
        >
          <MenuItem value="">{t('inventory.ledgerAllTypes')}</MenuItem>
          {MOVEMENT_TYPES.map((type) => (
            <MenuItem key={type} value={type}>{typeLabel(type)}</MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="date"
          label={t('inventory.ledgerFrom')}
          value={dateFrom}
          onChange={(e) => change(setDateFrom)(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          size="small"
          type="date"
          label={t('inventory.ledgerTo')}
          value={dateTo}
          onChange={(e) => change(setDateTo)(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          size="small"
          label={t('inventory.ledgerSearch')}
          value={search}
          onChange={(e) => change(setSearch)(e.target.value)}
        />
      </Stack>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && !query.isError && rows.length === 0 ? <EmptyState description={t('inventory.ledgerEmpty')} /> : null}
      {rows.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('inventory.ledgerDate')}</TableCell>
                <TableCell>{t('inventory.ledgerItem')}</TableCell>
                <TableCell>{t('inventory.ledgerGodown')}</TableCell>
                <TableCell>{t('inventory.ledgerType')}</TableCell>
                <TableCell align="right">{t('inventory.ledgerQty')}</TableCell>
                {showBalance ? <TableCell align="right">{t('inventory.ledgerBalance')}</TableCell> : null}
                {showCost ? <TableCell align="right">{t('inventory.ledgerCost')}</TableCell> : null}
                <TableCell>{t('inventory.ledgerReason')}</TableCell>
                <TableCell>{t('inventory.ledgerReference')}</TableCell>
                <TableCell>{t('inventory.ledgerBy')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => {
                const qty = toNumber(row.quantity);
                const reference = describeReference(row.referenceType, row.referenceId);
                return (
                  <TableRow key={row.id} hover>
                    <TableCell>{row.movementDate}</TableCell>
                    <TableCell>
                      {row.productName}
                      {row.batchNo ? ` · ${row.batchNo}` : ''}
                    </TableCell>
                    <TableCell>{row.warehouseName ?? '—'}</TableCell>
                    <TableCell>{row.movementTypeLabel}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, color: qty < 0 ? 'error.main' : 'success.main' }}>
                      {qty > 0 ? `+${qty}` : qty}
                    </TableCell>
                    {showBalance ? <TableCell align="right">{row.runningBalance == null ? '—' : toNumber(row.runningBalance)}</TableCell> : null}
                    {showCost ? <TableCell align="right">{row.unitCost == null ? '—' : formatMoney(row.unitCost)}</TableCell> : null}
                    <TableCell>{row.reason || '—'}</TableCell>
                    <TableCell>
                      {reference.href ? (
                        <Link component={RouterLink} to={reference.href} aria-label={t('inventory.ledgerOpenDocument', { name: reference.label })}>
                          {reference.label}
                        </Link>
                      ) : (
                        reference.label || '—'
                      )}
                    </TableCell>
                    <TableCell>{row.createdByName || '—'}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {total > pageSize ? (
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
          <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            {t('common.previous')}
          </Button>
          <Typography variant="body2">
            {t('common.page')} {page} / {lastPage}
          </Typography>
          <Button size="small" disabled={page >= lastPage} onClick={() => setPage((p) => Math.min(lastPage, p + 1))}>
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}
    </Stack>
  );
}
