/** Builds the quotation create/update body for each editor mode.
 *
 * A partially converted quotation may only change the header fields the server
 * whitelists (validity, notes, terms, delivery address, salesperson, channel), so
 * its payload never carries customer, date, type, money fields or lines. */
export type QuotationFormLine = {
  /** Existing line id; lets the server update the line in place. */
  id?: number;
  productId: number;
  qty: number;
  unitPrice: number;
  discountPercent: number;
  expectedPrice: number;
  gstRate: number;
  /** Carried through from the saved line so an edit does not drop what only the API can set. */
  hsnCode?: string;
  cessRate?: number;
  unitPriceInclusive?: number | null;
};

function lineExtras(l: QuotationFormLine): Record<string, unknown> {
  return {
    ...(l.hsnCode ? { hsnCode: l.hsnCode } : {}),
    ...(l.cessRate ? { cessRate: l.cessRate } : {}),
    ...(l.unitPriceInclusive != null ? { unitPriceInclusive: l.unitPriceInclusive } : {}),
  };
}

export type QuotationFormState = {
  customerId: number;
  quotationDate: string;
  validUntil: string;
  salesman: string;
  salesChannel: string;
  deliveryAddress: string;
  invoiceType: string;
  lines: QuotationFormLine[];
  notes?: string;
  termsText?: string;
  paymentTermsDays?: number;
  additionalCharges?: number;
  chargesHsn?: string;
  chargesGstRate?: number;
  invoiceDiscount?: number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
};

export type QuotationPayloadMode = 'create' | 'edit' | 'edit-partially-converted';

export function buildQuotationPayload(
  form: QuotationFormState,
  mode: QuotationPayloadMode,
  opts: { includeCost?: boolean } = {},
): Record<string, unknown> {
  const includeCost = opts.includeCost ?? true;
  const header: Record<string, unknown> = {
    validUntil: form.validUntil || null,
    salesman: form.salesman ? Number(form.salesman) : null,
    salesChannel: form.salesChannel,
    deliveryAddress: form.deliveryAddress,
  };
  if (form.notes !== undefined) header.notes = form.notes;
  if (form.termsText !== undefined) header.termsText = form.termsText;
  if (mode === 'edit-partially-converted') return header;

  const payload: Record<string, unknown> = {
    ...header,
    customer: form.customerId,
    quotationDate: form.quotationDate,
    items: form.lines.map((l) => ({
      ...(l.id != null ? { id: l.id } : {}),
      product: l.productId,
      quantity: l.qty,
      unitPrice: l.unitPrice,
      discountPercent: l.discountPercent,
      ...(includeCost ? { expectedPrice: l.expectedPrice } : {}),
      gstRate: l.gstRate,
      ...lineExtras(l),
    })),
  };
  if (form.paymentTermsDays !== undefined) payload.paymentTermsDays = form.paymentTermsDays;
  if (form.additionalCharges !== undefined) payload.additionalCharges = form.additionalCharges;
  if (form.chargesHsn !== undefined) payload.chargesHsn = form.chargesHsn;
  if (form.chargesGstRate !== undefined) payload.chargesGstRate = form.chargesGstRate;
  if (form.invoiceDiscount !== undefined) payload.invoiceDiscount = form.invoiceDiscount;
  if (form.invoiceDiscountMode !== undefined) payload.invoiceDiscountMode = form.invoiceDiscountMode;
  if (form.autoRoundOff !== undefined) payload.autoRoundOff = form.autoRoundOff;
  // An existing quotation keeps its stored invoice type.
  if (mode === 'create') payload.invoiceType = form.invoiceType;
  return payload;
}

/** The body the server's totals preview needs, built from the same form. */
export function buildQuotationPreviewBody(
  form: QuotationFormState,
  extra: { supplyType?: string; companyGstin?: number | null } = {},
): Record<string, unknown> {
  return {
    customer: form.customerId,
    invoiceType: form.invoiceType,
    ...(extra.supplyType ? { supplyType: extra.supplyType } : {}),
    ...(extra.companyGstin ? { companyGstin: extra.companyGstin } : {}),
    additionalCharges: form.additionalCharges ?? 0,
    chargesHsn: form.chargesHsn ?? '',
    chargesGstRate: form.chargesGstRate ?? 0,
    invoiceDiscount: form.invoiceDiscount ?? 0,
    invoiceDiscountMode: form.invoiceDiscountMode ?? 'AFTER_TAX',
    autoRoundOff: form.autoRoundOff ?? true,
    items: form.lines.map((l) => ({
      product: l.productId,
      quantity: l.qty,
      unitPrice: l.unitPrice,
      discountPercent: l.discountPercent,
      gstRate: l.gstRate,
      ...lineExtras(l),
    })),
  };
}
