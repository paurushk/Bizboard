import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import DeleteIcon from '@mui/icons-material/Delete';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { createSalesInvoice, listSalesInvoicesPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState } from '@/components/PageState';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useProductSearch } from '@/hooks/useProductSearch';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { Customer, Product } from '@/types/domain';
import { canCreateSales } from '@/utils/permissions';
import { formatMoney, toNumber } from '@/utils/money';
import { ForbiddenPage } from '@/pages/ForbiddenPage';

const RECENT_SKUS_KEY = 'bizboard:quick-entry-recent-skus';
const RECENT_SKUS_MAX = 8;

interface RecentSku {
  id: number;
  name: string;
  sku: string;
  sellingPrice: string | number;
  gstRate?: string | number;
}

function loadRecentSkus(companyId: number): RecentSku[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(`${RECENT_SKUS_KEY}:${companyId}`);
    return raw ? (JSON.parse(raw) as RecentSku[]) : [];
  } catch {
    return [];
  }
}

function saveRecentSku(companyId: number, product: Product) {
  if (typeof localStorage === 'undefined') return;
  const existing = loadRecentSkus(companyId).filter((p) => p.id !== product.id);
  const next = [
    { id: product.id, name: product.name, sku: product.sku, sellingPrice: product.sellingPrice, gstRate: product.gstRate },
    ...existing,
  ].slice(0, RECENT_SKUS_MAX);
  try {
    localStorage.setItem(`${RECENT_SKUS_KEY}:${companyId}`, JSON.stringify(next));
  } catch {
    // best-effort — a full/blocked localStorage must not break quick-entry
  }
}

interface QuickLine {
  key: string;
  productId: number;
  name: string;
  quantity: number;
  unitPrice: number;
  gstRate: number;
}

/**
 * QOS-0048 — a keyboard-light order-booking sheet for a field rep between
 * customer visits: recent customers + recent SKUs as one-tap chips, a
 * stepper for quantity instead of typing, one "Save order" action. Voice
 * capture and full offline booking are deliberately out of scope for this
 * pass (offline order-booking itself isn't in pilot scope yet) — this is
 * the online quick-entry half only.
 */
export function QuickEntryPage() {
  const { user } = useAuth();
  const companyId = user?.companyId ?? 0;
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [lines, setLines] = useState<QuickLine[]>([]);
  const [recentSkus, setRecentSkus] = useState<RecentSku[]>(() => loadRecentSkus(companyId));
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [saveError, setSaveError] = useState<unknown>(null);

  const customerSearch = useCustomerSearch({ selected: customer });
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct });

  const recentInvoices = useQuery({
    queryKey: ['quick-entry-recent-invoices'],
    queryFn: () => listSalesInvoicesPage({ page: 1, pageSize: 10 }),
  });

  const recentCustomers = useMemo(() => {
    const seen = new Set<number>();
    const out: { id: number; name: string }[] = [];
    for (const inv of recentInvoices.data?.results ?? []) {
      const id = inv.customer;
      const name = inv.customerName;
      if (!id || seen.has(id) || !name) continue;
      seen.add(id);
      out.push({ id, name });
      if (out.length >= 6) break;
    }
    return out;
  }, [recentInvoices.data]);

  useEffect(() => {
    setRecentSkus(loadRecentSkus(companyId));
  }, [companyId]);

  const addLine = (product: Product | RecentSku) => {
    saveRecentSku(companyId, product as Product);
    setRecentSkus(loadRecentSkus(companyId));
    setLines((current) => {
      const existing = current.find((l) => l.productId === product.id);
      if (existing) {
        return current.map((l) => (l.productId === product.id ? { ...l, quantity: l.quantity + 1 } : l));
      }
      return [
        ...current,
        {
          key: `${product.id}-${Date.now()}`,
          productId: product.id,
          name: product.name,
          quantity: 1,
          unitPrice: toNumber(product.sellingPrice),
          gstRate: toNumber((product as Product).gstRate ?? (product as RecentSku).gstRate ?? 0),
        },
      ];
    });
    setPendingProduct(null);
    productSearch.setProductQuery('');
  };

  const bump = (key: string, delta: number) => {
    setLines((current) =>
      current
        .map((l) => (l.key === key ? { ...l, quantity: l.quantity + delta } : l))
        .filter((l) => l.quantity > 0),
    );
  };

  const removeLine = (key: string) => setLines((current) => current.filter((l) => l.key !== key));

  const total = lines.reduce((sum, l) => sum + l.quantity * l.unitPrice, 0);

  const save = useMutation({
    mutationFn: () =>
      createSalesInvoice({
        customer: customer!.id,
        items: lines.map((l) => ({
          product: l.productId,
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: l.gstRate,
        })),
      }),
    onSuccess: (invoice) => {
      setSaveError(null);
      void qc.invalidateQueries({ queryKey: ['quick-entry-recent-invoices'] });
      navigate(`/sales/history/${invoice.id}`);
    },
    onError: (e) => setSaveError(e),
  });

  if (!canCreateSales(user)) return <ForbiddenPage />;

  return (
    <Stack spacing={2} sx={{ maxWidth: 480, mx: 'auto', pb: 8 }}>
      <PageTitle variant="h5">{t('quickEntry.pageTitle')}</PageTitle>

      {saveError ? <HelpErrorAlert error={saveError} /> : null}

      <Paper sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          {t('quickEntry.customer')}
        </Typography>
        {customer ? (
          <Chip label={customer.name} onDelete={() => setCustomer(null)} color="primary" sx={{ mb: 1 }} />
        ) : (
          <>
            {recentCustomers.length > 0 ? (
              <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mb: 1 }}>
                {recentCustomers.map((c) => (
                  <Chip
                    key={c.id}
                    label={c.name}
                    onClick={() => setCustomer({ id: c.id, name: c.name } as Customer)}
                    variant="outlined"
                  />
                ))}
              </Stack>
            ) : null}
            <Autocomplete<Customer>
              options={customerSearch.options}
              loading={customerSearch.isFetching}
              filterOptions={(opts) => opts}
              inputValue={customerSearch.query}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear' || reason === 'reset') customerSearch.setQuery(v);
              }}
              onChange={(_, value) => setCustomer(value)}
              getOptionLabel={(c) => c.name}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              renderInput={(params) => <TextField {...params} size="small" label={t('quickEntry.searchCustomer')} />}
            />
          </>
        )}
      </Paper>

      <Paper sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          {t('quickEntry.addItem')}
        </Typography>
        {recentSkus.length > 0 ? (
          <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mb: 1 }}>
            {recentSkus.map((p) => (
              <Chip key={p.id} label={p.name} onClick={() => addLine(p)} variant="outlined" />
            ))}
          </Stack>
        ) : null}
        <Autocomplete<Product>
          options={productSearch.options}
          loading={productSearch.isFetching}
          filterOptions={(opts) => opts}
          inputValue={productSearch.productQuery}
          onInputChange={(_, v, reason) => {
            if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
          }}
          value={pendingProduct}
          onChange={(_, value) => value && addLine(value)}
          getOptionLabel={(p) => `${p.name} (${p.sku})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} size="small" label={t('quickEntry.searchProduct')} />}
        />
      </Paper>

      {lines.length === 0 ? (
        <EmptyState description={t('quickEntry.empty')} />
      ) : (
        <Stack spacing={1}>
          {lines.map((line) => (
            <Paper key={line.key} sx={{ p: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography noWrap fontWeight={600}>
                  {line.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatMoney(line.unitPrice)} {t('quickEntry.each')}
                </Typography>
              </Box>
              <IconButton size="small" onClick={() => bump(line.key, -1)} aria-label={t('quickEntry.decrease')}>
                <RemoveIcon fontSize="small" />
              </IconButton>
              <Typography sx={{ minWidth: 24, textAlign: 'center' }}>{line.quantity}</Typography>
              <IconButton size="small" onClick={() => bump(line.key, 1)} aria-label={t('quickEntry.increase')}>
                <AddIcon fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={() => removeLine(line.key)} aria-label={t('common.delete')}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Paper>
          ))}
        </Stack>
      )}

      {lines.length > 0 ? (
        <Paper sx={{ p: 1.5, position: 'sticky', bottom: 8 }} elevation={4}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle1">{t('common.total')}</Typography>
            <Typography variant="h6">{formatMoney(total)}</Typography>
          </Stack>
          {!customer ? (
            <Alert severity="info" sx={{ mb: 1 }}>
              {t('quickEntry.pickCustomerFirst')}
            </Alert>
          ) : null}
          <Button
            fullWidth
            variant="contained"
            size="large"
            disabled={!customer || lines.length === 0 || save.isPending}
            onClick={() => save.mutate()}
          >
            {t('quickEntry.saveOrder')}
          </Button>
        </Paper>
      ) : null}
    </Stack>
  );
}
