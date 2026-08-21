import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { getErrorMessage } from '@/api/client';
import { listStock, listWarehouses } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import type { StockBalance } from '@/types/domain';
import { toNumber } from '@/utils/money';

type StockRow = StockBalance & {
  warehouseLabel: string;
  onHandNum: number;
  reservedNum: number;
  availableNum: number;
};

export function CurrentStockPage() {
  const query = useQuery({ queryKey: ['stock'], queryFn: listStock });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const [warehouse, setWarehouse] = useState('');

  const warehouseName = useMemo(() => {
    const map = new Map<number | string, string>();
    for (const w of warehouses.data ?? []) {
      map.set(w.id, w.name);
      map.set(String(w.id), w.name);
    }
    return map;
  }, [warehouses.data]);

  const rows = useMemo(() => {
    const src = (query.data ?? []).filter((s) => !warehouse || String(s.warehouse) === warehouse);
    // UXW2-007: when viewing all warehouses, aggregate by product so the same SKU
    // does not appear as duplicate unlabeled rows.
    if (!warehouse) {
      const map = new Map<number | string, StockRow>();
      for (const s of src) {
        const key = s.product;
        const onHand = toNumber(s.onHand);
        const reserved = toNumber(s.reserved);
        const available = toNumber(s.available);
        const existing = map.get(key);
        if (!existing) {
          map.set(key, {
            ...s,
            warehouseLabel: 'All warehouses',
            onHandNum: onHand,
            reservedNum: reserved,
            availableNum: available,
          });
        } else {
          existing.onHandNum += onHand;
          existing.reservedNum += reserved;
          existing.availableNum += available;
        }
      }
      return [...map.values()];
    }
    return src.map((s) => ({
      ...s,
      warehouseLabel: warehouseName.get(s.warehouse as never) ?? String(s.warehouse ?? '—'),
      onHandNum: toNumber(s.onHand),
      reservedNum: toNumber(s.reserved),
      availableNum: toNumber(s.available),
    }));
  }, [query.data, warehouse, warehouseName]);

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.currentStock')}</Typography>
      <TextField
        select
        size="small"
        label={t('nav.warehouses')}
        value={warehouse}
        onChange={(e) => setWarehouse(e.target.value)}
        sx={{ maxWidth: 280 }}
      >
        <MenuItem value="">
          {t('common.all')} {t('nav.warehouses')}
        </MenuItem>
        {(warehouses.data ?? []).map((item) => (
          <MenuItem key={item.id} value={item.id}>
            {item.name}
          </MenuItem>
        ))}
      </TextField>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description={t('empty.stock')} /> : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.sku')}</TableCell>
                <TableCell>{t('nav.warehouses')}</TableCell>
                <TableCell align="right">On Hand</TableCell>
                <TableCell align="right">
                  <Tooltip title={t('billing.reservedStockHint')}>
                    <span style={{ cursor: 'help' }}>Reserved ℹ️</span>
                  </Tooltip>
                </TableCell>
                <TableCell align="right">Available</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((s) => (
                <TableRow key={`${s.warehouse ?? 'all'}-${s.product}`}>
                  <TableCell
                    sx={{
                      position: { xs: 'sticky', md: 'static' },
                      left: 0,
                      zIndex: 1,
                      bgcolor: 'background.paper',
                      minWidth: 120,
                    }}
                  >
                    {s.productName}
                  </TableCell>
                  <TableCell>{s.sku}</TableCell>
                  <TableCell>{s.warehouseLabel}</TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      fontWeight: 600,
                      color: s.availableNum < 0 ? 'error.main' : undefined,
                    }}
                  >
                    {s.onHandNum}
                  </TableCell>
                  <TableCell align="right">{s.reservedNum}</TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color: s.availableNum < 0 ? 'error.main' : 'success.main',
                      fontWeight: 600,
                    }}
                  >
                    {s.availableNum}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
