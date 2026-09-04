import { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
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
import DeleteIcon from '@mui/icons-material/Delete';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  createBom,
  listBomsPage,
  updateBom,
  type Bom,
  type BomLine,
} from '@/api/manufacturing';
import { getProduct } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { useProductSearch } from '@/hooks/useProductSearch';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import type { Product } from '@/types/domain';

const PAGE_SIZE = 50;
const BOM_STATUSES = ['DRAFT', 'ACTIVE', 'ARCHIVED'] as const;

// F2-025: the local form keeps a resolved Product alongside each line's raw
// id so the component Autocomplete can show a name without loading the
// entire product catalog (was listProducts() pulling every product).
type BomLineForm = BomLine & { componentProduct?: Product | null };

const emptyLine = (): BomLineForm => ({ component: 0, qty: '1', componentProduct: null });

type BomForm = {
  product: number | '';
  name: string;
  status: string;
  lines: BomLineForm[];
};

const emptyForm = (): BomForm => ({
  product: '',
  name: '',
  status: 'DRAFT',
  lines: [emptyLine()],
});

export function BomsPage() {
  return (
    <ModuleGate module="manufacturing" title={t('nav.boms')}>
      <BomsPageInner />
    </ModuleGate>
  );
}

function BomsPageInner() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Bom | null>(null);
  const [form, setForm] = useState<BomForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['boms', page],
    queryFn: () => listBomsPage({ page, pageSize: PAGE_SIZE }),
  });
  const rows = useMemo(() => query.data?.results ?? [], [query.data]);

  // F2-025: resolve just the product names needed for the current page of
  // rows, instead of loading the entire product catalog up front.
  const [productMap, setProductMap] = useState<Map<number, string>>(new Map());
  useEffect(() => {
    const ids = Array.from(new Set(rows.map((r) => r.product))).filter((id) => !productMap.has(id));
    if (!ids.length) return;
    let cancelled = false;
    void Promise.all(ids.map((id) => getProduct(id).catch(() => null))).then((resolved) => {
      if (cancelled) return;
      setProductMap((prev) => {
        const next = new Map(prev);
        for (const p of resolved) if (p) next.set(p.id, p.name);
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [rows, productMap]);

  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const productSearch = useProductSearch({ selected: selectedProduct });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        product: Number(form.product),
        name: form.name,
        status: form.status,
        lines: form.lines.filter((l) => l.component > 0).map((l) => ({
          component: l.component,
          qty: l.qty,
        })),
      };
      if (editing) return updateBom(editing.id, payload);
      return createBom(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm());
      void qc.invalidateQueries({ queryKey: ['boms'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setSelectedProduct(null);
    setOpen(true);
  };

  const openEdit = (bom: Bom) => {
    setEditing(bom);
    const lines: BomLineForm[] = bom.lines.length ? bom.lines.map((l) => ({ ...l, componentProduct: null })) : [emptyLine()];
    setForm({
      product: bom.product,
      name: bom.name,
      status: bom.status,
      lines,
    });
    setSelectedProduct(null);
    setOpen(true);
    // F2-025: resolve the assembled product + each line's component by id
    // rather than pulling the whole catalog to find their names.
    void getProduct(bom.product).then(setSelectedProduct).catch(() => {});
    const ids = Array.from(new Set(lines.map((l) => l.component).filter((id) => id > 0)));
    void Promise.all(ids.map((id) => getProduct(id).catch(() => null))).then((resolved) => {
      const byId = new Map(resolved.filter((p): p is Product => !!p).map((p) => [p.id, p]));
      setForm((f) => ({
        ...f,
        lines: f.lines.map((l) => (byId.has(l.component) ? { ...l, componentProduct: byId.get(l.component) } : l)),
      }));
    });
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="manufacturing" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.boms')}</Typography>
        <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.boms')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell>{t('erp.components')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((bom) => (
                <TableRow key={bom.id}>
                  <TableCell>{bom.name}</TableCell>
                  <TableCell>{productMap.get(bom.product) ?? bom.product}</TableCell>
                  <TableCell>{bom.lines?.length ?? 0}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(bom.status)}
                      labelKey={statusLabelKey(bom.status)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(bom)} disabled={writesBlocked}>
                      {t('common.edit')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} BOM</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <Autocomplete
              options={productSearch.options}
              getOptionLabel={(o: Product) => o.name}
              isOptionEqualToValue={(o, v) => o.id === v.id}
              value={selectedProduct}
              onChange={(_, v) => {
                setSelectedProduct(v);
                setForm((f) => ({ ...f, product: v?.id ?? '' }));
              }}
              onInputChange={(_, v) => productSearch.setProductQuery(v)}
              filterOptions={(opts) => opts}
              loading={productSearch.isFetching}
              renderInput={(params) => (
                <TextField {...params} label={t('nav.products')} required helperText={productSearch.helperText} />
              )}
            />
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              select
              label={t('common.status')}
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
            >
              {BOM_STATUSES.map((s) => (
                <MenuItem key={s} value={s}>
                  {t(statusLabelKey(s))}
                </MenuItem>
              ))}
            </TextField>
            <Typography variant="subtitle2">{t('erp.components')}</Typography>
            {form.lines.map((line, idx) => (
              <BomLineFields
                key={idx}
                line={line}
                removeDisabled={form.lines.length <= 1}
                onChangeComponent={(p) =>
                  setForm((f) => {
                    const lines = [...f.lines];
                    lines[idx] = { ...lines[idx], component: p?.id ?? 0, componentProduct: p };
                    return { ...f, lines };
                  })
                }
                onChangeQty={(qty) =>
                  setForm((f) => {
                    const lines = [...f.lines];
                    lines[idx] = { ...lines[idx], qty };
                    return { ...f, lines };
                  })
                }
                onRemove={() =>
                  setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }))
                }
              />
            ))}
            <Button
              variant="outlined"
              onClick={() => setForm((f) => ({ ...f, lines: [...f.lines, emptyLine()] }))}
              disabled={writesBlocked}
            >
              {t('erp.addComponent')}
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name || !form.product || writesBlocked || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

// F2-025: one search hook instance per row (rules-of-hooks requires a real
// component, not a per-item call inside form.lines.map).
function BomLineFields({
  line,
  removeDisabled,
  onChangeComponent,
  onChangeQty,
  onRemove,
}: {
  line: BomLineForm;
  removeDisabled: boolean;
  onChangeComponent: (product: Product | null) => void;
  onChangeQty: (qty: string) => void;
  onRemove: () => void;
}) {
  const search = useProductSearch({ selected: line.componentProduct ?? undefined });
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Autocomplete
        options={search.options}
        getOptionLabel={(o: Product) => o.name}
        isOptionEqualToValue={(o, v) => o.id === v.id}
        value={line.componentProduct ?? null}
        onChange={(_, v) => onChangeComponent(v)}
        onInputChange={(_, v) => search.setProductQuery(v)}
        filterOptions={(opts) => opts}
        loading={search.isFetching}
        sx={{ flex: 2 }}
        renderInput={(params) => (
          <TextField {...params} label={t('nav.products')} helperText={search.helperText} />
        )}
      />
      <TextField
        label={t('erp.qty')}
        type="number"
        sx={{ flex: 1 }}
        value={line.qty}
        onChange={(e) => onChangeQty(e.target.value)}
      />
      <IconButton aria-label={t('common.remove')} disabled={removeDisabled} onClick={onRemove}>
        <DeleteIcon />
      </IconButton>
    </Stack>
  );
}
