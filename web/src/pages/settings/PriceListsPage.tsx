import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { useProductSearch } from '@/hooks/useProductSearch';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { asRows, DataTable, type Row } from '@/pages/phase/phaseShared';
import type { PriceListRow } from '@/utils/priceList';
import { useIdempotentSave } from '@/hooks/useIdempotentSave';
import { settingsErrorText } from '@/utils/settingsErrors';

type SlabForm = {
  product: string;
  productLabel: string;
  minQty: string;
  maxQty: string;
  unitPrice: string;
  discountPct: string;
};
type Editing = { id: number; name: string; updatedAt?: string; items: SlabForm[] };

const KEY = ['price-lists'];

/** One message per problem so the owner can fix them all, not one at a time. */
function validateSlabs(rows: SlabForm[]): string[] {
  const problems: string[] = [];
  const byProduct = new Map<string, Array<{ lo: number; hi: number }>>();
  rows.forEach((row, i) => {
    const n = String(i + 1);
    if (!Number(row.product)) problems.push(t('priceLists.problemProduct', { n }));
    const price = Number(row.unitPrice);
    if (row.unitPrice.trim() === '' || Number.isNaN(price) || price < 0) problems.push(t('priceLists.problemPrice', { n }));
    const lo = Number(row.minQty || 1);
    const hi = row.maxQty.trim() === '' ? Number.POSITIVE_INFINITY : Number(row.maxQty);
    if (Number.isNaN(lo) || lo < 1) problems.push(t('priceLists.problemMin', { n }));
    if (!Number.isNaN(hi) && hi < lo) problems.push(t('priceLists.problemMax', { n }));
    const disc = Number(row.discountPct || 0);
    if (Number.isNaN(disc) || disc < 0 || disc > 100) problems.push(t('priceLists.problemDiscount', { n }));
    if (Number(row.product) && !Number.isNaN(lo) && !Number.isNaN(hi)) {
      const list = byProduct.get(row.product) ?? [];
      if (list.some((r) => lo <= r.hi && hi >= r.lo)) problems.push(t('priceLists.problemOverlap', { n }));
      list.push({ lo, hi });
      byProduct.set(row.product, list);
    }
  });
  return problems;
}

function ProductCell({
  row,
  onPick,
}: {
  row: SlabForm;
  onPick: (id: string, label: string) => void;
}) {
  const search = useProductSearch({});
  const selected = row.product
    ? ({ id: Number(row.product), name: row.productLabel } as unknown as (typeof search.options)[number])
    : null;
  return (
    <Autocomplete
      sx={{ minWidth: 260 }}
      options={search.options}
      value={selected}
      loading={search.isFetching}
      filterOptions={(x) => x}
      getOptionLabel={(p) => (p.sku ? `${p.name} (${p.sku})` : p.name)}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_e, value, reason) => {
        if (reason === 'input') search.setProductQuery(value);
      }}
      onChange={(_e, p) => onPick(p ? String(p.id) : '', p ? (p.sku ? `${p.name} (${p.sku})` : p.name) : '')}
      renderInput={(params) => (
        <TextField {...params} label={t('sweep.product')} helperText={search.helperText} />
      )}
    />
  );
}

export function PriceListsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: api.listPriceLists });
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [edit, setEdit] = useState<Editing | null>(null);
  const [baseline, setBaseline] = useState('');
  const [problems, setProblems] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [switchOff, setSwitchOff] = useState<{ list: PriceListRow; names: string[] } | null>(null);

  const refresh = () => void qc.invalidateQueries({ queryKey: KEY });

  const idem = useIdempotentSave();
  const create = useMutation({
    mutationFn: () => api.createPriceList({ name: name.trim() }, idem.headers()),
    onSuccess: () => {
      idem.renew();
      setCreateOpen(false);
      setName('');
      setError('');
      refresh();
    },
    onError: (e) => setError(settingsErrorText(e)),
  });

  const save = useMutation({
    mutationFn: () => {
      if (!edit) return Promise.reject(new Error('No list'));
      return api.updatePriceList(edit.id, {
        expected_updated_at: edit.updatedAt,
        name: edit.name,
        items: edit.items.map((row) => ({
          product: Number(row.product),
          minQty: Number(row.minQty || 1),
          maxQty: row.maxQty.trim() === '' ? null : Number(row.maxQty),
          unitPrice: Number(row.unitPrice),
          // Kept, not reset: saving a list replaces its slabs, and a slab's discount used to be lost here.
          discountPct: Number(row.discountPct || 0),
        })),
      });
    },
    onSuccess: () => {
      setEdit(null);
      setProblems([]);
      setError('');
      refresh();
    },
    onError: (e) => setProblems([settingsErrorText(e)]),
  });

  const setActive = useMutation({
    mutationFn: ({ id, active, confirm }: { id: number; active: boolean; confirm?: boolean }) =>
      api.updatePriceList(id, { is_active: active, ...(confirm ? { confirm_customers: true } : {}) }),
    onSuccess: () => {
      setSwitchOff(null);
      refresh();
    },
    onError: (e) => {
      setSwitchOff(null);
      setError(settingsErrorText(e));
    },
  });

  const askSwitchOff = async (list: PriceListRow) => {
    setError('');
    if (!list.customerCount) {
      setActive.mutate({ id: list.id, active: false });
      return;
    }
    try {
      const customers = await api.listPriceListCustomers(list.id);
      setSwitchOff({ list, names: customers.map((c) => c.name) });
    } catch (e) {
      setError(settingsErrorText(e));
    }
  };

  const openEdit = (list: PriceListRow) => {
    const next: Editing = {
      id: list.id,
      name: list.name ?? '',
      updatedAt: list.updatedAt,
      items: (list.items ?? []).map((item) => ({
        product: String(item.product),
        productLabel: item.productSku ? `${item.productName ?? ''} (${item.productSku})` : (item.productName ?? ''),
        minQty: String(item.minQty ?? item.min_qty ?? 1),
        maxQty: item.maxQty == null && item.max_qty == null ? '' : String(item.maxQty ?? item.max_qty),
        unitPrice: String(item.unitPrice ?? item.unit_price ?? ''),
        discountPct: String(item.discountPct ?? item.discount_pct ?? 0),
      })),
    };
    setEdit(next);
    setBaseline(JSON.stringify(next));
    setProblems([]);
  };

  const patchRow = (idx: number, patch: Partial<SlabForm>) =>
    setEdit((cur) => (cur ? { ...cur, items: cur.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)) } : cur));

  const byId = (row: Row) => (query.data ?? []).find((l) => l.id === Number(row.id)) as PriceListRow;

  return (
    <SettingsPage
      title={t('phase.priceLists')}
      purpose={t('priceLists.purpose')}
      actions={
        <Button variant="contained" onClick={() => { setError(''); setCreateOpen(true); }} disabled={writesBlocked}>
          {t('sweep2.newList')}
        </Button>
      }
    >
      <Alert severity="info">{t('priceLists.howItWorks')}</Alert>
      {error && !createOpen ? <Alert severity="error" onClose={() => setError('')}>{error}</Alert> : null}
      <AsyncSection
        query={query}
        isEmpty={(rows) => rows.length === 0}
        empty={{ description: t('priceLists.empty') }}
      >
        {(rows) => (
          <DataTable
            rows={asRows(rows)}
            empty={t('priceLists.empty')}
            columns={[
              { key: 'name', label: t('sweep.name') },
              { key: 'itemCount', label: t('priceLists.colSlabs'), render: (row) => String(row.itemCount ?? 0) },
              { key: 'customerCount', label: t('priceLists.colCustomers'), render: (row) => String(row.customerCount ?? 0) },
              {
                key: 'isActive',
                label: '',
                render: (row) =>
                  row.isActive === false ? <Chip size="small" label={t('priceLists.chipOff')} /> : <Chip size="small" color="success" variant="outlined" label={t('priceLists.chipOn')} />,
              },
            ]}
            actions={(row) => {
              const list = byId(row);
              return (
                <Stack direction="row" spacing={1}>
                  <Button size="small" disabled={writesBlocked} onClick={() => openEdit(list)}>
                    {t('priceLists.editSlabs')}
                  </Button>
                  {list.isActive === false ? (
                    <Button size="small" disabled={writesBlocked} onClick={() => setActive.mutate({ id: list.id, active: true })}>
                      {t('priceLists.switchOn')}
                    </Button>
                  ) : (
                    <Button size="small" color="error" disabled={writesBlocked} onClick={() => void askSwitchOff(list)}>
                      {t('priceLists.switchOff')}
                    </Button>
                  )}
                </Stack>
              );
            }}
          />
        )}
      </AsyncSection>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('sweep2.newPriceList')}</DialogTitle>
        <DialogContent>
          <TextField fullWidth sx={{ mt: 1 }} label={t('sweep.name')} value={name} onChange={(e) => setName(e.target.value)} />
          {error ? <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>{t('sweep2.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || !name.trim() || create.isPending} onClick={() => idem.once(create.mutate)}>
            {t('sweep2.create')}
          </Button>
        </DialogActions>
      </Dialog>

      <UnsavedChangesGuard when={edit !== null && JSON.stringify(edit) !== baseline} />
      <Dialog open={edit !== null} onClose={() => setEdit(null)} fullWidth maxWidth="lg">
        <DialogTitle>{t('priceLists.slabsTitle', { name: edit?.name ?? '' })}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {(edit?.items ?? []).map((row, idx) => (
              <Stack key={idx} direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'flex-start' }}>
                <ProductCell row={row} onPick={(id, label) => patchRow(idx, { product: id, productLabel: label })} />
                <TextField label={t('sweep.minQty')} value={row.minQty} onChange={(e) => patchRow(idx, { minQty: e.target.value })} />
                <TextField
                  label={t('sweep.maxQty')}
                  placeholder={t('sweep.openEnded')}
                  value={row.maxQty}
                  onChange={(e) => patchRow(idx, { maxQty: e.target.value })}
                />
                <TextField label={t('sweep.unitPrice')} value={row.unitPrice} onChange={(e) => patchRow(idx, { unitPrice: e.target.value })} />
                <TextField label={t('priceLists.discount')} value={row.discountPct} onChange={(e) => patchRow(idx, { discountPct: e.target.value })} />
                <Button
                  color="error"
                  size="small"
                  onClick={() => setEdit((cur) => (cur ? { ...cur, items: cur.items.filter((_, i) => i !== idx) } : cur))}
                >
                  {t('sweep2.remove')}
                </Button>
              </Stack>
            ))}
            {problems.length > 0 ? (
              <Alert severity="error" onClose={() => setProblems([])}>
                <Stack component="ul" sx={{ m: 0, pl: 2 }}>
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </Stack>
              </Alert>
            ) : null}
            <Button
              sx={{ alignSelf: 'flex-start' }}
              onClick={() =>
                setEdit((cur) =>
                  cur
                    ? { ...cur, items: [...cur.items, { product: '', productLabel: '', minQty: '1', maxQty: '', unitPrice: '', discountPct: '0' }] }
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
          <Button
            variant="contained"
            disabled={writesBlocked || save.isPending}
            onClick={() => {
              const found = validateSlabs(edit?.items ?? []);
              setProblems(found);
              if (found.length === 0) save.mutate();
            }}
          >
            {t('sweep2.saveSlabs')}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={switchOff !== null}
        title={t('priceLists.offTitle', { name: switchOff?.list.name ?? '' })}
        body={`${t('priceLists.offBody', { count: String(switchOff?.list.customerCount ?? 0) })}\n\n${(switchOff?.names ?? []).slice(0, 10).join(', ')}${
          (switchOff?.list.customerCount ?? 0) > 10 ? ` ${t('priceLists.offMore', { n: String((switchOff?.list.customerCount ?? 0) - 10) })}` : ''
        }`}
        confirmLabel={t('priceLists.switchOff')}
        confirmColor="error"
        confirming={setActive.isPending}
        onClose={() => setSwitchOff(null)}
        onConfirm={() => switchOff && setActive.mutate({ id: switchOff.list.id, active: false, confirm: true })}
      />
    </SettingsPage>
  );
}
