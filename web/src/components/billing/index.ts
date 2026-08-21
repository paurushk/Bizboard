/**
 * Shared billing UI helpers extracted from NewInvoice / NewPurchase pages (P0-311).
 * Page-specific save mutations stay in the page wrappers.
 */
export { useDebouncedValue } from '@/hooks/useDebouncedValue';
export {
  primarySaveAction,
  useBillingSaveFeedback,
} from '@/hooks/useBillingSaveFeedback';
export type { BillingDocumentStatus, PrimarySaveAction } from '@/hooks/useBillingSaveFeedback';
export { printBlob, triggerBlobDownload, openBlobInTab } from '@/utils/blob';
export { CompactField, NumericField } from './NumericField';
export {
  applyDiscountAmountPatch,
  formatSerialNumbersText,
  makeLine,
  parseSerialNumbersText,
  recomputeLine,
  todayIso,
} from './lineHelpers';
export type { DraftLine, DraftLinePriceField } from './types';
export { DocumentEditorShell } from './DocumentEditorShell';
export type { DocumentEditorShellProps } from './DocumentEditorShell';
export { InvoiceSourceLineTable, InvoiceReturnLineTable } from './InvoiceSourceLineTable';
export { SimpleTotalsPanel } from './SimpleTotalsPanel';
export { DraftLineTable } from './DraftLineTable';
export type { DraftLinePatchOpts } from './DraftLineTable';
export { NoteReasonSelect } from './NoteReasonSelect';
export {
  activeSourceLines,
  clampSourceLineQty,
  invoiceItemsToSourceLines,
  noteItemsToSourceLines,
} from './invoiceSourceLines';
export type { InvoiceSourceLine } from './invoiceSourceLines';
