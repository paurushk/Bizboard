import type {
  CustomerStatus,
  DocumentStatus,
  PdfStatus,
  ProductStatus,
} from '@/types/domain';

export type ChipTone = 'default' | 'success' | 'warning' | 'error' | 'info';

/** Completed invoices with zero outstanding show as Paid (E2E3-031). */
export function paidAwareStatus(status: string, balance?: string | number | null): string {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'COMPLETED' && balance != null && Number(balance) === 0) {
    return 'PAID';
  }
  return String(status || '');
}

export function documentStatusTone(status: DocumentStatus | string): ChipTone {
  switch (String(status).toUpperCase()) {
    case 'COMPLETED':
    case 'CONVERTED':
    case 'PAID':
      return 'success';
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
