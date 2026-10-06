import { useMemo, useState } from 'react';
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
import Paper from '@mui/material/Paper';
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
import { t, useLocale } from '@/i18n';
import { todayIso } from '@/components/billing';
import type { Product } from '@/types/domain';
import { isValidHsnSac, normalizeGstRate, GST_RATE_OPTIONS } from '@/utils/gst';
import { STANDARD_UNITS, formatUnitLabel } from '@/constants/unitLabels';
import { toNumber } from '@/utils/money';
import { activeCustomFieldDefs, type ItemCustomFieldDef } from './itemCustomFieldDefaults';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { trackShopFloor } from '@/lib/telemetry';

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
  gstSupplyForm: string;
  cessRate: string;
  cessAmount: string;
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
  regulatedCategory: 'NONE' | 'DRUG' | 'FOOD';
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
    gstSupplyForm: product?.gstSupplyForm ?? '',
    cessRate: String(product?.cessRate ?? '0'),
    cessAmount: String(product?.cessAmount ?? '0'),
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
    regulatedCategory: product?.regulatedCategory ?? 'NONE',
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
  onSaved: (keepOpen: boolean, rateNotice?: string) => void;
}

export function ItemFormDialog({ open, product, existingNames, onClose, onSaved }: Props) {
  useLocale();
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
  const [showStockOnCreate, setShowStockOnCreate] = useState(false);
  const [form, setForm] = useState<FormState>(() => buildForm(product, defaultWarehouseId));
  // F3-015: JSON-diff dirty tracking — this form isn't react-hook-form.
  const [baselineFormJson, setBaselineFormJson] = useState('');
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

  // The base unit stays frozen once movements exist -- past movement
  // quantities are permanently "in whatever unit was active then" and can
  // never be rewritten. But once on-hand + reserved stock is back to zero
  // everywhere, there's no ambiguous quantity left to reinterpret, so the
  // backend allows starting a new chapter under a different unit. Stay
  // conservative (locked) while the stock totals are still loading.
  const totalStock = useMemo(() => {
    if (!product) return 0;
    return (stockQuery.data ?? [])
      .filter((row) => Number(row.product) === Number(product.id))
      .reduce((sum, row) => sum + toNumber(row.onHand) + toNumber(row.reserved), 0);
  }, [stockQuery.data, product]);
  const unitLocked = locked && (stockQuery.isLoading || totalStock !== 0);

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
  }, [form.unitName, product, unitsQuery.data]);
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
  }, [form.unitName, form.alternateUnitName, product, unitsQuery.data]);
  const unitLabel = (code: string) => {
    const match = (unitsQuery.data ?? []).find(
      (unit) => (unit.shortName || unit.uqcCode || '').toUpperCase() === code.toUpperCase(),
    );
    return formatUnitLabel(code, match?.name);
  };

  // Reset only when the dialog opens or the edited product changes — not when
  // company defs / godowns finish loading, which would wipe in-progress edits.
  const resetKey = open ? String(product?.id ?? 'new') : null;
  const [seenResetKey, setSeenResetKey] = useState<string | null>(null);
  const resettingForm = seenResetKey !== resetKey && resetKey !== null;
  if (seenResetKey !== resetKey) {
    setSeenResetKey(resetKey);
    if (resetKey !== null) {
      setTab('basic');
      setShowStockOnCreate(false);
      setError(null);
      const fresh = buildForm(product, defaultWarehouseId, customDefs);
      setForm(fresh);
      // F3-015: snapshot this as the "clean" baseline for the unsaved-changes
      // guard below.
      setBaselineFormJson(JSON.stringify(fresh));
    }
  }

  // Fill an empty godown when the default arrives or the dialog opens. Keyed on the
  // default itself, so a godown the user clears on purpose is not filled again.
  const warehouseKey = open && defaultWarehouseId ? String(defaultWarehouseId) : null;
  const [seenWarehouseKey, setSeenWarehouseKey] = useState<string | null>(null);
  if (seenWarehouseKey !== warehouseKey) {
    setSeenWarehouseKey(warehouseKey);
    if (warehouseKey !== null) {
      setForm((current) => {
        if (current.warehouseId) return current;
        return {
          ...current,
          warehouseId: defaultWarehouseId,
          lots: current.lots.map((lot) => ({ ...lot, warehouseId: lot.warehouseId || defaultWarehouseId })),
          serials: current.serials.map((row) => ({ ...row, warehouseId: row.warehouseId || defaultWarehouseId })),
        };
      });
    }
  }

  // Add a value slot for any custom field the form does not have yet. Stops once every key exists.
  // Must not run in the same render as the product reset above: a plain setForm({...form})
  // would replace that reset with the previous empty form and drop the item name.
  if (!resettingForm && open && customDefs.some((def) => !(def.key in form.customValues))) {
    setForm((current) => {
      if (customDefs.every((def) => def.key in current.customValues)) return current;
      const customValues = { ...current.customValues };
      const stored = product?.customFields ?? {};
      for (const def of customDefs) {
        if (def.key in customValues) continue;
        customValues[def.key] = String(stored[def.key] ?? stored[def.label] ?? '');
      }
      return { ...current, customValues };
    });
  }

  if (tab === 'custom' && customDefs.length === 0) setTab('basic');

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
  const isRegularDealer =
    (companyQuery.data?.registrationType ?? user?.company?.registrationType ?? 'REGULAR') === 'REGULAR';

  const validateForm = (): { valid: boolean; tab?: TabKey; fieldId?: string; message?: string } => {
    if (!form.name.trim()) {
      return { valid: false, fieldId: 'item-form-name', message: 'Item name is required.' };
    }
    if (isNaN(Number(form.sellingPrice)) || Number(form.sellingPrice) < 0) {
      return { valid: false, fieldId: 'item-form-selling-price', message: 'Selling price cannot be negative.' };
    }
    if (isNaN(Number(form.purchasePrice)) || Number(form.purchasePrice) < 0) {
      return { valid: false, fieldId: 'item-form-purchase-price', message: 'Purchase price cannot be negative.' };
    }
    if (hsnInvalid) {
      return {
        valid: false,
        tab: isRegularDealer ? undefined : 'basic',
        fieldId: 'item-form-hsn',
        message: 'HSN/SAC must be 4, 6, or 8 digits',
      };
    }
    if (!form.sku.trim()) {
      return { valid: false, tab: 'basic', fieldId: 'item-form-sku', message: 'Item code is required.' };
    }
    if (conversionRateInvalid) {
      return {
        valid: false,
        tab: 'basic',
        fieldId: 'item-form-conversion-rate',
        message: 'Conversion rate must be greater than 0',
      };
    }
    if (isNaN(Number(form.reorderLevel)) || Number(form.reorderLevel) < 0) {
      return { valid: false, tab: 'stock', fieldId: 'item-form-reorder-level', message: 'Reorder level cannot be negative' };
    }
    if (isNaN(Number(form.wholesalePrice)) || Number(form.wholesalePrice) < 0) {
      return { valid: false, tab: 'pricing', fieldId: 'item-form-wholesale-price', message: 'Wholesale price cannot be negative' };
    }
    if (isNaN(Number(form.mrp)) || Number(form.mrp) < 0) {
      return { valid: false, tab: 'pricing', fieldId: 'item-form-mrp', message: 'MRP cannot be negative' };
    }
    if (isNaN(Number(form.cessRate)) || Number(form.cessRate) < 0) {
      return { valid: false, tab: 'pricing', fieldId: 'item-form-cess-rate', message: 'Cess rate cannot be negative' };
    }
    if (isNaN(Number(form.cessAmount)) || Number(form.cessAmount) < 0) {
      return { valid: false, tab: 'pricing', fieldId: 'item-form-cess-amount', message: 'Cess amount cannot be negative' };
    }
    const disc = Number(form.defaultDiscountPercent);
    if (isNaN(disc) || disc < 0 || disc > 100) {
      return { valid: false, tab: 'pricing', fieldId: 'item-form-discount', message: 'Default discount must be between 0 and 100%' };
    }
    if (!customValuesReady) {
      return { valid: false, tab: 'custom', message: 'Please fill all required custom fields' };
    }
    return { valid: true };
  };

  const validationResult = validateForm();
  const canSave = validationResult.valid && !companyQuery.isLoading;
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
        gstSupplyForm: form.gstSupplyForm,
        cessRate: Number(form.cessRate) || 0,
        cessAmount: Number(form.cessAmount) || 0,
        purchasePrice: Number(form.purchasePrice),
        sellingPrice: Number(form.sellingPrice),
        mrp: Number(form.mrp) || 0,
        wholesalePrice: Number(form.wholesalePrice) || 0,
        reorderLevel: Number(form.reorderLevel),
        productType: form.productType,
        trackInventory: !isService && form.trackInventory,
        trackBatch: !isService && form.tracking === 'BATCH',
        trackSerial: !isService && form.tracking === 'SERIAL',
        regulatedCategory: form.regulatedCategory,
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
      const rateNotice = String((saved as { gstRateNotice?: string }).gstRateNotice || '');
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
      return { keepOpen, rateNotice };
    },
    onSuccess: ({ keepOpen, rateNotice }) => {
      void qc.invalidateQueries({ queryKey: ['products'] });
      void qc.invalidateQueries({ queryKey: ['products-count'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
      onSaved(keepOpen, rateNotice);
      if (keepOpen) {
        // F3-015: reset the dirty baseline along with the form — otherwise the
        // fresh blank form reads as "dirty" against the just-saved product's data.
        const fresh = buildForm(null, defaultWarehouseId, customDefs);
        setForm(fresh);
        setBaselineFormJson(JSON.stringify(fresh));
        setTab('basic');
        setShowStockOnCreate(false);
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const handleSave = (keepOpen: boolean) => {
    const result = validateForm();
    if (!result.valid) {
      trackShopFloor('form_validation_failed', { feature: 'form' });
      if (result.tab && result.tab !== tab) {
        if (result.tab === 'stock') setShowStockOnCreate(true);
        setTab(result.tab);
      }
      setError(result.message || 'Please check highlighted fields.');
      if (result.fieldId) {
        setTimeout(() => {
          const el = document.getElementById(result.fieldId!);
          el?.focus();
        }, 50);
      }
      return;
    }
    setError(null);
    save.mutate(keepOpen);
  };

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

  const dirty = open && JSON.stringify(form) !== baselineFormJson;
  // F3-011: UnsavedChangesGuard only covers browser nav/reload/tab-close --
  // the Dialog's own close triggers (backdrop click, Escape, Cancel button)
  // bypassed it entirely and discarded a dirty multi-tab form with no guard.
  const handleClose = () => {
    if (dirty && !window.confirm(t('inventory.confirmDiscardItemChanges'))) return;
    onClose();
  };

  return (
    <>
      <UnsavedChangesGuard when={dirty} />
      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
        <DialogTitle>
          {product ? t('common.edit') : t('empty.createItem')}
        </DialogTitle>
        <DialogContent>
          {error ? (
            <HelpErrorAlert message={error} sx={{ mb: 2 }} />
          ) : null}
          {duplicateName ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              An item with this name already exists — check SKU when billing. Duplicate names are allowed.
            </Alert>
          ) : null}

          <Paper variant="outlined" sx={{ p: 2, mb: 2.5, bgcolor: 'background.default' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.secondary', mb: 1.5, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {t('sweep2.coreEssentials')}
            </Typography>
            <Stack spacing={2}>
              <TextField
                id="item-form-name"
                label={t('common.name')}
                required
                value={form.name}
                onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
                helperText={duplicateName ? 'An item with this name already exists — check SKU when billing' : undefined}
                fullWidth
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  id="item-form-selling-price"
                  label={t('products.sellingPrice')}
                  type="number"
                  value={form.sellingPrice}
                  onChange={(e) => setForm((current) => ({ ...current, sellingPrice: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  id="item-form-purchase-price"
                  label={t('products.purchasePrice')}
                  type="number"
                  value={form.purchasePrice}
                  onChange={(e) => setForm((current) => ({ ...current, purchasePrice: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  id="item-form-gst-rate"
                  select
                  label={t('items.gstRate')}
                  value={form.gstRate}
                  onChange={(e) => setForm((current) => ({ ...current, gstRate: e.target.value }))}
                  sx={{ flex: 1 }}
                >
                  {(GST_RATE_OPTIONS.some((r) => r.value === form.gstRate)
                    ? GST_RATE_OPTIONS
                    : [...GST_RATE_OPTIONS, { value: form.gstRate, label: `${form.gstRate}%` }]
                  ).map((rate) => (
                    <MenuItem key={rate.value} value={rate.value}>
                      {rate.label}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
                <Box sx={{ flex: 1, minWidth: 160, width: '100%' }}>
                  <HelpHint intent="unit-conversion-rate" slot="uom">
                    <TextField
                      id="item-form-unit"
                      select
                      label={t('products.unit')}
                      value={form.unitName}
                      onChange={(e) =>
                        setForm((current) => {
                          const unitName = e.target.value;
                          const changed = current.unitName !== unitName;
                          return {
                            ...current,
                            unitName,
                            alternateUnitName: changed ? '' : current.alternateUnitName,
                            conversionRate: changed ? '1' : current.conversionRate,
                          };
                        })
                      }
                      disabled={unitLocked}
                      helperText={
                        unitLocked
                          ? 'Locked — this item has stock on hand. Bring stock to zero (Stock Adjustment) to change the unit.'
                          : locked
                            ? 'Stock for this item is zero, so the unit can be changed.'
                            : undefined
                      }
                      fullWidth
                    >
                      {baseUnitOptions.map((unit) => (
                        <MenuItem key={unit} value={unit}>
                          {unitLabel(unit)}
                        </MenuItem>
                      ))}
                    </TextField>
                  </HelpHint>
                </Box>
                {isRegularDealer ? (
                  <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ flex: 1, width: '100%' }}>
                    <TextField
                      id="item-form-hsn"
                      label={isService ? 'SAC code' : 'HSN code'}
                      value={form.hsnCode}
                      onChange={(e) => setForm((current) => ({ ...current, hsnCode: e.target.value }))}
                      error={hsnInvalid}
                      helperText={hsnInvalid ? 'HSN/SAC must be 4, 6, or 8 digits' : undefined}
                      fullWidth
                    />
                    <Button sx={{ mt: 1, whiteSpace: 'nowrap' }} onClick={() => setHsnOpen(true)}>
                      Find {hsnKind}
                    </Button>
                  </Stack>
                ) : null}
              </Stack>
            </Stack>
          </Paper>

          <Tabs value={tab} onChange={(_, value: TabKey) => setTab(value)} sx={{ mb: 2 }} variant="scrollable">
            <Tab value="basic" label={t('items.basicDetails')} />
            {product || showStockOnCreate ? (
              <Tab value="stock" label={t('items.stockDetails')} disabled={isService} />
            ) : null}
            <Tab value="pricing" label={t('items.pricingDetails')} />
            {customDefs.length ? <Tab value="custom" label={t('items.customFields')} /> : null}
          </Tabs>
          {!product && !stockHidden && !showStockOnCreate ? (
            <Stack spacing={0.5} sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                {t('products.openingStockAfterSave')}
              </Typography>
              <Box>
                <Button variant="outlined" onClick={() => { setShowStockOnCreate(true); setTab('stock'); }}>
                  {t('products.addOpeningStock')}
                </Button>
              </Box>
            </Stack>
          ) : null}

          {tab === 'basic' ? (
            <Stack spacing={2}>
              <TextField
                select
                label={t('items.itemType')}
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
                <MenuItem value="GOODS">{t('items.goods')}</MenuItem>
                <MenuItem value="SERVICE">{t('items.service')}</MenuItem>
              </TextField>
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
                  id="item-form-sku"
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
              {!isRegularDealer ? (
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
                  <TextField
                    id="item-form-hsn"
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
              ) : null}
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start" data-testid="item-form-unit-row">
                <Box sx={{ flex: '1 1 160px', minWidth: 0, maxWidth: '100%' }}>
                  <TextField
                    select
                    label={t('items.alternateUnit')}
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
                    helperText={t('sweep.altUnitHelp')}
                    sx={{ minWidth: 160, width: '100%' }}
                  >
                    <MenuItem value="">{t('items.none')}</MenuItem>
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
                      id="item-form-conversion-rate"
                      label={t('items.conversionRate')}
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
                label={t('items.description')}
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
                <MenuItem value="ACTIVE">{t('items.active')}</MenuItem>
                <MenuItem value="INACTIVE">{t('items.inactive')}</MenuItem>
              </TextField>
            </Stack>
          ) : null}

          {tab === 'stock' && !stockHidden ? (
            <Stack spacing={2}>
              {product ? (
                <Stack spacing={1}>
                  <Typography variant="subtitle2">{t('items.stockInGodowns')}</Typography>
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
                  Item type and tracking flags are locked after the first stock movement.{' '}
                  {unitLocked
                    ? 'The base unit is also locked while stock is on hand — bring it to zero to change the unit.'
                    : 'Stock is zero, so the base unit (Basic details tab) can still be changed.'}{' '}
                  {product ? (
                    <Button size="small" component={RouterLink} to={`/inventory/adjustments?product=${product.id}`}>
                      {t('sweep2.adjustStock')}
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
                label={t('items.trackInventory')}
              />
              <Typography variant="subtitle2">{t('items.trackingMode')}</Typography>
              <RadioGroup
                row
                value={form.tracking}
                onChange={(e) => setForm((current) => ({ ...current, tracking: e.target.value as Tracking }))}
              >
                <FormControlLabel value="NONE" control={<Radio disabled={locked} />} label={t('items.none')} />
                <FormControlLabel value="BATCH" control={<Radio disabled={locked} />} label={t('items.batchExpiry')} />
                <FormControlLabel value="SERIAL" control={<Radio disabled={locked} />} label={t('items.serial')} />
              </RadioGroup>
              <TextField
                select
                label={t('items.regulatedCategory')}
                helperText={t('items.regulatedHint')}
                value={form.regulatedCategory}
                onChange={(e) =>
                  setForm((current) => ({
                    ...current,
                    regulatedCategory: e.target.value as FormState['regulatedCategory'],
                  }))
                }
              >
                <MenuItem value="NONE">{t('items.notRegulated')}</MenuItem>
                <MenuItem value="DRUG">{t('items.drug')}</MenuItem>
                <MenuItem value="FOOD">{t('items.food')}</MenuItem>
              </TextField>
              {form.tracking === 'BATCH' && !product ? (
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2">{t('items.openingLots')}</Typography>
                  {form.lots.map((lot, index) => (
                    <Stack key={index} direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
                      <TextField
                        select
                        label={t('items.godown')}
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
                      <TextField label={t('items.qty')} type="number" value={lot.quantity} onChange={(e) => patchLot(index, { quantity: e.target.value })} />
                      <TextField label={t('items.asOf')} type="date" InputLabelProps={{ shrink: true }} value={lot.asOf} onChange={(e) => patchLot(index, { asOf: e.target.value })} />
                      <TextField label={t('items.batchNo')} value={lot.batchNo} onChange={(e) => patchLot(index, { batchNo: e.target.value })} />
                      <TextField label={t('items.expiry')} type="date" InputLabelProps={{ shrink: true }} value={lot.expiryDate} onChange={(e) => patchLot(index, { expiryDate: e.target.value })} />
                      <TextField label={t('items.mfg')} type="date" InputLabelProps={{ shrink: true }} value={lot.manufacturingDate} onChange={(e) => patchLot(index, { manufacturingDate: e.target.value })} />
                      <TextField label={t('items.unitCost')} type="number" value={lot.unitCost} onChange={(e) => patchLot(index, { unitCost: e.target.value })} />
                      <IconButton onClick={() => setForm((current) => ({ ...current, lots: current.lots.filter((_, i) => i !== index) }))} disabled={form.lots.length === 1}>
                        <DeleteOutlineIcon />
                      </IconButton>
                    </Stack>
                  ))}
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Button startIcon={<AddIcon />} onClick={() => setForm((current) => ({ ...current, lots: [...current.lots, emptyLot(defaultWarehouseId)] }))}>
                      {t('sweep2.addGodownLot')}
                    </Button>
                    <Button
                      onClick={() =>
                        setForm((current) => {
                          const id = current.lots[0]?.warehouseId || defaultWarehouseId;
                          return { ...current, lots: current.lots.map((lot) => ({ ...lot, warehouseId: id })) };
                        })
                      }
                    >
                      {t('sweep2.applyFirstGodown')}
                    </Button>
                  </Stack>
                </Stack>
              ) : null}
              {form.tracking === 'SERIAL' && !product ? (
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2">{t('items.openingSerials')}</Typography>
                  {form.serials.map((row, index) => (
                    <Stack key={index} direction={{ xs: 'column', md: 'row' }} spacing={1}>
                      <TextField
                        select
                        label={t('items.godown')}
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
                      <TextField label={t('items.serialNo')} value={row.serialNo} onChange={(e) => patchSerial(index, { serialNo: e.target.value })} sx={{ flex: 1 }} />
                      <TextField label={t('items.asOf')} type="date" InputLabelProps={{ shrink: true }} value={row.asOf} onChange={(e) => patchSerial(index, { asOf: e.target.value })} />
                      <TextField label={t('items.unitCost')} type="number" value={row.unitCost} onChange={(e) => patchSerial(index, { unitCost: e.target.value })} />
                      <IconButton onClick={() => setForm((current) => ({ ...current, serials: current.serials.filter((_, i) => i !== index) }))} disabled={form.serials.length === 1}>
                        <DeleteOutlineIcon />
                      </IconButton>
                    </Stack>
                  ))}
                  <TextField
                    label={t('items.pasteSerials')}
                    helperText={t('sweep.serialsHelp')}
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
                      {t('sweep2.applyPastedSerials')}
                    </Button>
                    <Button startIcon={<AddIcon />} onClick={() => setForm((current) => ({ ...current, serials: [...current.serials, emptySerial(defaultWarehouseId)] }))}>
                      {t('sweep2.addSerial')}
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
                    label={t('items.godown')}
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
                <TextField size="small" label={t('items.newGodownName')} value={godownName} onChange={(e) => setGodownName(e.target.value)} />
                <TextField size="small" label={t('items.code')} value={godownCode} onChange={(e) => setGodownCode(e.target.value)} />
                <Button disabled={!godownName.trim() || createGodown.isPending} onClick={() => createGodown.mutate()}>
                  + New godown
                </Button>
              </Stack>
              <TextField
                id="item-form-reorder-level"
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
                  select
                  label={t('items.salesTax')}
                  value={form.sellingTaxInclusive ? 'IN' : 'EX'}
                  onChange={(e) => setForm((current) => ({ ...current, sellingTaxInclusive: e.target.value === 'IN' }))}
                  sx={{ flex: 1 }}
                >
                  <MenuItem value="EX">{t('items.withoutTax')}</MenuItem>
                  <MenuItem value="IN">{t('items.withTax')}</MenuItem>
                </TextField>
                <TextField
                  select
                  label={t('items.purchaseTax')}
                  value={form.purchaseTaxInclusive ? 'IN' : 'EX'}
                  onChange={(e) => setForm((current) => ({ ...current, purchaseTaxInclusive: e.target.value === 'IN' }))}
                  sx={{ flex: 1 }}
                >
                  <MenuItem value="EX">{t('items.withoutTax')}</MenuItem>
                  <MenuItem value="IN">{t('items.withTax')}</MenuItem>
                </TextField>
              </Stack>
              <TextField id="item-form-mrp" label={t('items.mrp')} type="number" value={form.mrp} onChange={(e) => setForm((current) => ({ ...current, mrp: e.target.value }))} />
              <TextField
                label={t('items.discOnMrp')}
                value={discOnMrp}
                InputProps={{ readOnly: true }}
                helperText="(MRP − selling price) / MRP. Not a line discount."
              />
              <TextField
                id="item-form-wholesale-price"
                label={t('items.wholesalePrice')}
                type="number"
                value={form.wholesalePrice}
                onChange={(e) => setForm((current) => ({ ...current, wholesalePrice: e.target.value }))}
              />
              <TextField
                select
                label={t('billing.gstSupplyForm')}
                value={form.gstSupplyForm}
                onChange={(e) => setForm((current) => ({ ...current, gstSupplyForm: e.target.value }))}
              >
                <MenuItem value="">{t('billing.gstSupplyUnset')}</MenuItem>
                <MenuItem value="UNBRANDED">{t('billing.gstSupplyUnbranded')}</MenuItem>
                <MenuItem value="BRANDED_PREPACKED">{t('billing.gstSupplyBranded')}</MenuItem>
              </TextField>
              <TextField
                id="item-form-cess-rate"
                label={t('items.cessRate')}
                type="number"
                value={form.cessRate}
                onChange={(e) => setForm((current) => ({ ...current, cessRate: e.target.value }))}
                helperText={t('sweep.cessRateHelp')}
                inputProps={{ min: 0, step: '0.01' }}
              />
              <TextField
                id="item-form-cess-amount"
                label={t('items.cessPerUnit')}
                type="number"
                value={form.cessAmount}
                onChange={(e) => setForm((current) => ({ ...current, cessAmount: e.target.value }))}
                helperText={t('sweep.cessAmountHelp')}
                inputProps={{ min: 0, step: '0.01' }}
              />
              <TextField
                id="item-form-discount"
                label={t('items.defaultDiscount')}
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
                  {t('sweep2.itemSettings')}
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
          <Button onClick={handleClose}>{t('common.cancel')}</Button>
          {!product ? (
            <Button disabled={save.isPending} onClick={() => handleSave(true)}>
              {t('sweep2.saveAndNew')}
            </Button>
          ) : null}
          <Tooltip
            title={
              !canSave && validationResult.message
                ? validationResult.message
                : ''
            }
          >
            <span>
              <Button variant="contained" disabled={save.isPending} onClick={() => handleSave(false)}>
                {t('sweep2.saveItem')}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>

      <Dialog open={hsnOpen} onClose={() => setHsnOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('items.findCode', { kind: hsnKind })}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            label={t('items.searchCode')}
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
