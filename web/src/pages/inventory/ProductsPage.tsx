import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
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
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import TableViewOutlinedIcon from '@mui/icons-material/TableViewOutlined';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { createProduct, listProducts, updateProduct } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canImport } from '@/utils/permissions';
import { productStatusTone, statusLabelKey } from '@/utils/status';

const emptyForm: {
  name: string;
  sku: string;
  barcode: string;
  hsnCode: string;
  gstRate: string;
  purchasePrice: string;
  sellingPrice: string;
  reorderLevel: string;
  status: 'ACTIVE' | 'INACTIVE';
} = {
  name: '',
  sku: '',
  barcode: '',
  hsnCode: '',
  gstRate: '18',
  purchasePrice: '0',
  sellingPrice: '0',
  reorderLevel: '0',
  status: 'ACTIVE',
};

export function ProductsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['products'], queryFn: () => listProducts() });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [bulkAnchor, setBulkAnchor] = useState<null | HTMLElement>(null);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        gstRate: Number(form.gstRate),
        purchasePrice: Number(form.purchasePrice),
        sellingPrice: Number(form.sellingPrice),
        reorderLevel: Number(form.reorderLevel),
      };
      if (editing) return updateProduct(editing.id, payload);
      return createProduct(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['products'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.products')}</Typography>
        <Stack direction="row" spacing={1}>
          {canImport(user) ? (
            <>
              <Button variant="outlined" onClick={(e) => setBulkAnchor(e.currentTarget)}>
                {t('products.bulkActions')}
              </Button>
              <Menu
                anchorEl={bulkAnchor}
                open={Boolean(bulkAnchor)}
                onClose={() => setBulkAnchor(null)}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
              >
                <MenuItem
                  onClick={() => {
                    setBulkAnchor(null);
                    void navigate('/settings/import?kind=PRODUCTS');
                  }}
                >
                  <ListItemIcon>
                    <TableViewOutlinedIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={t('products.bulkAddItems')}
                    secondary={t('products.bulkAddItemsHint')}
                  />
                </MenuItem>
                <MenuItem
                  onClick={() => {
                    setBulkAnchor(null);
                    void navigate('/purchases/bill-upload');
                  }}
                >
                  <ListItemIcon>
                    <CloudUploadOutlinedIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={t('products.purchaseBillUpload')}
                    secondary={t('products.purchaseBillUploadHint')}
                  />
                </MenuItem>
              </Menu>
            </>
          ) : null}
          <Button
            variant="contained"
            onClick={() => {
              setEditing(null);
              setForm(emptyForm);
              setOpen(true);
            }}
          >
            {t('common.add')}
          </Button>
        </Stack>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description={t('empty.products')} /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.sku')}</TableCell>
                <TableCell>{t('common.barcode')}</TableCell>
                <TableCell align="right">Sale</TableCell>
                <TableCell align="right">GST %</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{p.sku}</TableCell>
                  <TableCell>{p.barcode ?? '—'}</TableCell>
                  <TableCell align="right">{formatMoney(p.sellingPrice)}</TableCell>
                  <TableCell align="right">{toNumber(p.gstRate)}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={productStatusTone(p.status)}
                      labelKey={statusLabelKey(p.status)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => {
                        setEditing(p);
                        setForm({
                          name: p.name,
                          sku: p.sku,
                          barcode: p.barcode ?? '',
                          hsnCode: p.hsnCode ?? '',
                          gstRate: String(p.gstRate),
                          purchasePrice: String(p.purchasePrice),
                          sellingPrice: String(p.sellingPrice),
                          reorderLevel: String(p.reorderLevel),
                          status: p.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE',
                        });
                        setOpen(true);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} product</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('common.sku')}
              required
              value={form.sku}
              onChange={(e) => setForm((f) => ({ ...f, sku: e.target.value }))}
            />
            <TextField
              label={t('common.barcode')}
              value={form.barcode}
              onChange={(e) => setForm((f) => ({ ...f, barcode: e.target.value }))}
            />
            <TextField
              label="HSN"
              value={form.hsnCode}
              onChange={(e) => setForm((f) => ({ ...f, hsnCode: e.target.value }))}
            />
            <TextField
              label="GST %"
              type="number"
              value={form.gstRate}
              onChange={(e) => setForm((f) => ({ ...f, gstRate: e.target.value }))}
            />
            <TextField
              label="Purchase price"
              type="number"
              value={form.purchasePrice}
              onChange={(e) => setForm((f) => ({ ...f, purchasePrice: e.target.value }))}
            />
            <TextField
              label="Selling price"
              type="number"
              value={form.sellingPrice}
              onChange={(e) => setForm((f) => ({ ...f, sellingPrice: e.target.value }))}
            />
            <TextField
              label="Reorder level"
              type="number"
              value={form.reorderLevel}
              onChange={(e) => setForm((f) => ({ ...f, reorderLevel: e.target.value }))}
            />
            <TextField
              select
              label={t('common.status')}
              value={form.status}
              onChange={(e) =>
                setForm((f) => ({ ...f, status: e.target.value as 'ACTIVE' | 'INACTIVE' }))
              }
            >
              <MenuItem value="ACTIVE">ACTIVE</MenuItem>
              <MenuItem value="INACTIVE">INACTIVE</MenuItem>
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name || !form.sku || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
