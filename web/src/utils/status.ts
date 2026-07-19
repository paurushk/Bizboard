import type {
  CustomerStatus,
  DocumentStatus,
  PdfStatus,
  ProductStatus,
} from '@/types/domain';

export type ChipTone = 'default' | 'success' | 'warning' | 'error' | 'info';

export function documentStatusTone(status: DocumentStatus | string): ChipTone {
  switch (String(status).toUpperCase()) {
    case 'COMPLETED':
    case 'CONVERTED':
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
