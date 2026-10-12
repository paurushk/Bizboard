import type { GstinVerificationStatus } from '@/types/domain';

export type GstinChipColor = 'default' | 'success' | 'warning' | 'error';

function normalise(status?: GstinVerificationStatus | null): string {
  return (status || 'UNVERIFIED').toUpperCase();
}

/** Chip colour for a stored GSTIN verification status. The API stores VALID; VERIFIED is a legacy alias. */
export function gstinStatusColor(status?: GstinVerificationStatus | null): GstinChipColor {
  switch (normalise(status)) {
    case 'VALID':
    case 'VERIFIED':
      return 'success';
    case 'INVALID':
    case 'FAILED':
    case 'CANCELLED':
    case 'SUSPENDED':
      return 'error';
    case 'UNVERIFIED':
      return 'warning';
    default:
      return 'default';
  }
}

const LABEL_KEYS: Record<string, string> = {
  VALID: 'customers.gstinStatusValid',
  VERIFIED: 'customers.gstinStatusValid',
  INVALID: 'customers.gstinStatusInvalid',
  FAILED: 'customers.gstinStatusInvalid',
  CANCELLED: 'customers.gstinStatusCancelled',
  SUSPENDED: 'customers.gstinStatusSuspended',
  UNVERIFIED: 'customers.gstinStatusUnverified',
};

/** i18n key for the chip text; an unknown status falls back to Unverified rather than showing a raw code. */
export function gstinStatusLabelKey(status?: GstinVerificationStatus | null): string {
  return LABEL_KEYS[normalise(status)] ?? 'customers.gstinStatusUnverified';
}
