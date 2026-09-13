import type {
  CustomerStatus,
  DocumentStatus,
  PdfStatus,
  ProductStatus,
} from '@/types/domain';

export type ChipTone = 'default' | 'success' | 'warning' | 'error' | 'info';

/** Completed invoices with zero outstanding show as Paid (E2E3-031).
 * Only COMPLETED invoices get this treatment — a RETURNED or CANCELLED
 * invoice can also have zero outstanding (e.g. a full return unallocates
 * the payment into a credit note that nets the balance back to zero), but
 * must keep showing its real status rather than being masked as "Paid". */
export function paidAwareStatus(
  status: string,
  balance?: string | number | null,
  paymentState?: string | null,
): string {
  const normalized = String(status || '').toUpperCase();
  if (normalized !== 'COMPLETED') return normalized;
  const ps = String(paymentState || '').toUpperCase();
  if (ps === 'PAID') return 'PAID';
  if (ps === 'PAID_PENDING_BOOKS') return 'PAID_PENDING_BOOKS';
  if (balance != null && Number(balance) === 0) {
    return 'PAID';
  }
  return normalized;
}

export function documentStatusTone(status: DocumentStatus | string): ChipTone {
  switch (String(status).toUpperCase()) {
    case 'COMPLETED':
    case 'CONVERTED':
    case 'PAID':
      return 'success';
    case 'PAID_PENDING_BOOKS':
      return 'info';
    case 'DRAFT':
      return 'default';
    case 'RETURNED':
      return 'warning';
    case 'CANCELLED':
      return 'error';
    default:
      return 'default';
  }
}

export function customerStatusTone(status: CustomerStatus | string): ChipTone {
  return String(status).toUpperCase() === 'ACTIVE' ? 'success' : 'error';
}

export function productStatusTone(status: ProductStatus | string): ChipTone {
  return String(status).toUpperCase() === 'ACTIVE' ? 'success' : 'default';
}

export function pdfStatusTone(status: PdfStatus | string): ChipTone {
  switch (String(status).toUpperCase()) {
    case 'READY':
      return 'success';
    case 'NONE':
    case 'QUEUED':
      return 'info';
    case 'FAILED':
      return 'error';
    default:
      return 'default';
  }
}

export function statusLabelKey(status: string): string {
  return `status.${String(status).toUpperCase()}`;
}
