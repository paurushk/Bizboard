import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  downloadSalesDocumentPdf,
  getSalesDocumentPdfStatus,
  regenerateSalesDocumentPdf,
  type SalesPdfDocType,
} from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import type { PdfStatus } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';
import { pdfStatusTone } from '@/utils/status';
import { StatusChip } from './StatusChip';

interface PdfStatusPollerProps {
  /** @deprecated Prefer documentId + docType */
  invoiceId?: number | string;
  documentId?: number | string;
  docType?: SalesPdfDocType;
  enabled?: boolean;
  onReady?: (pdfUrl?: string) => void;
  filenameBase?: string;
}

const MAX_POLLS = 40;

/**
 * PDF status poller for sales documents.
 *
 * When GET /api/v1/health/ reports `celery: false` / `status: "degraded"`,
 * jobs stay QUEUED until a worker recovers — ops should watch `pdf_queue_depth`.
 * A future enhancement can one-shot health and show "PDF worker unavailable"
 * here; skipped for now to avoid coupling every invoice screen to /health/.
 */
export function PdfStatusPoller({
  invoiceId,
  documentId,
  docType = 'invoice',
  enabled = true,
  onReady,
  filenameBase,
}: PdfStatusPollerProps) {
  const id = documentId ?? invoiceId;
  const [pollCount, setPollCount] = useState(0);
  const [retryToken, setRetryToken] = useState(0);
  const [dlError, setDlError] = useState<string | null>(null);

  const regenerate = useMutation({
    mutationFn: () => regenerateSalesDocumentPdf(docType, id as number | string),
    onSuccess: () => {
      setPollCount(0);
      setRetryToken((n) => n + 1);
    },
  });

  const query = useQuery({
    queryKey: ['doc-pdf', docType, id, retryToken],
    // F3-045: queryFn must be pure — a retry / internal refetch double-counted
    // and the poller gave up early on a still-generating PDF. Count in an
    // effect keyed on the fetch timestamp instead.
    queryFn: () => getSalesDocumentPdfStatus(docType, id as number | string),
    enabled: enabled && Boolean(id),
    refetchInterval: (q) => {
      const status = q.state.data?.pdfStatus;
      if (status === 'READY' || status === 'FAILED') return false;
      if (pollCount >= MAX_POLLS) return false;
      const step = Math.min(6000, 1500 * 2 ** Math.min(pollCount, 2));
      return step;
    },
  });

  useEffect(() => {
    setPollCount(0);
  }, [retryToken]);
  useEffect(() => {
    if (query.dataUpdatedAt) setPollCount((n) => n + 1);
  }, [query.dataUpdatedAt]);

  const status = (query.data?.pdfStatus ?? 'QUEUED') as PdfStatus;

  useEffect(() => {
    if (status === 'READY') {
      onReady?.(query.data?.pdfUrl);
    }
  }, [status, query.data?.pdfUrl, onReady]);

  if (!enabled || !id) return null;

  const handleDownload = async () => {
    setDlError(null);
    try {
      const blob = await downloadSalesDocumentPdf(docType, id, { copy: 'ORIGINAL' });
      const name = `${filenameBase ?? `${docType}-${id}`}_original.pdf`;
      triggerBlobDownload(blob, name);
    } catch (err) {
      setDlError(getErrorMessage(err));
    }
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
        {dlError ? (
          <Stack sx={{ color: 'error.main', fontSize: 13 }}>{dlError}</Stack>
        ) : null}
      </Stack>
    </Alert>
  );
}
