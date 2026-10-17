import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { completeDeliveryChallanReturn, listDeliveryChallanReturnsPage } from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { t } from '@/i18n';
import { ageInDays } from './ageInDays';

type ReturnRow = {
  id: number;
  number?: string | null;
  customerName?: string;
  challanNumber?: string | null;
  reason?: string;
  createdAt?: string;
  items?: Array<{ productName?: string; quantity?: string | number }>;
};

/**
 * Goods the godown is waiting to check in: the draft returns a failed or refused delivery opened. Checking
 * one in puts the goods back on the shelf and reopens the order for the dispatcher (DEC-O3). The older
 * a return is, the more it stands out, so it is not forgotten at the back of the godown.
 */
export function GoodsToCheckIn({ canWrite }: { canWrite: boolean }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ['goods-to-check-in'],
    queryFn: async () =>
      (await listDeliveryChallanReturnsPage({ status: 'DRAFT', from_route: true, pageSize: 50 })).results as ReturnRow[],
  });
  const checkIn = useMutation({
    mutationFn: (id: number) => completeDeliveryChallanReturn(id),
    onSuccess: () => {
      setConfirmId(null);
      setError(null);
      for (const key of ['goods-to-check-in', 'delivery-challans', 'delivery-routes', 'delivery-route', 'sales-orders', 'stock-balance', 'products', 'stock']) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
    onError: (err) => {
      setConfirmId(null);
      setError(getErrorMessage(err));
    },
  });

  const rows = query.data ?? [];
  if (query.isLoading || rows.length === 0) return error ? <Alert severity="error">{error}</Alert> : null;

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="goods-to-check-in">
      <Stack spacing={1}>
        <Typography variant="subtitle1">{t('routes.goodsBack.title', { n: rows.length })}</Typography>
        <Typography variant="body2" color="text.secondary">{t('routes.goodsBack.help')}</Typography>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {rows.map((row) => {
          const age = ageInDays(row.createdAt);
          return (
            <Stack
              key={row.id}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              alignItems={{ sm: 'center' }}
              justifyContent="space-between"
              sx={{ borderTop: 1, borderColor: 'divider', pt: 1 }}
            >
              <Stack spacing={0.25}>
                <Typography variant="body2" fontWeight={600}>
                  {row.customerName ?? '—'} · {row.challanNumber ?? ''}
                </Typography>
                <Typography variant="body2" color="text.secondary">{row.reason}</Typography>
                <Typography variant="body2">
                  {(row.items ?? []).map((i) => `${i.productName ?? ''} × ${Number(i.quantity)}`).join(', ')}
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip
                  size="small"
                  color={age >= 1 ? 'warning' : 'default'}
                  label={age === 0 ? t('routes.goodsBack.today') : t('routes.goodsBack.days', { n: age })}
                />
                {canWrite ? (
                  <Button variant="contained" size="small" sx={{ minHeight: 44 }} disabled={checkIn.isPending} onClick={() => setConfirmId(row.id)}>
                    {t('routes.goodsBack.checkIn')}
                  </Button>
                ) : null}
              </Stack>
            </Stack>
          );
        })}
      </Stack>
      <ConfirmDialog
        open={confirmId !== null}
        title={t('routes.goodsBack.confirmTitle')}
        body={t('routes.goodsBack.confirmBody')}
        confirmLabel={t('routes.goodsBack.checkIn')}
        confirming={checkIn.isPending}
        onClose={() => setConfirmId(null)}
        onConfirm={() => confirmId && checkIn.mutate(confirmId)}
      />
    </Paper>
  );
}
