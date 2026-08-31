import type { ItemCustomFieldDef } from '@/types/domain';

export type { ItemCustomFieldDef };

export const DEFAULT_ITEM_CUSTOM_FIELD_DEFS: ItemCustomFieldDef[] = [];

export function normalizeCustomFieldDefs(rows?: ItemCustomFieldDef[] | null): ItemCustomFieldDef[] {
  const cleaned: ItemCustomFieldDef[] = [];
  const seen = new Set<string>();
  for (const row of rows ?? []) {
    const key = (row.key || '').trim();
    const label = (row.label || '').trim();
    if (!key || !label || seen.has(key.toLowerCase())) continue;
    seen.add(key.toLowerCase());
    const type = row.type === 'list' ? 'list' : 'text';
    const options: string[] = [];
    const optionSeen = new Set<string>();
    if (type === 'list') {
      for (const item of row.options ?? []) {
        const text = String(item || '').trim();
        if (!text || optionSeen.has(text.toLowerCase())) continue;
        optionSeen.add(text.toLowerCase());
        options.push(text);
      }
    }
    cleaned.push({
      key,
      label,
      type,
      active: row.active !== false,
      options,
    });
  }
  return [...cleaned.filter((row) => row.active), ...cleaned.filter((row) => !row.active)];
}

export function activeCustomFieldDefs(rows?: ItemCustomFieldDef[] | null): ItemCustomFieldDef[] {
  return normalizeCustomFieldDefs(rows).filter((row) => row.active !== false);
}

export function suggestCustomFieldKey(label: string): string {
  const parts = label.trim().split(/[\s_-]+/).filter(Boolean);
  if (!parts.length) return '';
  const clean = (value: string) => value.replace(/[^A-Za-z0-9]/g, '');
  const first = clean(parts[0]);
  if (!first) return '';
  let key = first.toLowerCase();
  if (!/^[a-z]/i.test(key)) key = `f${key}`;
  for (const part of parts.slice(1)) {
    const chunk = clean(part);
    if (!chunk) continue;
    key += chunk.charAt(0).toUpperCase() + chunk.slice(1).toLowerCase();
  }
  return key.slice(0, 64);
}

export function filledCustomFieldPreview(
  values: Record<string, string> | undefined,
  defs: ItemCustomFieldDef[],
  max = 2,
): string {
  const parts: string[] = [];
  for (const def of defs) {
    const value = String(values?.[def.key] ?? '').trim();
    if (!value) continue;
    parts.push(`${def.label}: ${value}`);
    if (parts.length >= max) break;
  }
  return parts.join(' · ');
}

export function customFieldCell(values: Record<string, string> | undefined, key: string): string {
  return String(values?.[key] ?? '').trim();
}

export const CUSTOM_FIELD_KEY_RE = /^[A-Za-z][A-Za-z0-9]*$/;
export const MAX_ACTIVE_CUSTOM_FIELDS = 20;
export const MAX_LIST_OPTIONS = 50;
export const MAX_KEY_LEN = 64;
export const MAX_LABEL_LEN = 80;
export const MAX_OPTION_LEN = 80;

/** Matches backend masters.custom_fields.normalize_header. */
export function normalizeHeader(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, ' ')
    .trim();
}

// Keep in sync with backend PRODUCTS_ITEM_COLUMNS + MASTER_COLUMN_ALIASES + reserved extras.
const RESERVED_ITEM_HEADERS = [
  'name', 'sku', 'barcode', 'hsn_code', 'description', 'category', 'unit',
  'alternate_unit', 'conversion_rate', 'gst_rate', 'purchase_price',
  'purchase_tax_inclusive', 'selling_price', 'selling_tax_inclusive', 'mrp',
  'wholesale_price', 'default_discount_percent', 'reorder_level', 'product_type',
  'track_inventory', 'track_batch', 'track_serial', 'godown', 'opening_stock',
  'unit_cost', 'batch_no', 'expiry_date', 'manufacturing_date', 'as_of', 'serial_no',
  'id', 'status', 'created_at', 'updated_at', 'brand', 'category_name', 'hsn',
  'quantity', 'custom_fields', 'customfields',
  'product name', 'item', 'item name', 'item name*', 'item description', 'product',
  'item code', 'product code', 'pcode', 'code', 'itemcode',
  'ean', 'upc', 'bar code', 'hsn code', 'hsn/sac', 'hsn_sac',
  'item desc', 'product description', 'gst', 'gst%', 'tax_rate', 'tax%', 'gst rate',
  'gst tax rate(%)', 'gst tax rate', 'purchase price', 'cost', 'buy price', 'purchase rate',
  'selling price', 'sale price', 'sell price', 'rate', 'sales price',
  'wholesale price', 'wholesale rate', 'wholesale', 'discount', 'discount %', 'default discount',
  'reorder level', 'reorder', 'min stock', 'low stock alert quantity',
  'qty', 'pcs', 'pieces', 'stock', 'stock qty', 'unit cost', 'cost price', 'opening cost',
  'opening stock', 'opening qty', 'opening quantity', 'current stock',
  'unit_name', 'uom', 'uqc', 'alternate unit', 'alt unit', 'alt_uom', 'conversion',
  'item type', 'item_type', 'type', 'track inventory', 'track stock',
  'track batch', 'batch tracking', 'track serial', 'serial tracking',
  'tracking', 'tracking mode', 'tracking_mode',
  'sales tax inclusive', 'sales tax inclusive?', 'purchase tax inclusive',
  'warehouse', 'godown name', 'warehouse name', 'batch no', 'batch', 'lot', 'lot no',
  'expiry date', 'expiry', 'exp date', 'manufacturing date', 'mfg', 'mfg date',
  'as of', 'as of date', 'opening date', 'serial', 'serial number', 'serial numbers',
  'phone', 'mobile', 'contact', 'phone number', 'email', 'e-mail',
  'gstin', 'gst no', 'gstin number', 'state', 'address', 'billing_address', 'billing address',
  'exact', 'iexact', 'contains', 'icontains', 'in', 'gt', 'gte', 'lt', 'lte',
  'startswith', 'istartswith', 'endswith', 'iendswith', 'range', 'isnull',
  'regex', 'iregex', 'contained_by', 'has_key', 'has_keys', 'has_any_keys',
];

const RESERVED_NORMALIZED = new Set(RESERVED_ITEM_HEADERS.map(normalizeHeader).filter(Boolean));

export type FieldDefRowError = {
  key?: 'required' | 'format' | 'duplicate' | 'reserved' | 'max';
  label?: 'required' | 'duplicate' | 'reserved' | 'max';
  options?: 'required' | 'max' | 'length';
};

export function fieldDefRowErrors(defs: Array<{ key: string; label: string; type?: string; active?: boolean; options?: string[] }>): FieldDefRowError[] {
  const errors: FieldDefRowError[] = defs.map(() => ({}));
  const keyIndex = new Map<string, number>();
  const labelIndex = new Map<string, number>();
  const tokenOwner = new Map<string, number>();
  defs.forEach((row, index) => {
    const key = row.key.trim();
    const label = row.label.trim();
    if (!key) errors[index].key = 'required';
    else if (!CUSTOM_FIELD_KEY_RE.test(key)) errors[index].key = 'format';
    else if (key.length > MAX_KEY_LEN) errors[index].key = 'max';
    else if (RESERVED_NORMALIZED.has(normalizeHeader(key))) errors[index].key = 'reserved';
    else {
      const folded = key.toLowerCase();
      const prev = keyIndex.get(folded);
      if (prev != null) {
        errors[index].key = 'duplicate';
        errors[prev].key = 'duplicate';
      } else keyIndex.set(folded, index);
    }
    if (!label) errors[index].label = 'required';
    else if (label.length > MAX_LABEL_LEN) errors[index].label = 'max';
    else if (RESERVED_NORMALIZED.has(normalizeHeader(label))) errors[index].label = 'reserved';
    else if (row.active !== false) {
      const folded = normalizeHeader(label);
      const prev = labelIndex.get(folded);
      if (prev != null) {
        errors[index].label = 'duplicate';
        errors[prev].label = 'duplicate';
      } else labelIndex.set(folded, index);
    }
    if (row.active !== false && !errors[index].key && !errors[index].label) {
      for (const raw of [key, label]) {
        const token = normalizeHeader(raw);
        if (!token) continue;
        const prev = tokenOwner.get(token);
        if (prev != null && prev !== index) {
          if (normalizeHeader(label) === token) errors[index].label = 'duplicate';
          else errors[index].key = 'duplicate';
          const other = defs[prev];
          if (normalizeHeader(other.label) === token) errors[prev].label = 'duplicate';
          else errors[prev].key = 'duplicate';
        } else if (prev == null) {
          tokenOwner.set(token, index);
        }
      }
    }
    if (row.type === 'list' && row.active !== false) {
      const options = (row.options ?? []).map((item) => item.trim()).filter(Boolean);
      if (!options.length) errors[index].options = 'required';
      else if (options.length > MAX_LIST_OPTIONS) errors[index].options = 'max';
      else if (options.some((item) => item.length > MAX_OPTION_LEN)) errors[index].options = 'length';
    }
  });
  return errors;
}

export function fieldDefsHaveErrors(rows: FieldDefRowError[]): boolean {
  return rows.some((row) => Boolean(row.key || row.label || row.options));
}
