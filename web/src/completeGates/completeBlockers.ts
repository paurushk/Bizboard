import { parseSerialInput } from '@/components/billing/lineHelpers';
import { t } from '@/i18n';

export type CompleteBlockerInput = {
  canSave: boolean;
  partyRole?: 'customer' | 'supplier';
  posKnown?: boolean;
  gstinRequired?: boolean;
  missingBatchName?: string | null;
  missingSerialName?: string | null;
  stockBlocked?: boolean;
  creditHold?: boolean;
  creditLimitExceeded?: boolean;
  rcmUnconfirmed?: boolean;
  zeroQty?: boolean;
  overCap?: boolean;
  previewPending?: boolean;
  irnLocked?: boolean;
};

/**
 * First named reason when Complete is blocked after the user already has
 * a party + line (or the line set is invalid). Order is user-visible priority.
 */
export function firstCompleteDisabledReason(input: CompleteBlockerInput): string | undefined {
  if (input.gstinRequired) return t('billing.gstinRequiredBeforeGstComplete');
  if (input.overCap) return t('billing.completeDisabledOverCap');
  if (!input.canSave) return undefined;
  if (input.posKnown === false) {
    return input.partyRole === 'supplier'
      ? t('billing.placeOfSupplyRequiredSupplier')
      : t('billing.placeOfSupplyRequired');
  }
  if (input.missingBatchName) {
    return t('billing.purchaseBatchRequiredToComplete', { name: input.missingBatchName });
  }
  if (input.missingSerialName) {
    return t('billing.completeDisabledMissingSerial', { name: input.missingSerialName });
  }
  if (input.stockBlocked) return t('billing.completeDisabledInsufficientStock');
  if (input.creditHold) return t('phase1.creditHoldBanner');
  if (input.creditLimitExceeded) return t('billing.completeDisabledCreditLimit');
  if (input.rcmUnconfirmed) return t('billing.confirmSalesRcmRequired');
  if (input.zeroQty) return t('billing.completeDisabledZeroQty');
  if (input.previewPending) return t('billing.completeDisabledPreviewPending');
  if (input.irnLocked) return t('einvoice.lineAmendBlocked');
  return undefined;
}

export function posPayDisabledReason(input: {
  writesBlocked?: boolean;
  busy?: boolean;
  flushing?: boolean;
  upiPending?: boolean;
  cashPending?: boolean;
  tenderPreviewFailed?: boolean;
  stockBlocked?: boolean;
  missingBatch?: boolean;
  missingSerial?: boolean;
  mode: 'CASH' | 'UPI';
}): string | undefined {
  if (input.writesBlocked) return t('billing.writesBlocked');
  if (input.busy || input.flushing) return t('pos.payInProgress');
  if (input.stockBlocked) return t('billing.completeDisabledInsufficientStock');
  if (input.missingBatch) return t('billing.completeDisabledMissingBatch');
  if (input.missingSerial) return t('pos.serialRequired');
  if (input.mode === 'CASH' && input.upiPending) return t('pos.finishPendingUpi');
  if (input.mode === 'UPI' && input.cashPending) return t('pos.finishPendingCash');
  if (input.mode === 'UPI' && input.tenderPreviewFailed) {
    return t('pos.tenderPreviewRetry');
  }
  return undefined;
}

/** Online preview: ready, or errored (client-total fallback), never silent pending. */
export function previewAllowsComplete(
  online: boolean,
  ready: boolean,
  error: string | null,
): boolean {
  if (!online) return true;
  if (ready) return true;
  return error != null;
}

export function serialCountMatchesQty(serialText: string | undefined, quantity: number): boolean {
  return parseSerialInput(serialText ?? '').serials.length === Math.trunc(quantity);
}

/** Named Complete reason on sales/purchase return dialogs (no DocumentEditorShell). */
export function returnCompleteDisabledReason(input: {
  writesBlocked?: boolean;
  permissionDenied?: boolean;
  pending?: boolean;
  missingSource?: boolean;
  noLines?: boolean;
}): string | undefined {
  if (input.writesBlocked) return t('billing.writesBlocked');
  if (input.permissionDenied) return t('phase1.salesReturnCompleteOwnerOnly');
  if (input.pending) return t('billing.completeDisabledSaving');
  if (input.missingSource) return t('billing.completeDisabledReason');
  if (input.noLines) return t('phase1.selectItemToReturn');
  return undefined;
}
