/**
 * Shared billing UI helpers extracted from NewInvoice / NewPurchase pages.
 * Page-specific save mutations stay in the page wrappers.
 */
export { useDebouncedValue } from '@/hooks/useDebouncedValue';
export {
  primarySaveAction,
  useBillingSaveFeedback,
} from '@/hooks/useBillingSaveFeedback';
export type { BillingDocumentStatus, PrimarySaveAction } from '@/hooks/useBillingSaveFeedback';
export { printBlob, triggerBlobDownload, openBlobInTab } from '@/utils/blob';
