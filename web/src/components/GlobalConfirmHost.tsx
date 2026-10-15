import { useEffect } from 'react';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';
import { registerGlobalConfirm } from '@/utils/confirmBridge';

/** Mount once in the app shell: renders the dialog that completeWithConfirms asks through. */
export function GlobalConfirmHost() {
  const { ask, dialog } = useConfirmPrompt();
  useEffect(() => {
    registerGlobalConfirm(ask);
    return () => registerGlobalConfirm(null);
  }, [ask]);
  return dialog;
}
