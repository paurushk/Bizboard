import { preferredInvoiceType } from '@/onboarding/taxHints';
import type { RegistrationType } from '@/types/domain';

export type InvoiceDefaultChoice = {
  invoiceType: 'GST' | 'NON_GST';
  priceMode: 'INCLUSIVE' | 'EXCLUSIVE';
  paymentTermsDays: number;
};

type RecentBill = {
  invoiceType?: string | null;
  priceMode?: string | null;
  customerName?: string | null;
};

function isWalkIn(name?: string | null): boolean {
  return /walk[\s-]?in/i.test(name ?? '');
}

/** Last completed bills choose the next invoice. Fewer than three bills follow the company. */
export function chooseInvoiceDefaults(args: {
  invoices: RecentBill[];
  registrationType?: RegistrationType | null;
  companyPriceMode?: string | null;
}): InvoiceDefaultChoice {
  const companyType = preferredInvoiceType(args.registrationType ?? undefined) === 'GST' ? 'GST' : 'NON_GST';
  const companyMode = args.companyPriceMode === 'INCLUSIVE' ? 'INCLUSIVE' : 'EXCLUSIVE';
  const recent = args.invoices.slice(0, 5);
  if (recent.length < 3) {
    return { invoiceType: companyType, priceMode: companyMode, paymentTermsDays: 30 };
  }
  const walkIn = recent.filter((row) => isWalkIn(row.customerName));
  if (walkIn.length >= 3) {
    const gst = walkIn.filter((row) => row.invoiceType === 'GST').length;
    const inclusive = walkIn.filter((row) => row.priceMode === 'INCLUSIVE').length;
    return {
      invoiceType: gst >= walkIn.length / 2 ? 'GST' : 'NON_GST',
      priceMode: inclusive > walkIn.length / 2 ? 'INCLUSIVE' : 'EXCLUSIVE',
      paymentTermsDays: 0,
    };
  }
  return { invoiceType: companyType, priceMode: companyMode, paymentTermsDays: 30 };
}

/**
 * BUG-COG-001a. The select stays on screen. Inference only runs while the user
 * has not touched it. RETAIL is the B2C value on the invoice-type select.
 */
export function inferInvoiceTypeFromParty(args: {
  registrationType?: string | null;
  customerGstin?: string | null;
}): 'GST' | 'NON_GST' | 'RETAIL' {
  if (args.registrationType !== 'REGULAR') {
    return preferredInvoiceType(args.registrationType as RegistrationType | undefined) === 'GST'
      ? 'GST'
      : 'NON_GST';
  }
  if ((args.customerGstin || '').trim()) return 'GST';
  return 'RETAIL';
}
