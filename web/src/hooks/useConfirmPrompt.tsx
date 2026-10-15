import { useCallback, useRef, useState } from 'react';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { t } from '@/i18n';

/**
 * In-app replacement for window.confirm (DN-04). `ask(messages)` resolves true when
 * the user continues. Render `dialog` once in the page.
 */
export function useConfirmPrompt() {
  const [messages, setMessages] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const ask = useCallback(
    (next: string[]) =>
      new Promise<boolean>((resolve) => {
        resolver.current = resolve;
        setMessages(next);
        setOpen(true);
      }),
    [],
  );

  const settle = (ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    // Keep the text while the dialog fades out; clearing it would flash an empty box.
    setOpen(false);
  };

  const dialog = (
    <ConfirmDialog
      open={open}
      title={t('common.confirm')}
      body={(messages ?? []).join('\n\n')}
      onClose={() => settle(false)}
      onConfirm={() => settle(true)}
    />
  );
  return { ask, dialog };
}
