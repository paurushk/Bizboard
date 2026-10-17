import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import {
  asRows,
  DataTable,
  PageShell,
} from '@/pages/phase/phaseShared';


export function PriceListsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['price-lists'], queryFn: api.listPriceLists });
  const products = useQuery({
    queryKey: ['price-list-products'],
    queryFn: () => api.listProductsPage({ page: 1, pageSize: 100 }),
  });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [slabError, setSlabError] = useState('');
  const [edit, setEdit] = useState<{
    id: number;
    name: string;
    items: { product: string; minQty: string; maxQty: string; unitPrice: string }[];
  } | null>(null);
  // F3-015: JSON-diff baseline for the slab-editor unsaved-changes guard.
  const [editBaselineJson, setEditBaselineJson] = useState('');
  const create = useMutation({
    mutationFn: () => api.createPriceList({ name }),
    onSuccess: () => {
      setOpen(false);
      setName('');
      void qc.invalidateQueries({ queryKey: ['price-lists'] });
    },
    onError: (e) => setSlabError(getErrorMessage(e)),
  });
  // F3-028: validate slab rows and block the save with a message instead of
  // silently dropping the bad ones; also flag overlapping qty ranges.
  const validateSlabs = (rows: { product: string; minQty: string; maxQty: string; unitPrice: string }[]): string => {
    const problems: string[] = [];
    const byProduct = new Map<string, { lo: number; hi: number }[]>();
    rows.forEach((row, i) => {
      const n = i + 1;
      if (!Number(row.product)) problems.push(`Row ${n}: pick a product`);
      const price = Number(row.unitPrice);
      if (row.unitPrice.trim() === '' || Number.isNaN(price) || price < 0)
        problems.push(`Row ${n}: unit price must be a number ≥ 0`);
      const lo = Number(row.minQty || 1);
      const hi = row.maxQty.trim() === '' ? Number.POSITIVE_INFINITY : Number(row.maxQty);
      if (Number.isNaN(lo) || lo < 1) problems.push(`Row ${n}: min qty must be ≥ 1`);
      if (!Number.isNaN(hi) && hi < lo) problems.push(`Row ${n}: max qty is below min qty`);
      if (Number(row.product) && !Number.isNaN(lo) && !Number.isNaN(hi)) {
        const list = byProduct.get(row.product) ?? [];
        if (list.some((r) => lo <= r.hi && hi >= r.lo)) {
          problems.push(`Row ${n}: qty range overlaps another slab for this product`);
        }
        list.push({ lo, hi });
        byProduct.set(row.product, list);
      }
    });
    return problems.join('; ');
  };
  const save = useMutation({
    mutationFn: () => {
      if (!edit) return Promise.reject(new Error('No list'));
      const msg = validateSlabs(edit.items);
      if (msg) return Promise.reject(new Error(msg));
      return api.updatePriceList(edit.id, {
        name: edit.name,
        items: edit.items.map((row) => ({
          product: Number(row.product),
          minQty: Number(row.minQty || 1),
          maxQty: row.maxQty.trim() === '' ? null : Number(row.maxQty),
          unitPrice: Number(row.unitPrice),
        })),
      });
    },
    onSuccess: () => {
      setEdit(null);
      setSlabError('');
      void qc.invalidateQueries({ queryKey: ['price-lists'] });
    },
    onError: (e) => setSlabError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const productRows = products.data?.results ?? [];
  return (
    <PageShell
      title={t('phase.priceLists')}
      subtitle={t('phase.priceListsSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          {t('sweep2.newList')}
        </Button>
      }
    >
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('integrations.priceListsLocal')}
      </Alert>
      <Alert severity="info" sx={{ mb: 2 }}>
        Quantity slabs (e.g. 1–10 @ ₹100, 11+ @ ₹92) apply at line qty. Assign a list on the customer.
        Credit notes keep the original invoice rate.
      </Alert>
      <DataTable
        rows={asRows(query.data)}
        empty="No price lists."
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'isActive', label: 'Active', bool: true },
        ]}
      />
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
        {(query.data ?? []).map((row) => (
          <Button
            key={row.id}
            size="small"
            variant="outlined"
            disabled={writesBlocked}
            onClick={() => {
              const next = {
                id: row.id,
                name: row.name ?? '',
                items: (row.items ?? []).map((item) => ({
                  product: String(item.product),
                  minQty: String(item.minQty ?? item.min_qty ?? 1),
                  maxQty: item.maxQty == null && item.max_qty == null ? '' : String(item.maxQty ?? item.max_qty),
                  unitPrice: String(item.unitPrice ?? item.unit_price ?? ''),
                })),
              };
              setEdit(next);
              setEditBaselineJson(JSON.stringify(next));
            }}
          >
            Edit {row.name}
          </Button>
        ))}
      </Stack>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('sweep2.newPriceList')}</DialogTitle>
        <DialogContent>
          <TextField fullWidth sx={{ mt: 1 }} label={t('sweep.name')} value={name} onChange={(e) => setName(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('sweep2.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || !name || create.isPending} onClick={() => create.mutate()}>
            {t('sweep2.create')}
          </Button>
        </DialogActions>
      </Dialog>
      <UnsavedChangesGuard when={Boolean(edit) && JSON.stringify(edit) !== editBaselineJson} />
      <Dialog open={Boolean(edit)} onClose={() => setEdit(null)} fullWidth maxWidth="md">
        <DialogTitle>Qty slabs — {edit?.name}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(edit?.items ?? []).map((row, idx) => (
              <Stack key={idx} direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  select
                  label={t('sweep.product')}
                  value={row.product}
                  onChange={(e) =>
                    setEdit((cur) =>
                      cur
                        ? {
                            ...cur,
                            items: cur.items.map((it, i) => (i === idx ? { ...it, product: e.target.value } : it)),
                          }
                        : cur,
                    )
                  }
                  sx={{ minWidth: 220 }}
                  helperText={
                    (products.data?.count ?? 0) > productRows.length
                      ? `first ${productRows.length} of ${products.data?.count} shown`
                      : undefined
                  }
                >
                  {productRows.map((p) => (
                    <MenuItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label={t('sweep.minQty')}
                  value={row.minQty}
                  onChange={(e) =>
                    setEdit((cur) =>
                      cur
                        ? { ...cur, items: cur.items.map((it, i) => (i === idx ? { ...it, minQty: e.target.value } : it)) }
                        : cur,
                    )
                  }
                />
                <TextField
                  label={t('sweep.maxQty')}
                  placeholder={t('sweep.openEnded')}
                  value={row.maxQty}
                  onChange={(e) =>
                    setEdit((cur) =>
                      cur
                        ? { ...cur, items: cur.items.map((it, i) => (i === idx ? { ...it, maxQty: e.target.value } : it)) }
                        : cur,
                    )
                  }
                />
                <TextField
                  label={t('sweep.unitPrice')}
                  value={row.unitPrice}
                  onChange={(e) =>
                    setEdit((cur) =>
                      cur
                        ? {
                            ...cur,
                            items: cur.items.map((it, i) => (i === idx ? { ...it, unitPrice: e.target.value } : it)),
                          }
                        : cur,
                    )
                  }
                />
                <Button
                  color="error"
                  size="small"
                  onClick={() =>
                    setEdit((cur) =>
                      cur ? { ...cur, items: cur.items.filter((_, i) => i !== idx) } : cur,
                    )
                  }
                >
                  {t('sweep2.remove')}
                </Button>
              </Stack>
            ))}
            {slabError ? (
              <Alert severity="error" onClose={() => setSlabError('')}>
                {slabError}
              </Alert>
            ) : null}
            <Button
              onClick={() =>
                setEdit((cur) =>
                  cur
                    ? { ...cur, items: [...cur.items, { product: '', minQty: '1', maxQty: '', unitPrice: '' }] }
                    : cur,
                )
              }
            >
              {t('sweep2.addSlab')}
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEdit(null)}>{t('sweep2.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || save.isPending} onClick={() => save.mutate()}>
            {t('sweep2.saveSlabs')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

