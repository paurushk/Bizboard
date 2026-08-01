import { useCallback, useState } from 'react';

/**
 * Shared billing flash state for New Invoice / New Purchase.
 *
 * BUG-500 / BUG-501: Save & New calls form reset in the same tick as setting
 * the success (and optional payment-warning) message. React batches those
 * updates — if reset clears message/error, the flash never appears.
 *
 * Contract: `resetForm` (and any field wipe) must NOT call `clearFeedback`.
 * Only clear on document switch, starting a new save attempt, or dismiss.
 */

export type BillingDocumentStatus = 'DRAFT' | 'COMPLETED' | 'CANCELLED' | string | null;

export type PrimarySaveAction = {
  /** Mutation mode for the primary button. */
  mode: 'draft' | 'complete';
  /** i18n key for the button label. */
  labelKey: 'common.save' | 'billing.saveAndComplete';
};

/**
 * Draft vs Complete button semantics (BUG-507 / P0-302):
 * - Creating or editing a DRAFT: primary action completes → "Save & Complete"
 * - Editing an already COMPLETED doc: primary only persists edits → "Save"
 */
export function primarySaveAction(opts: {
  isEdit: boolean;
  editingStatus: BillingDocumentStatus;
}): PrimarySaveAction {
  if (opts.isEdit && opts.editingStatus === 'COMPLETED') {
    return { mode: 'draft', labelKey: 'common.save' };
  }
  return { mode: 'complete', labelKey: 'billing.saveAndComplete' };
}

export function useBillingSaveFeedback() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearFeedback = useCallback(() => {
    setMessage(null);
    setError(null);
  }, []);

  /** Success flash for Save & New — intentionally survives a following form reset. */
  const flashSaveAndNew = useCallback((successMessage: string, warning?: string | null) => {
    setMessage(successMessage);
    setError(warning ?? null);
  }, []);

  const flashError = useCallback((err: string) => {
    setError(err);
  }, []);

  const flashWarning = useCallback((warning: string | null) => {
    setError(warning);
  }, []);

  return {
    message,
    error,
    setMessage,
    setError,
    clearFeedback,
    flashSaveAndNew,
    flashError,
    flashWarning,
  };
}
