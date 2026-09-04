import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { HelpHint } from '@/pages/help/HelpHint';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  createOpeningStock,
  createProduct,
  createWarehouse,
  fetchBarcodeImage,
  generateBarcode,
  getCompany,
  listCategories,
  listBrands,
  listStock,
  listUnits,
  listWarehouses,
  searchHsn,
  updateProduct,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { todayIso } from '@/components/billing';
import type { Product } from '@/types/domain';
import { isValidHsnSac, normalizeGstRate, GST_RATE_OPTIONS } from '@/utils/gst';
import { STANDARD_UNITS, formatUnitLabel } from '@/constants/unitLabels';
import { activeCustomFieldDefs, type ItemCustomFieldDef } from './itemCustomFieldDefaults';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type Tracking = 'NONE' | 'BATCH' | 'SERIAL';
type TabKey = 'basic' | 'stock' | 'pricing' | 'custom';

interface LotRow {
  warehouseId: string;
  quantity: string;
  asOf: string;
  unitCost: string;
  batchNo: string;
  expiryDate: string;
  manufacturingDate: string;
}

interface SerialRow {
  warehouseId: string;
  serialNo: string;
  asOf: string;
  unitCost: string;
}

interface FormState {
  productType: 'GOODS' | 'SERVICE';
  name: string;
  sku: string;
  unitName: string;
  barcode: string;
  hsnCode: string;
  description: string;
  gstRate: string;
  purchasePrice: string;
  sellingPrice: string;
  mrp: string;
  wholesalePrice: string;
  sellingTaxInclusive: boolean;
  purchaseTaxInclusive: boolean;
  defaultDiscountPercent: string;
  conversionRate: string;
  alternateUnitName: string;
  categoryName: string;
  brandName: string;
  trackInventory: boolean;
  tracking: Tracking;
  openingStock: string;
  warehouseId: string;
  reorderLevel: string;
  status: 'ACTIVE' | 'INACTIVE';
  customValues: Record<string, string>;
  lots: LotRow[];
  serials: SerialRow[];
}

function emptyLot(warehouseId: string): LotRow {
  return {
    warehouseId,
    quantity: '',
    asOf: todayIso(),
    unitCost: '',
    batchNo: '',
    expiryDate: '',
    manufacturingDate: '',
  };
}

function emptySerial(warehouseId: string): SerialRow {
  return { warehouseId, serialNo: '', asOf: todayIso(), unitCost: '' };
}

function buildForm(
  product: Product | null,
  defaultWarehouseId: string,
  defs: ItemCustomFieldDef[] = [],
): FormState {
  const tracking: Tracking = product?.trackSerial ? 'SERIAL' : product?.trackBatch ? 'BATCH' : 'NONE';
  const custom = product?.customFields ?? {};
  const customValues: Record<string, string> = {};
  for (const def of defs) {
    customValues[def.key] = String(custom[def.key] ?? custom[def.label] ?? '');
  }
  return {
    productType: product?.productType === 'SERVICE' ? 'SERVICE' : 'GOODS',
    name: product?.name ?? '',
    sku: product?.sku ?? '',
    unitName: product?.unitName || 'PCS',
    barcode: product?.barcode ?? '',
    hsnCode: product?.hsnCode ?? '',
    description: product?.description ?? '',
    gstRate: String(product?.gstRate ?? '18'),
    purchasePrice: String(product?.purchasePrice ?? '0'),
    sellingPrice: String(product?.sellingPrice ?? '0'),
    mrp: String(product?.mrp ?? '0'),
    wholesalePrice: String(product?.wholesalePrice ?? '0'),
    sellingTaxInclusive: Boolean(product?.sellingTaxInclusive),
    purchaseTaxInclusive: Boolean(product?.purchaseTaxInclusive),
    defaultDiscountPercent: String(product?.defaultDiscountPercent ?? '0'),
    conversionRate: String(product?.conversionRate ?? '1'),
    alternateUnitName: product?.alternateUnitName ?? '',
    categoryName: product?.categoryName ?? '',
    brandName: product?.brandName ?? '',
    trackInventory: product?.trackInventory !== false,
    tracking,
    openingStock: '0',
    warehouseId: defaultWarehouseId,
    reorderLevel: String(product?.reorderLevel ?? '0'),
    status: product?.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE',
    customValues,
    lots: [emptyLot(defaultWarehouseId)],
    serials: [emptySerial(defaultWarehouseId)],
  };
}

interface Props {
  open: boolean;
  product: Product | null;
  existingNames: string[];
  onClose: () => void;
  onSaved: (keepOpen: boolean) => void;
}

export function ItemFormDialog({ open, product, existingNames, onClose, onSaved }: Props) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany, enabled: open });
  const customDefs = useMemo(
    () =>
      activeCustomFieldDefs(
        companyQuery.data?.itemCustomFieldDefs ?? user?.company?.itemCustomFieldDefs,
      ),
    [companyQuery.data?.itemCustomFieldDefs, user?.company?.itemCustomFieldDefs],
  );
  const warehousesQuery = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses, enabled: open });
  const unitsQuery = useQuery({ queryKey: ['units'], queryFn: listUnits, enabled: open });
  const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: listCategories, enabled: open });
  const brandsQuery = useQuery({ queryKey: ['brands'], queryFn: listBrands, enabled: open });
  const stockQuery = useQuery({ queryKey: ['stock'], queryFn: () => listStock(), enabled: open && Boolean(product) });
  const warehouses = warehousesQuery.data ?? [];
  const defaultWarehouseId = String(warehouses[0]?.id ?? '');
  const [tab, setTab] = useState<TabKey>('basic');
  const [form, setForm] = useState<FormState>(() => buildForm(product, defaultWarehouseId));
  const [error, setError] = useState<string | null>(null);
  const [hsnOpen, setHsnOpen] = useState(false);
  const [hsnQuery, setHsnQuery] = useState('');
  const [godownName, setGodownName] = useState('');
  const [godownCode, setGodownCode] = useState('');
  const [serialPaste, setSerialPaste] = useState('');

  const isService = form.productType === 'SERVICE';
  const locked = Boolean(product?.hasMovements);
  const hsnKind = isService ? 'SAC' : 'HSN';
  const stockHidden = isService || !form.trackInventory;

  // The dropdowns offer a set of common units, but items created via import or the
  // API can carry any unit string. Fold the item's stored units into the option
  // lists so an existing value is always visible (and never silently replaced).
  const baseUnitOptions = useMemo(() => {
    const set = new Set(STANDARD_UNITS);
    for (const unit of unitsQuery.data ?? []) {
      const code = (unit.shortName || unit.uqcCode || unit.name || '').trim();
      if (code) set.add(code);
    }
    if (form.unitName) set.add(form.unitName);
    if (product?.unitName) set.add(product.unitName);
    return [...set];
  }, [form.unitName, product?.unitName, unitsQuery.data]);
  const alternateUnitOptions = useMemo(() => {
    const set = new Set(STANDARD_UNITS.filter((unit) => unit !== form.unitName));
    for (const unit of unitsQuery.data ?? []) {
      const code = (unit.shortName || unit.uqcCode || unit.name || '').trim();
      if (code && code !== form.unitName) set.add(code);
    }
    if (form.alternateUnitName) set.add(form.alternateUnitName);
    if (product?.alternateUnitName && product.alternateUnitName !== form.unitName) {
      set.add(product.alternateUnitName);
    }
    return [...set];
  }, [form.unitName, form.alternateUnitName, product?.alternateUnitName, unitsQuery.data]);
  const unitLabel = (code: string) => {
    const match = (unitsQuery.data ?? []).find(
      (unit) => (unit.shortName || unit.uqcCode || '').toUpperCase() === code.toUpperCase(),
    );
    return formatUnitLabel(code, match?.name);
  };

  useEffect(() => {
    if (!open) return;
    setTab('basic');
    setError(null);
    setForm(buildForm(product, defaultWarehouseId, customDefs));
    // Reset only when the dialog opens or the edited product changes — not when
    // company defs / godowns finish loading, which would wipe in-progress edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, product?.id]);

  useEffect(() => {
    if (!open || !defaultWarehouseId) return;
    setForm((current) => {
      if (current.warehouseId) return current;
      return {
        ...current,
        warehouseId: defaultWarehouseId,
        lots: current.lots.map((lot) => ({ ...lot, warehouseId: lot.warehouseId || defaultWarehouseId })),
        serials: current.serials.map((row) => ({ ...row, warehouseId: row.warehouseId || defaultWarehouseId })),
      };
    });
  }, [open, defaultWarehouseId]);

  useEffect(() => {
    if (!open) return;
    setForm((current) => {
      const customValues = { ...current.customValues };
      let changed = false;
      const stored = product?.customFields ?? {};
      for (const def of customDefs) {
        if (def.key in customValues) continue;
        customValues[def.key] = String(stored[def.key] ?? stored[def.label] ?? '');
        changed = true;
      }
      return changed ? { ...current, customValues } : current;
    });
  }, [open, customDefs, product]);

  useEffect(() => {
    if (tab === 'custom' && customDefs.length === 0) setTab('basic');
  }, [tab, customDefs.length]);

  const hsnSearch = useQuery({
    queryKey: ['hsn-search', hsnQuery, hsnKind],
    queryFn: () => searchHsn(hsnQuery, hsnKind),
    enabled: hsnOpen,
  });

  const createGodown = useMutation({
    mutationFn: async () =>
      (await createWarehouse({
        name: godownName.trim(),
        code: (godownCode || godownName).slice(0, 8).toUpperCase(),
      })) as { id: number | string },
    onSuccess: (created: { id: number | string }) => {
      void qc.invalidateQueries({ queryKey: ['warehouses'] });
      setForm((current) => ({ ...current, warehouseId: String(created.id) }));
      setGodownName('');
      setGodownCode('');
    },
  });

  const duplicateName =
    !product &&
    Boolean(form.name.trim()) &&
    existingNames.some((name) => name.trim().toLowerCase() === form.name.trim().toLowerCase());
  const hsnInvalid = Boolean(form.hsnCode) && !isValidHsnSac(form.hsnCode);
  const customValuesReady = customDefs.every((def) => def.key in form.customValues);
  const conversionRateInvalid =
    Boolean(form.alternateUnitName) && !(Number(form.conversionRate) > 0);
  const canSave =
    Boolean(form.name.trim()) &&
    Boolean(form.sku.trim()) &&
    !hsnInvalid &&
    !conversionRateInvalid &&
    Number(form.purchasePrice) >= 0 &&
    Number(form.sellingPrice) >= 0 &&
    Number(form.reorderLevel) >= 0 &&
    !companyQuery.isLoading &&
    customValuesReady;
  const mrpNum = Number(form.mrp) || 0;
  const sellNum = Number(form.sellingPrice) || 0;
  const discOnMrp = mrpNum > 0 ? (((mrpNum - sellNum) / mrpNum) * 100).toFixed(2) : '';

  const printBarcode = async () => {
    const code = form.barcode.trim();
    if (!code) return;
    try {
      const blob = await fetchBarcodeImage(code);
      const url = URL.createObjectURL(blob);
      const win = window.open('', '_blank', 'width=420,height=280');
      if (!win) {
        URL.revokeObjectURL(url);
        setError('Allow pop-ups to print the barcode.');
        return;
      }
      // F3-013: build the popup with DOM APIs, not string-interpolated HTML —
      // a barcode value like `"><img onerror=...>` executed as script.
      win.document.body.style.cssText = 'text-align:center;font-family:sans-serif;padding:24px';
      const img = win.document.createElement('img');
      img.src = url;
      img.alt = code;
      const label = win.document.createElement('div');
      label.style.marginTop = '8px';
      label.textContent = code;
      win.document.body.append(img, label);
      win.document.close();
      win.focus();
      win.print();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const save = useMutation({
    mutationFn: async (keepOpen: boolean) => {
      if (hsnInvalid) throw new Error('HSN/SAC must be 4, 6, or 8 digits');
      const sku = form.sku.trim();
      if (!sku) throw new Error('Item code is required.');
      const payload: Partial<Product> = {
        name: form.name.trim(),
        sku,
        unitName: form.unitName,
        categoryName: form.categoryName.trim() || undefined,
        brandName: form.brandName.trim() || undefined,
        barcode: form.barcode.trim() || undefined,
        hsnCode: form.hsnCode.trim() || undefined,
        description: form.description.trim() || undefined,
        gstRate: normalizeGstRate(Number(form.gstRate) || 0),
        purchasePrice: Number(form.purchasePrice),
        sellingPrice: Number(form.sellingPrice),
        mrp: Number(form.mrp) || 0,
        wholesalePrice: Number(form.wholesalePrice) || 0,
        reorderLevel: Number(form.reorderLevel),
        productType: form.productType,
        trackInventory: !isService && form.trackInventory,
        trackBatch: !isService && form.tracking === 'BATCH',
        trackSerial: !isService && form.tracking === 'SERIAL',
        sellingTaxInclusive: form.sellingTaxInclusive,
        purchaseTaxInclusive: form.purchaseTaxInclusive,
        defaultDiscountPercent: Number(form.defaultDiscountPercent) || 0,
        conversionRate: Number(form.conversionRate) || 1,
        alternateUnitName: form.alternateUnitName.trim() || undefined,
        status: form.status,
      };
      if (companyQuery.isSuccess || Boolean(user?.company)) {
        payload.customFields = Object.fromEntries(
          customDefs
            .map((def) => [def.key, (form.customValues[def.key] ?? '').trim()] as const)
            .filter(([, value]) => Boolean(value)),
        );
      }
      const saved = product ? await updateProduct(product.id, payload) : await createProduct(payload);
      if (!product && !isService && form.trackInventory) {
        try {
          const defaultCost = Number(form.purchasePrice) > 0 ? Number(form.purchasePrice) : undefined;
        // F3-010: a stable key per opening-stock lot so a retry after a partial
        // failure ("item saved, but opening stock failed") skips the lots that
        // already succeeded instead of doubling them.
        if (form.tracking === 'BATCH') {
          for (const [i, lot] of form.lots.entries()) {
            const qty = Number(lot.quantity);
            if (qty <= 0) continue;
            await createOpeningStock(
              {
                product: saved.id,
                quantity: qty,
                unitCost: lot.unitCost ? Number(lot.unitCost) : defaultCost,
                warehouse: Number(lot.warehouseId) || undefined,
                batchNo: lot.batchNo,
                expiryDate: lot.expiryDate || undefined,
                manufacturingDate: lot.manufacturingDate || undefined,
                asOf: lot.asOf || undefined,
              },
              { idempotencyKey: `opening-${saved.id}-b${i}-${lot.warehouseId || 'x'}-${lot.batchNo || 'x'}` },
            );
          }
        } else if (form.tracking === 'SERIAL') {
          const grouped = new Map<string, SerialRow[]>();
          for (const row of form.serials) {
            if (!row.serialNo.trim()) continue;
            const key = row.warehouseId || defaultWarehouseId;
            grouped.set(key, [...(grouped.get(key) ?? []), row]);
          }
          for (const [warehouseId, rows] of grouped) {
            await createOpeningStock(
              {
                product: saved.id,
                quantity: rows.length,
                warehouse: Number(warehouseId) || undefined,
                serialNumbers: rows.map((row) => row.serialNo.trim()),
                unitCost: rows[0]?.unitCost ? Number(rows[0].unitCost) : defaultCost,
                asOf: rows[0]?.asOf,
              },
              { idempotencyKey: `opening-${saved.id}-s-${warehouseId || 'x'}` },
            );
          }
        } else if (Number(form.openingStock) > 0) {
          await createOpeningStock(
            {
              product: saved.id,
              quantity: Number(form.openingStock),
              unitCost: defaultCost,
              warehouse: Number(form.warehouseId) || undefined,
            },
            { idempotencyKey: `opening-${saved.id}-simple-${form.warehouseId || 'x'}` },
          );
        }
        } catch (err) {
          throw new Error(`Item saved, but opening stock failed: ${getErrorMessage(err)}`);
        }
      }
      return keepOpen;
    },
    onSuccess: (keepOpen) => {
      void qc.invalidateQueries({ queryKey: ['products'] });
      void qc.invalidateQueries({ queryKey: ['products-count'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
      onSaved(keepOpen);
      if (keepOpen) {
        setForm(buildForm(null, defaultWarehouseId, customDefs));
        setTab('basic');
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const patchLot = (index: number, patch: Partial<LotRow>) =>
    setForm((current) => {
      const lots = [...current.lots];
      lots[index] = { ...lots[index], ...patch };
      return { ...current, lots };
    });
  const patchSerial = (index: number, patch: Partial<SerialRow>) =>
    setForm((current) => {
      const serials = [...current.serials];
      serials[index] = { ...serials[index], ...patch };
      return { ...current, serials };
    });

  return (
    <>
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
        <DialogTitle>
          {product ? t('common.edit') : t('empty.createItem')}
        </DialogTitle>
        <DialogContent>
          <Tabs value={tab} onChange={(_, value: TabKey) => setTab(value)} sx={{ mb: 2 }} variant="scrollable">
            <Tab value="basic" label="Basic details" />
            <Tab value="stock" label="Stock details" disabled={isService} />
            <Tab value="pricing" label="Pricing details" />
            {customDefs.length ? <Tab value="custom" label="Custom fields" /> : null}
          </Tabs>
          {error ? (
            <HelpErrorAlert message={error} sx={{ mb: 2 }} />
          ) : null}
          {duplicateName ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              An item with this name already exists — check SKU when billing. Duplicate names are allowed.
            </Alert>
          ) : null}

          {tab === 'basic' ? (
            <Stack spacing={2}>
              <TextField
                select
                label="Item type"
                value={form.productType}
                onChange={(e) =>
                  setForm((current) => ({
                    ...current,
                    productType: e.target.value as 'GOODS' | 'SERVICE',
                    trackInventory: e.target.value !== 'SERVICE',
                    tracking: e.target.value === 'SERVICE' ? 'NONE' : current.tracking,
                  }))
                }
                disabled={locked}
              >
                <MenuItem value="GOODS">Goods</MenuItem>
                <MenuItem value="SERVICE">Service</MenuItem>
              </TextField>
              <TextField
                label={t('common.name')}
                required
                value={form.name}
                onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
                helperText={duplicateName ? 'An item with this name already exists — check SKU when billing' : undefined}
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label={t('products.category')}
                  value={form.categoryName}
                  onChange={(e) => setForm((current) => ({ ...current, categoryName: e.target.value }))}
                  placeholder={t('products.categoryPlaceholder')}
                  helperText={t('products.categoryHint')}
                  sx={{ flex: 1 }}
                  InputProps={{
                    inputProps: { list: 'item-form-categories' },
                  }}
                />
                <datalist id="item-form-categories">
                  {(categoriesQuery.data ?? []).map((row) => (
                    <option key={row.id} value={row.name} />
                  ))}
                </datalist>
                <TextField
                  label={t('products.brand')}
                  value={form.brandName}
                  onChange={(e) => setForm((current) => ({ ...current, brandName: e.target.value }))}
                  placeholder={t('products.brandPlaceholder')}
                  helperText={t('products.brandHint')}
                  sx={{ flex: 1 }}
                  InputProps={{
                    inputProps: { list: 'item-form-brands' },
                  }}
                />
                <datalist id="item-form-brands">
                  {(brandsQuery.data ?? []).map((row) => (
                    <option key={row.id} value={row.name} />
                  ))}
                </datalist>
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label={t('products.skuRequired')}
                  helperText={t('products.skuRequiredHint')}
                  required
                  value={form.sku}
                  onChange={(e) => setForm((current) => ({ ...current, sku: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label={t('common.barcode')}
                  value={form.barcode}
                  onChange={(e) => setForm((current) => ({ ...current, barcode: e.target.value }))}
                  sx={{ flex: 1 }}
                  InputProps={{
                    endAdornment: (
                      <Stack direction="row" spacing={0.5}>
                        {form.barcode.trim() ? (
                          <Button size="small" onClick={() => void printBarcode()}>
                            {t('common.print')}
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          onClick={() => {
                            void generateBarcode(product?.id)
                              .then((res) =>
                                setForm((current) => ({ ...current, barcode: res.barcode })),
                              )
                              .catch((err) => setError(getErrorMessage(err)));
                          }}
                        >
                          {t('products.generateBarcode')}
                        </Button>
                      </Stack>
                    ),
                  }}
                />
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
                <TextField
                  label={isService ? 'SAC code' : 'HSN code'}
                  value={form.hsnCode}
                  onChange={(e) => setForm((current) => ({ ...current, hsnCode: e.target.value }))}
                  error={hsnInvalid}
                  helperText={hsnInvalid ? 'HSN/SAC must be 4, 6, or 8 digits' : undefined}
                  sx={{ flex: 1 }}
                />
                <Button sx={{ mt: 1 }} onClick={() => setHsnOpen(true)}>
                  Find {hsnKind}
                </Button>
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start" data-testid="item-form-unit-row">
                <Box sx={{ flex: '1 1 160px', minWidth: 0, maxWidth: '100%' }}>
                  <HelpHint intent="unit-conversion-rate" slot="uom">
                    <TextField
                      select
                      label={t('products.unit')}
                      value={form.unitName}
                      onChange={(e) =>
                        setForm((current) => {
                          const unitName = e.target.value;
                          const collides = current.alternateUnitName === unitName;
                          return {
                            ...current,
                            unitName,
                            alternateUnitName: collides ? '' : current.alternateUnitName,
                            conversionRate: collides ? '1' : current.conversionRate,
                          };
                        })
                      }
                      disabled={locked}
                      helperText={
                        locked
                          ? 'Locked — this item already has stock movements. Use a stock adjustment to change quantities.'
                          : 'How you buy and sell this item (e.g. PCS, BOX, KG). Stock is counted in this unit and it becomes fixed after the first stock movement.'
                      }
                      sx={{ minWidth: 160, width: '100%' }}
                    >
                      {baseUnitOptions.map((unit) => (
                        <MenuItem key={unit} value={unit}>
                          {unitLabel(unit)}
                        </MenuItem>
                      ))}
                    </TextField>
                  </HelpHint>
                </Box>
                <Box sx={{ flex: '1 1 160px', minWidth: 0, maxWidth: '100%' }}>
                  <TextField
                    select
                    label="Alternate unit (optional)"
                    value={form.alternateUnitName}
                    onChange={(e) =>
                      setForm((current) => {
                        const alternateUnitName = e.target.value;
                        return {
                          ...current,
                          alternateUnitName,
                          conversionRate: alternateUnitName ? current.conversionRate : '1',
                        };
                      })
                    }
                    helperText="A second unit for billing — e.g. stock in Pieces (PCS) but sell by Carton (CTN). Stock is always kept in the base unit."
                    sx={{ minWidth: 160, width: '100%' }}
                  >
                    <MenuItem value="">None</MenuItem>
                    {alternateUnitOptions.map((unit) => (
                      <MenuItem key={unit} value={unit}>
                        {unitLabel(unit)}
                      </MenuItem>
                    ))}
                  </TextField>
                </Box>
                <Box sx={{ flex: '1 1 160px', minWidth: 0, maxWidth: '100%' }}>
                  <HelpHint intent="unit-conversion-rate" slot="conversion-rate">
                    <TextField
                      label="Conversion rate"
                      type="number"
                      value={form.conversionRate}
                      onChange={(e) => setForm((current) => ({ ...current, conversionRate: e.target.value }))}
                      disabled={!form.alternateUnitName}
                      error={conversionRateInvalid}
                      helperText={
                        conversionRateInvalid
                          ? 'Enter a number greater than 0'
                          : form.alternateUnitName
                            ? `1 ${unitLabel(form.alternateUnitName)} = this many ${unitLabel(form.unitName || 'PCS')}`
                            : 'Set an alternate unit first'
                      }
                      sx={{ minWidth: 160, width: '100%' }}
                    />
                  </HelpHint>
                </Box>
              </Stack>
              <TextField
                label="Description"
                multiline
                minRows={2}
                value={form.description}
                onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
              />
              <TextField
                select
                label={t('common.status')}
                value={form.status}
                onChange={(e) =>
                  setForm((current) => ({ ...current, status: e.target.value as 'ACTIVE' | 'INACTIVE' }))
                }
              >
                <MenuItem value="ACTIVE">ACTIVE</MenuItem>
                <MenuItem value="INACTIVE">INACTIVE</MenuItem>
              </TextField>
            </Stack>
          ) : null}

          {tab === 'stock' && !stockHidden ? (
            <Stack spacing={2}>
              {product ? (
                <Stack spacing={1}>
                  <Typography variant="subtitle2">Stock in existing godowns</Typography>
                  {(stockQuery.data ?? []).filter((row) => Number(row.product) === Number(product.id)).length ? (
                    (stockQuery.data ?? [])
                      .filter((row) => Number(row.product) === Number(product.id))
                      .map((row) => (
                        <Typography key={`${row.warehouse}-${row.batchNo ?? ''}`} variant="body2">
                          {row.warehouseName || 'Default godown'}
                          {row.batchNo ? ` · batch ${row.batchNo}` : ''}
                          {': '}
                          <strong>
                            {row.onHand} {unitLabel(form.unitName || 'PCS')}
                          </strong>
                        </Typography>
                      ))
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      No recorded stock in any godown yet. Opening stock below is only for a new item.
                    </Typography>
                  )}
                </Stack>
              ) : null}
              {locked ? (
                <Alert severity="info">
                  Tracking flags and the base unit are locked after the first stock movement.{' '}
                  {product ? (
                    <Button size="small" component={RouterLink} to={`/inventory/adjustments?product=${product.id}`}>
                      Adjust stock
                    </Button>
                  ) : null}
                </Alert>
              ) : null}
              <FormControlLabel
                control={
                  <Checkbox
                    checked={form.trackInventory}
                    onChange={(e) => setForm((current) => ({ ...current, trackInventory: e.target.checked }))}
                    disabled={locked}
                  />
                }
                label="Track inventory"
              />
              <Typography variant="subtitle2">Tracking mode</Typography>
              <RadioGroup
                row
                value={form.tracking}
                onChange={(e) => setForm((current) => ({ ...current, tracking: e.target.value as Tracking }))}
              >
                <FormControlLabel value="NONE" control={<Radio disabled={locked} />} label="None" />
                <FormControlLabel value="BATCH" control={<Radio disabled={locked} />} label="Batch / expiry" />
                <FormControlLabel value="SERIAL" control={<Radio disabled={locked} />} label="Serial" />
              </RadioGroup>
              {form.tracking === 'BATCH' && !product ? (
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2">Opening lots</Typography>
                  {form.lots.map((lot, index) => (
                    <Stack key={index} direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
                      <TextField
                        select
                        label="Godown"
                        value={lot.warehouseId || defaultWarehouseId}
                        onChange={(e) => patchLot(index, { warehouseId: e.target.value })}
                        sx={{ minWidth: 140 }}
                      >
                        {warehouses.map((warehouse) => (
                          <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                            {warehouse.name}
                          </MenuItem>
                        ))}
                      </TextField>
                      <TextField label="Qty" type="number" value={lot.quantity} onChange={(e) => patchLot(index, { quantity: e.target.value })} />
                      <TextField label="As of" type="date" InputLabelProps={{ shrink: true }} value={lot.asOf} onChange={(e) => patchLot(index, { asOf: e.target.value })} />
                      <TextField label="Batch no" value={lot.batchNo} onChange={(e) => patchLot(index, { batchNo: e.target.value })} />
                      <TextField label="Expiry" type="date" InputLabelProps={{ shrink: true }} value={lot.expiryDate} onChange={(e) => patchLot(index, { expiryDate: e.target.value })} />
                      <TextField label="Mfg" type="date" InputLabelProps={{ shrink: true }} value={lot.manufacturingDate} onChange={(e) => patchLot(index, { manufacturingDate: e.target.value })} />
                      <TextField label="Unit cost" type="number" value={lot.unitCost} onChange={(e) => patchLot(index, { unitCost: e.target.value })} />
                      <IconButton onClick={() => setForm((current) => ({ ...current, lots: current.lots.filter((_, i) => i !== index) }))} disabled={form.lots.length === 1}>
                        <DeleteOutlineIcon />
                      </IconButton>
                    </Stack>
                  ))}
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Button startIcon={<AddIcon />} onClick={() => setForm((current) => ({ ...current, lots: [...current.lots, emptyLot(defaultWarehouseId)] }))}>
                      Add godown / lot
                    </Button>
                    <Button
                      onClick={() =>
                        setForm((current) => {
                          const id = current.lots[0]?.warehouseId || defaultWarehouseId;
                          return { ...current, lots: current.lots.map((lot) => ({ ...lot, warehouseId: id })) };
                        })
                      }
                    >
                      Apply first godown to all rows
                    </Button>
                  </Stack>
                </Stack>
              ) : null}
              {form.tracking === 'SERIAL' && !product ? (
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2">Opening serials</Typography>
                  {form.serials.map((row, index) => (
                    <Stack key={index} direction={{ xs: 'column', md: 'row' }} spacing={1}>
                      <TextField
                        select
                        label="Godown"
                        value={row.warehouseId || defaultWarehouseId}
                        onChange={(e) => patchSerial(index, { warehouseId: e.target.value })}
                        sx={{ minWidth: 140 }}
                      >
                        {warehouses.map((warehouse) => (
                          <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                            {warehouse.name}
                          </MenuItem>
                        ))}
                      </TextField>
                      <TextField label="Serial no" value={row.serialNo} onChange={(e) => patchSerial(index, { serialNo: e.target.value })} sx={{ flex: 1 }} />
                      <TextField label="As of" type="date" InputLabelProps={{ shrink: true }} value={row.asOf} onChange={(e) => patchSerial(index, { asOf: e.target.value })} />
                      <TextField label="Unit cost" type="number" value={row.unitCost} onChange={(e) => patchSerial(index, { unitCost: e.target.value })} />
                      <IconButton onClick={() => setForm((current) => ({ ...current, serials: current.serials.filter((_, i) => i !== index) }))} disabled={form.serials.length === 1}>
                        <DeleteOutlineIcon />
                      </IconButton>
                    </Stack>
                  ))}
                  <TextField
                    label="Paste serials"
                    helperText="One serial per line, or comma-separated. Qty = number of serials."
                    value={serialPaste}
                    onChange={(e) => setSerialPaste(e.target.value)}
                    multiline
                    minRows={2}
                  />
                  <Stack direction="row" spacing={1}>
                    <Button
                      onClick={() => {
                        const values = serialPaste.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
                        if (!values.length) return;
                        setForm((current) => ({
                          ...current,
                          serials: values.map((serialNo) => ({
                            warehouseId: current.warehouseId || defaultWarehouseId,
                            serialNo,
                            asOf: todayIso(),
                            unitCost: '',
                          })),
                        }));
                        setSerialPaste('');
                      }}
                    >
                      Apply pasted serials
                    </Button>
                    <Button startIcon={<AddIcon />} onClick={() => setForm((current) => ({ ...current, serials: [...current.serials, emptySerial(defaultWarehouseId)] }))}>
                      Add serial
                    </Button>
                  </Stack>
                </Stack>
              ) : null}
              {form.tracking === 'NONE' && !product ? (
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField
                    label={t('products.openingStock')}
                    type="number"
                    value={form.openingStock}
                    onChange={(e) => setForm((current) => ({ ...current, openingStock: e.target.value }))}
                    helperText={t('products.openingStockHint')}
                  />
                  <TextField
                    select
                    label="Godown"
                    value={form.warehouseId || defaultWarehouseId}
                    onChange={(e) => setForm((current) => ({ ...current, warehouseId: e.target.value }))}
                    sx={{ minWidth: 180 }}
                  >
                    {warehouses.map((warehouse) => (
                      <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                        {warehouse.name}
                      </MenuItem>
                    ))}
                  </TextField>
                </Stack>
              ) : null}
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
                <TextField size="small" label="New godown name" value={godownName} onChange={(e) => setGodownName(e.target.value)} />
                <TextField size="small" label="Code" value={godownCode} onChange={(e) => setGodownCode(e.target.value)} />
                <Button disabled={!godownName.trim() || createGodown.isPending} onClick={() => createGodown.mutate()}>
                  + New godown
                </Button>
              </Stack>
              <TextField
                label={t('products.reorderLevel')}
                type="number"
                value={form.reorderLevel}
                onChange={(e) => setForm((current) => ({ ...current, reorderLevel: e.target.value }))}
                helperText={t('products.reorderLevelHint')}
              />
            </Stack>
          ) : null}

          {tab === 'pricing' ? (
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label={t('products.sellingPrice')}
                  type="number"
                  value={form.sellingPrice}
                  onChange={(e) => setForm((current) => ({ ...current, sellingPrice: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  select
                  label="Sales tax"
                  value={form.sellingTaxInclusive ? 'IN' : 'EX'}
                  onChange={(e) => setForm((current) => ({ ...current, sellingTaxInclusive: e.target.value === 'IN' }))}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="EX">Without tax</MenuItem>
                  <MenuItem value="IN">With tax</MenuItem>
                </TextField>
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label={t('products.purchasePrice')}
                  type="number"
                  value={form.purchasePrice}
                  onChange={(e) => setForm((current) => ({ ...current, purchasePrice: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  select
                  label="Purchase tax"
                  value={form.purchaseTaxInclusive ? 'IN' : 'EX'}
                  onChange={(e) => setForm((current) => ({ ...current, purchaseTaxInclusive: e.target.value === 'IN' }))}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="EX">Without tax</MenuItem>
                  <MenuItem value="IN">With tax</MenuItem>
                </TextField>
              </Stack>
              <TextField label="MRP" type="number" value={form.mrp} onChange={(e) => setForm((current) => ({ ...current, mrp: e.target.value }))} />
              <TextField
                label="Disc. on MRP %"
                value={discOnMrp}
                InputProps={{ readOnly: true }}
                helperText="(MRP − selling price) / MRP. Not a line discount."
              />
              <TextField
                label="Wholesale price"
                type="number"
                value={form.wholesalePrice}
                onChange={(e) => setForm((current) => ({ ...current, wholesalePrice: e.target.value }))}
              />
              <TextField select label="GST rate" value={form.gstRate} onChange={(e) => setForm((current) => ({ ...current, gstRate: e.target.value }))}>
                {/* F3-012: if an HSN picker (or a legacy product) set a rate not
                    in the standard slabs, still render it as an option so the
                    field doesn't go blank. */}
                {(GST_RATE_OPTIONS.some((r) => r.value === form.gstRate)
                  ? GST_RATE_OPTIONS
                  : [...GST_RATE_OPTIONS, { value: form.gstRate, label: `${form.gstRate}%` }]
                ).map((rate) => (
                  <MenuItem key={rate.value} value={rate.value}>
                    {rate.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Default discount %"
                type="number"
                value={form.defaultDiscountPercent}
                onChange={(e) => setForm((current) => ({ ...current, defaultDiscountPercent: e.target.value }))}
              />
            </Stack>
          ) : null}

          {tab === 'custom' ? (
            <Stack spacing={2}>
              <Alert severity="info">
                Extra keys are defined in{' '}
                <Button size="small" component={RouterLink} to="/settings/items">
                  Item Settings
                </Button>
                .
              </Alert>
              {customDefs.length === 0 ? (
                <Typography color="text.secondary">{t('customFields.emptyItemTab')}</Typography>
              ) : (
                customDefs.map((def) => {
                  const stored = form.customValues[def.key] ?? '';
                  if (def.type === 'list') {
                    const options = [...(def.options ?? [])];
                    if (stored && !options.some((item) => item.toLowerCase() === stored.toLowerCase())) {
                      options.push(stored);
                    }
                    return (
                      <TextField
                        key={def.key}
                        select
                        label={def.label}
                        value={stored}
                        onChange={(e) =>
                          setForm((current) => ({
                            ...current,
                            customValues: { ...current.customValues, [def.key]: e.target.value },
                          }))
                        }
                      >
                        <MenuItem value="">—</MenuItem>
                        {options.map((option) => (
                          <MenuItem key={option} value={option}>
                            {option}
                            {!(def.options ?? []).some((item) => item.toLowerCase() === option.toLowerCase())
                              ? ` (${t('customFields.removedOption')})`
                              : ''}
                          </MenuItem>
                        ))}
                      </TextField>
                    );
                  }
                  return (
                    <TextField
                      key={def.key}
                      label={def.label}
                      value={stored}
                      onChange={(e) =>
                        setForm((current) => ({
                          ...current,
                          customValues: { ...current.customValues, [def.key]: e.target.value },
                        }))
                      }
                    />
                  );
                })
              )}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          {!product ? (
            <Button disabled={!canSave || save.isPending} onClick={() => save.mutate(true)}>
              Save & New
            </Button>
          ) : null}
          <Tooltip
            title={
              !form.name.trim()
                ? 'Enter item name to save'
                : !form.sku.trim()
                  ? 'Enter item code (SKU) to save'
                  : hsnInvalid
                  ? 'Enter a valid HSN/SAC code (4, 6, or 8 digits)'
                  : conversionRateInvalid
                    ? 'Conversion rate must be greater than 0'
                    : ''
            }
          >
            <span>
              <Button variant="contained" disabled={!canSave || save.isPending} onClick={() => save.mutate(false)}>
                Save item
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>

      <Dialog open={hsnOpen} onClose={() => setHsnOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Find {hsnKind}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            label="Search code or description"
            value={hsnQuery}
            onChange={(e) => setHsnQuery(e.target.value)}
            sx={{ mt: 1, mb: 2 }}
          />
          <Stack spacing={1}>
            {(hsnSearch.data?.items ?? []).map((row) => (
              <Button
                key={row.code}
                onClick={() => {
                  const rate = row.gstRate ?? (row as { gst_rate?: string }).gst_rate;
                  setForm((current) => ({
                    ...current,
                    hsnCode: row.code,
                    gstRate: rate ? String(rate) : current.gstRate,
                  }));
                  setHsnOpen(false);
                }}
                sx={{ justifyContent: 'flex-start', textTransform: 'none', display: 'block' }}
              >
                <Typography variant="body2" fontWeight={600}>
                  {row.code} · {row.kind}
                  {row.gstRate ? ` · GST ${row.gstRate}%` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  {row.description}
                </Typography>
              </Button>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHsnOpen(false)}>{t('common.cancel')}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
