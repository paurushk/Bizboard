import type { ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import type { SxProps, Theme } from '@mui/material/styles';
import { getErrorCode, getErrorMessage, getErrorRequestId } from '@/api/client';
import { HelpWhyLink } from '@/pages/help/HelpWhyLink';

/** Error Alert with Why? when helpV2 is on. Drop-in for mutation/page errors. */
export function HelpErrorAlert({
  message,
  error,
  invoiceId,
  onClose,
  sx,
  action,
  children,
  code: codeOverride,
}: {
  message?: string | null;
  error?: unknown;
  invoiceId?: string | number;
  onClose?: () => void;
  sx?: SxProps<Theme>;
  action?: ReactNode;
  children?: ReactNode;
  code?: string | null;
}) {
  const text = message ?? (error != null ? getErrorMessage(error) : null);
  if (!text) return null;
  const code = codeOverride ?? (error != null ? getErrorCode(error) : undefined);
  const supportId = error != null ? getErrorRequestId(error) : null;
  return (
    <Alert severity="error" role="alert" aria-live="polite" onClose={onClose} sx={sx} action={action}>
      {text}
      {children}
      {supportId ? (
        <div style={{ marginTop: 8, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', userSelect: 'all' }}>
          Support ID: {supportId}
        </div>
      ) : null}
      <HelpWhyLink code={code} message={text} invoiceId={invoiceId} />
    </Alert>
  );
}
