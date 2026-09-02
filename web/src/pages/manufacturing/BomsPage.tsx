import { useMemo, useState } from 'react';
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
import { listProducts } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;
const BOM_STATUSES = ['DRAFT', 'ACTIVE', 'ARCHIVED'] as const;

const emptyLine = (): BomLine => ({ component: 0, qty: '1' });

type BomForm = {
  product: number | '';
  name: string;
  status: string;
  lines: BomLine[];
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
  const productsQuery = useQuery({ queryKey: ['products'], queryFn: () => listProducts() });

  const productMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const p of productsQuery.data ?? []) map.set(p.id, p.name);
    return map;
  }, [productsQuery.data]);

  const rows = query.data?.results ?? [];

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
    setOpen(true);
  };

  const openEdit = (bom: Bom) => {
    setEditing(bom);
    setForm({
      product: bom.product,
      name: bom.name,
      status: bom.status,
      lines: bom.lines.length ? bom.lines.map((l) => ({ ...l })) : [emptyLine()],
    });
    setOpen(true);
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
            <TextField
              select
              label={t('nav.products')}
              required
              value={form.product}
              onChange={(e) => setForm((f) => ({ ...f, product: Number(e.target.value) }))}
            >
              <MenuItem value="">—</MenuItem>
              {(productsQuery.data ?? []).map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.name}
                </MenuItem>
              ))}
            </TextField>
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
              <Stack key={idx} direction="row" spacing={1} alignItems="center">
                <TextField
                  select
                  label={t('nav.products')}
                  sx={{ flex: 2 }}
                  value={line.component || ''}
                  onChange={(e) =>
                    setForm((f) => {
                      const lines = [...f.lines];
                      lines[idx] = { ...lines[idx], component: Number(e.target.value) };
                      return { ...f, lines };
                    })
                  }
                >
                  <MenuItem value="">—</MenuItem>
                  {(productsQuery.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={p.id}>
                      {p.name}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label={t('erp.qty')}
                  type="number"
                  sx={{ flex: 1 }}
                  value={line.qty}
                  onChange={(e) =>
                    setForm((f) => {
                      const lines = [...f.lines];
                      lines[idx] = { ...lines[idx], qty: e.target.value };
                      return { ...f, lines };
                    })
                  }
                />
                <IconButton
                  aria-label={t('common.remove')}
                  disabled={form.lines.length <= 1}
                  onClick={() =>
                    setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }))
                  }
                >
                  <DeleteIcon />
                </IconButton>
              </Stack>
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
