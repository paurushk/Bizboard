import { useEffect } from 'react';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';
import { useReasonPrompt } from '@/hooks/useReasonPrompt';
import { registerGlobalConfirm, registerGlobalReason } from '@/utils/confirmBridge';

/** Mount once in the app shell: renders the dialog that completeWithConfirms asks through. */
export function GlobalConfirmHost() {
  const { ask, dialog } = useConfirmPrompt();
  const { ask: askReasonDialog, dialog: reasonDialog } = useReasonPrompt();
  useEffect(() => {
    registerGlobalConfirm(ask);
    return () => registerGlobalConfirm(null);
  }, [ask]);
  useEffect(() => {
    registerGlobalReason(askReasonDialog);
    return () => registerGlobalReason(null);
  }, [askReasonDialog]);
  return (
    <>
      {dialog}
      {reasonDialog}
    </>
  );
}
