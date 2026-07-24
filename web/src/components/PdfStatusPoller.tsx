import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  downloadInvoicePdf,
  getInvoicePdfStatus,
  regenerateInvoicePdf,
} from '@/api/resources';
import { t } from '@/i18n';
import type { PdfStatus } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';
import { pdfStatusTone } from '@/utils/status';
import { StatusChip } from './StatusChip';

interface PdfStatusPollerProps {
  invoiceId: number | string;
  enabled?: boolean;
  onReady?: (pdfUrl?: string) => void;
  filenameBase?: string;
}

const MAX_POLLS = 40;

export function PdfStatusPoller({
  invoiceId,
  enabled = true,
  onReady,
  filenameBase,
}: PdfStatusPollerProps) {
  const [pollCount, setPollCount] = useState(0);
  const [retryToken, setRetryToken] = useState(0);

  const regenerate = useMutation({
    mutationFn: () => regenerateInvoicePdf(invoiceId),
    onSuccess: () => {
      setPollCount(0);
      setRetryToken((n) => n + 1);
    },
  });

  const query = useQuery({
    queryKey: ['invoice-pdf', invoiceId, retryToken],
    queryFn: async () => {
      setPollCount((n) => n + 1);
      return getInvoicePdfStatus(invoiceId);
    },
    enabled: enabled && Boolean(invoiceId),
    refetchInterval: (q) => {
      const status = q.state.data?.pdfStatus;
      if (status === 'READY' || status === 'FAILED') return false;
      if (pollCount >= MAX_POLLS) return false;
      // Backoff: 1.5s → 3s → 6s capped at 6s
      const step = Math.min(6000, 1500 * 2 ** Math.min(pollCount, 2));
      return step;
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
    const blob = await downloadInvoicePdf(invoiceId, { copy: 'ORIGINAL' });
    const name = `${filenameBase ?? `invoice-${invoiceId}`}_original.pdf`;
    triggerBlobDownload(blob, name);
  };

  const timedOut = pollCount >= MAX_POLLS && status !== 'READY' && status !== 'FAILED';

  return (
    <Alert
      severity={
        status === 'FAILED' || timedOut
          ? 'warning'
          : status === 'READY'
            ? 'success'
            : 'info'
      }
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
        ) : status === 'FAILED' || timedOut ? (
          <Button
            color="inherit"
            size="small"
            disabled={regenerate.isPending}
            onClick={() => regenerate.mutate()}
          >
            {t('common.retry')}
          </Button>
        ) : undefined
      }
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <StatusChip
          tone={pdfStatusTone(status === 'FAILED' || timedOut ? 'FAILED' : status)}
          label={
            status === 'READY'
              ? t('billing.pdfReady')
              : status === 'FAILED' || timedOut
                ? t('billing.pdfFailed')
                : t('billing.pdfWaiting')
          }
        />
      </Stack>
    </Alert>
  );
}
