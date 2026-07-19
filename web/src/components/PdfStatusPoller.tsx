import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import { useQuery } from '@tanstack/react-query';
import { downloadInvoicePdf, getInvoicePdfStatus } from '@/api/resources';
import { t } from '@/i18n';
import type { PdfStatus } from '@/types/domain';
import { StatusChip } from './StatusChip';
import { pdfStatusTone } from '@/utils/status';

interface PdfStatusPollerProps {
  invoiceId: number | string;
  enabled?: boolean;
  onReady?: (pdfUrl?: string) => void;
}

export function PdfStatusPoller({
  invoiceId,
  enabled = true,
  onReady,
}: PdfStatusPollerProps) {
  const [manualRetry, setManualRetry] = useState(0);

  const query = useQuery({
    queryKey: ['invoice-pdf', invoiceId, manualRetry],
    queryFn: () => getInvoicePdfStatus(invoiceId),
    enabled: enabled && Boolean(invoiceId),
    refetchInterval: (q) => {
      const status = q.state.data?.pdfStatus;
      if (status === 'READY' || status === 'FAILED') return false;
      return 1500;
    },
  });

  const status = (query.data?.pdfStatus ?? 'QUEUED') as PdfStatus;

  useEffect(() => {
    if (status === 'READY') {
      onReady?.(query.data?.pdfUrl);
    }
  }, [status, query.data?.pdfUrl, onReady]);

  if (!enabled) return null;

  const handleDownload = async () => {
    const blob = await downloadInvoicePdf(invoiceId);
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  return (
    <Alert
      severity={status === 'FAILED' ? 'warning' : status === 'READY' ? 'success' : 'info'}
      icon={
        status === 'NONE' || status === 'QUEUED' ? (
          <CircularProgress size={18} />
        ) : undefined
      }
      action={
        status === 'READY' ? (
          <Button color="inherit" size="small" onClick={() => void handleDownload()}>
            {t('common.download')}
          </Button>
        ) : status === 'FAILED' ? (
          <Button color="inherit" size="small" onClick={() => setManualRetry((n) => n + 1)}>
            {t('common.retry')}
          </Button>
        ) : undefined
      }
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <StatusChip
          tone={pdfStatusTone(status)}
          label={
            status === 'READY'
              ? t('billing.pdfReady')
              : status === 'FAILED'
                ? t('billing.pdfFailed')
                : t('billing.pdfWaiting')
          }
        />
      </Stack>
    </Alert>
  );
}
