import { ALLOWED_GST_RATES } from '@/utils/gst';
import type {
  BillLineError,
  ImportJob,
  PurchaseBillLinePreview,
  PurchaseBillPreview,
} from '@/types/domain';

/** A preview line as held in the editor. `clientKey` is stable for the life of the row. */
export type EditorLine = PurchaseBillLinePreview & { clientKey: string; deleted?: boolean };

// Mirrors the backend HSN rule (2, 4, 6 or 8 digits). The server is the final
// authority; this only gives instant feedback while typing.
const HSN_PATTERN = /^\d{2}(\d{2})?(\d{2})?(\d{2})?$/;

export function isBillPreview(preview: ImportJob['preview']): preview is PurchaseBillPreview {
  return !!preview && !Array.isArray(preview) && Array.isArray((preview as PurchaseBillPreview).lines);
}

/** cs*upc+pcs, or null when the pack data cannot form a quantity. */
export function billedFromPack(cs?: string, pcs?: string, upc?: string): string | null {
  const u = Number(upc);
  if (!Number.isFinite(u) || u <= 0) return null;
  const c = Number(cs || 0);
  const p = Number(pcs || 0);
  if (!Number.isFinite(c) || !Number.isFinite(p)) return null;
  return String(c * u + p);
}

let keyCounter = 0;
export function newClientKey(): string {
  keyCounter += 1;
  return `row-${Date.now().toString(36)}-${keyCounter}`;
}

function text(value: unknown): string {
  return value == null ? '' : String(value);
}

/** Bill Import Redesign Plan §7 Phase 0: unread OCR fields stay blank, never fabricated. */
export function toEditorLines(preview: PurchaseBillPreview | null): EditorLine[] {
  if (!preview?.lines) return [];
  return preview.lines.map((line, index) => {
    const raw = line as PurchaseBillLinePreview & {
      hsn_code?: string;
      unit_price?: string;
      gst_rate?: string;
    };
    return {
      clientKey: raw.lineId != null ? `line-${raw.lineId}` : newClientKey(),
      lineId: raw.lineId,
      si: raw.si ? String(raw.si) : String(index + 1),
      name: raw.name ?? '',
      sku: raw.sku ?? '',
      hsnCode: raw.hsnCode ?? raw.hsn_code ?? '',
      quantity: text(raw.quantity),
      pcs: text(raw.pcs),
      cs: text(raw.cs),
      upc: text(raw.upc),
      unitPrice: text(raw.unitPrice ?? raw.unit_price),
      gstRate: text(raw.gstRate ?? raw.gst_rate),
      mrp: text(raw.mrp),
      discountPercent: text(raw.discountPercent),
      cessRate: text(raw.cessRate),
      include: raw.include !== false,
      flags: Array.isArray(raw.flags) ? raw.flags : [],
      errors: Array.isArray(raw.errors) ? raw.errors : [],
      excludedReason: raw.excludedReason,
      productId: raw.productId ?? null,
      createNew: Boolean(raw.createNew),
      productMatch: raw.productMatch,
      priceListPrice: raw.priceListPrice,
      belowPriceList: Boolean(raw.belowPriceList),
      bbox: Array.isArray(raw.bbox) && raw.bbox.length === 4 ? raw.bbox : null,
      edited: Boolean(raw.edited),
    };
  });
}

/** Fields that identify one editable row to the API (everything the user can change). */
const EDITABLE_FIELDS = [
  'name', 'sku', 'hsnCode', 'quantity', 'pcs', 'cs', 'upc', 'unitPrice', 'gstRate', 'mrp',
  'discountPercent', 'include', 'productId', 'createNew',
] as const;

export function lineSignature(line: EditorLine): string {
  return JSON.stringify(EDITABLE_FIELDS.map((field) => line[field] ?? null));
}

/** Payload for one line. Only server-known fields are sent; the server merges by lineId. */
export function linePayload(line: EditorLine): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: line.name,
    sku: line.sku ?? '',
    hsnCode: line.hsnCode ?? '',
    quantity: line.quantity,
    pcs: line.pcs ?? '',
    cs: line.cs ?? '',
    upc: line.upc ?? '',
    unitPrice: line.unitPrice,
    gstRate: line.gstRate,
    mrp: line.mrp ?? '0',
    discountPercent: line.discountPercent ?? '',
    include: line.include !== false,
    productId: line.productId ?? null,
    createNew: Boolean(line.createNew),
  };
  if (line.lineId != null) body.lineId = line.lineId;
  else body.isNew = true;
  return body;
}

function numeric(value: string | undefined): number | null {
  const trimmed = String(value ?? '').trim();
  if (trimmed === '') return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

/** Instant, cheap checks. The server repeats and extends these at commit. */
export function localLineErrors(line: EditorLine): BillLineError[] {
  const errors: BillLineError[] = [];
  if (!String(line.name ?? '').trim()) {
    errors.push({ field: 'name', code: 'NAME_REQUIRED', message: 'name is required' });
  }
  const qty = numeric(line.quantity);
  if (qty == null || qty <= 0) {
    errors.push({ field: 'quantity', code: 'QTY_POSITIVE', message: 'quantity must be > 0' });
  }
  const price = numeric(line.unitPrice);
  if (price == null || price < 0) {
    errors.push({ field: 'unit_price', code: 'PRICE_NUMBER', message: 'unit_price must be a number' });
  }
  const gst = numeric(line.gstRate);
  if (gst == null) {
    errors.push({ field: 'gst_rate', code: 'GST_REQUIRED', message: 'GST rate is required' });
  } else if (!ALLOWED_GST_RATES.includes(gst)) {
    errors.push({ field: 'gst_rate', code: 'GST_SLAB', message: `GST rate ${gst} is not an allowed slab` });
  }
  const hsn = String(line.hsnCode ?? '').trim();
  if (hsn && !HSN_PATTERN.test(hsn)) {
    errors.push({ field: 'hsn_code', code: 'HSN_FORMAT', message: 'invalid HSN code' });
  }
  return errors;
}

/** A row has no remaining blocking problem the page can already see. */
export function isLineComplete(line: EditorLine): boolean {
  return localLineErrors(line).length === 0;
}

export function errorFor(errors: BillLineError[] | undefined, field: string): BillLineError | undefined {
  return errors?.find((e) => e.field === field && e.severity !== 'warning');
}

/** The pack columns only matter when the bill actually has Cs / UPC data. */
export function hasPackData(lines: EditorLine[]): boolean {
  return lines.some((l) => String(l.cs ?? '').trim() !== '' || String(l.upc ?? '').trim() !== '');
}

/** djb2 hash of the canonical payload -> a short, stable idempotency suffix. */
export function payloadHash(payload: unknown): string {
  const textValue = JSON.stringify(payload);
  let hash = 5381;
  for (let i = 0; i < textValue.length; i += 1) {
    hash = ((hash << 5) + hash + textValue.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(36);
}

/** Line total as the draft will show it (GST included either way). */
export function lineAmount(line: EditorLine, priceInclusive = false): number | null {
  const qty = numeric(line.quantity);
  const price = numeric(line.unitPrice);
  if (qty == null || price == null) return null;
  const disc = numeric(line.discountPercent) ?? 0;
  const gst = numeric(line.gstRate) ?? 0;
  const net = qty * price * (1 - disc / 100);
  return Math.round((priceInclusive ? net : net * (1 + gst / 100)) * 100) / 100;
}
