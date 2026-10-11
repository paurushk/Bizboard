import { t } from '@/i18n';
import type { CustomerReceipt } from '@/types/domain';

export type ReceiptChipColor = 'success' | 'error' | 'warning' | 'info' | 'default';

export interface ReceiptChip {
  key: string;
  label: string;
  color: ReceiptChipColor;
}

/** Same floor the server enforces on a void reason (payments.services.MIN_VOID_REASON_LENGTH). */
export const MIN_VOID_REASON_LENGTH = 3;
export const MAX_VOID_REASON_LENGTH = 500;

/**
 * Status chips for one receipt: its own state, then the cheque state for a cheque.
 * Every known state has its own colour so a voided or bounced row never reads as normal.
 */
export function receiptStatusChips(
  receipt: Pick<CustomerReceipt, 'status' | 'mode' | 'chequeStatus'>,
): ReceiptChip[] {
  const chips: ReceiptChip[] = [];
  switch (receipt.status) {
    case 'VOIDED':
      chips.push({ key: 'status', label: t('receipts.statusVoided'), color: 'error' });
      break;
    case 'REFUNDED':
      chips.push({ key: 'status', label: t('receipts.statusRefunded'), color: 'warning' });
      break;
    case 'POSTED':
    case undefined:
      chips.push({ key: 'status', label: t('receipts.statusPosted'), color: 'success' });
      break;
    default:
      chips.push({ key: 'status', label: String(receipt.status), color: 'default' });
  }
  if (receipt.mode === 'CHEQUE' && receipt.chequeStatus) {
    if (receipt.chequeStatus === 'PENDING_CLEARANCE') {
      chips.push({ key: 'cheque', label: t('receipts.chequePending'), color: 'warning' });
    } else if (receipt.chequeStatus === 'CLEARED') {
      chips.push({ key: 'cheque', label: t('receipts.chequeCleared'), color: 'success' });
    } else if (receipt.chequeStatus === 'BOUNCED') {
      chips.push({ key: 'cheque', label: t('receipts.chequeBounced'), color: 'error' });
    }
  }
  return chips;
}
