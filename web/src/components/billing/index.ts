/**
 * Shared billing UI helpers extracted from NewInvoice / NewPurchase pages.
 * Page-specific save mutations stay in the page wrappers.
 */
export { useDebouncedValue } from '@/hooks/useDebouncedValue';
export { printBlob, triggerBlobDownload, openBlobInTab } from '@/utils/blob';
