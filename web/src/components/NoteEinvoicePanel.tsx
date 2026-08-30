import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelCreditNoteEinvoice,
  cancelDebitNoteEinvoice,
  prepareCreditNoteEinvoice,
  prepareDebitNoteEinvoice,
  submitCreditNoteEinvoice,
  submitDebitNoteEinvoice,
} from '@/api/resources';
import { isEinvoiceSubmitEnabled } from '@/config/features';
import { t } from '@/i18n';
import type { SalesCreditNote, SalesDebitNote } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type NoteKind = 'credit' | 'debit';

type Props = {
  kind: NoteKind;
  note: SalesCreditNote | SalesDebitNote;
  onError?: (message: string) => void;
  onMessage?: (message: string) => void;
};

function statusColor(status?: string): 'default' | 'success' | 'warning' | 'error' | 'info' {
  switch (status) {
    case 'READY':
      return 'info';
    case 'GENERATED':
      return 'success';
    case 'FAILED':
      return 'error';
    case 'CANCELLED':
      return 'warning';
    default:
      return 'default';
  }
}

export function NoteEinvoicePanel({ kind, note, onError, onMessage }: Props) {
  const qc = useQueryClient();
  const [lastPayload, setLastPayload] = useState<unknown>(null);
  const queryKey = kind === 'credit' ? 'sales-credit-notes' : 'sales-debit-notes';

  useEffect(() => {
    setLastPayload(null);
  }, [note.id]);

  const invalidate = () => void qc.invalidateQueries({ queryKey: [queryKey, note.id] });

  const prepareMutation = useMutation({
    mutationFn: () =>
      kind === 'credit' ? prepareCreditNoteEinvoice(note.id) : prepareDebitNoteEinvoice(note.id),
    onSuccess: (res) => {
      setLastPayload(res.payload ?? null);
      onMessage?.('e-Invoice payload ready');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const submitMutation = useMutation({
    mutationFn: () =>
      kind === 'credit' ? submitCreditNoteEinvoice(note.id) : submitDebitNoteEinvoice(note.id),
    onSuccess: () => {
      onMessage?.('e-Invoice submitted (sandbox)');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      kind === 'credit' ? cancelCreditNoteEinvoice(note.id) : cancelDebitNoteEinvoice(note.id),
    onSuccess: () => {
      onMessage?.('e-Invoice cancelled');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const generated = note.einvoiceStatus === 'GENERATED';
  const canSubmit = isEinvoiceSubmitEnabled();
  const base = note.number ?? `${kind}-note-${note.id}`;

  return (
    <Paper sx={{ p: 2 }} data-testid="note-einvoice-panel">
      <Typography variant="h6" sx={{ mb: 1 }}>
        Credit/debit note e-Invoice
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('common.sandboxGstnBanner')}. Prepare JSON for portal filing, or submit a sandbox IRN
        with the buttons below.
      </Alert>
      <Box>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">e-Invoice</Typography>
          <Chip
            size="small"
            label={t(`status.${note.einvoiceStatus ?? 'NONE'}`)}
            color={statusColor(note.einvoiceStatus)}
          />
        </Stack>
        {note.einvoiceError ? <HelpErrorAlert message={note.einvoiceError} sx={{ mb: 1 }} /> : null}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            variant="outlined"
            size="small"
            disabled={prepareMutation.isPending}
            onClick={() => prepareMutation.mutate()}
          >
            Prepare payload
          </Button>
          {canSubmit ? (
            <Button
              variant="contained"
              size="small"
              disabled={submitMutation.isPending || generated}
              onClick={() => submitMutation.mutate()}
            >
              Submit (sandbox)
            </Button>
          ) : null}
          {generated ? (
            <Button
              variant="outlined"
              color="warning"
              size="small"
              disabled={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
            >
              Cancel IRN
            </Button>
          ) : null}
          {lastPayload ? (
            <Button
              variant="outlined"
              size="small"
              onClick={() => {
                const blob = new Blob([JSON.stringify(lastPayload, null, 2)], { type: 'application/json' });
                triggerBlobDownload(blob, `${base}_einvoice.json`);
              }}
            >
              Download JSON
            </Button>
          ) : null}
        </Stack>
        {note.irn ? (
          <Typography variant="body2" sx={{ mt: 1 }}>
            IRN: {note.irn}
          </Typography>
        ) : null}
      </Box>
    </Paper>
  );
}
