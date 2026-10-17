import { useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { asRows, DataTable } from '@/pages/phase/phaseShared';
import type { Product } from '@/types/domain';
import { t } from '@/i18n';

/**
 * Per-godown reorder rules: a rule here overrides the item's company-wide reorder level for that
 * godown. Lives beside the Low stock list, which is where these rules take effect.
 */
export function GodownReorderRules() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const reorders = useQuery({ queryKey: ['reorder-levels'], queryFn: api.listReorderLevels });
  const [open, setOpen] = useState(false);
  const [warehouse, setWarehouse] = useState('');
  const [qty, setQty] = useState('');
  const [product, setProduct] = useState<Product | null>(null);
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const [error, setError] = useState('');
  const customDefs = useVisibleCustomFieldDefs();
  const productSearch = useProductSearch({ activeOnly: true, selected: product, cf: cfFilters });

  const save = useMutation({
    mutationFn: () =>
      api.createReorderLevel({ warehouse: Number(warehouse), product: Number(product?.id), reorderLevel: qty }),
    onSuccess: () => {
      setOpen(false);
      setQty('');
      setProduct(null);
      setError('');
      void qc.invalidateQueries({ queryKey: ['reorder-levels'] });
      void qc.invalidateQueries({ queryKey: ['low-stock'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={1} sx={{ mt: 3 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{t('sweep2.perGodownReorder')}</Typography>
        <Button variant="outlined" onClick={() => setOpen(true)} disabled={writesBlocked}>
          {t('sweep2.addGodownReorder')}
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {t('inventory.godownReorderHelp')}
      </Typography>
      <DataTable
        rows={asRows(reorders.data)}
        empty={t('items.noReorderRules')}
        virtualized
        columns={[
          { key: 'productName', label: t('items.item') },
          { key: 'warehouseName', label: t('items.godown') },
          { key: 'reorderLevel', label: t('items.reorderQty') },
        ]}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('items.perGodownReorder')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
            <Autocomplete
              options={productSearch.options}
              value={product}
              onChange={(_, value) => setProduct(value)}
              getOptionLabel={(option) => option.name}
              inputValue={productSearch.productQuery}
              onInputChange={(_, value) => productSearch.setProductQuery(value)}
              renderInput={(params) => <TextField {...params} label={t('items.item')} helperText={productSearch.helperText} />}
            />
            <TextField select label={t('items.godown')} value={warehouse} onChange={(e) => setWarehouse(e.target.value)}>
              {(warehouses.data ?? []).map((w) => (
                <MenuItem key={w.id} value={String(w.id)}>
                  {w.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label={t('items.reorderQty')} type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!product || !warehouse || !qty || writesBlocked || save.isPending}
            onClick={() => save.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
