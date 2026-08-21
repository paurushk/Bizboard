import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelChallanEway,
  markChallanEwayGenerated,
  prepareChallanEway,
  submitChallanEway,
} from '@/api/resources';
import { isEinvoiceSubmitEnabled } from '@/config/features';
import { t } from '@/i18n';
import type { DeliveryChallan } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';

type Props = {
  challan: DeliveryChallan;
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

export function ChallanEwayPanel({ challan, onError, onMessage }: Props) {
  const qc = useQueryClient();
  const [ewayBillNo, setEwayBillNo] = useState(challan.ewayBillNo ?? '');
  const [lastPayload, setLastPayload] = useState<unknown>(null);

  const prepareMutation = useMutation({
    mutationFn: () => prepareChallanEway(challan.id),
    onSuccess: (res) => {
      setLastPayload(res.payload ?? null);
      onMessage?.('e-Way payload ready');
      void qc.invalidateQueries({ queryKey: ['delivery-challans', challan.id] });
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const markMutation = useMutation({
    mutationFn: () => markChallanEwayGenerated(challan.id, { ewayBillNo }),
    onSuccess: () => {
      onMessage?.('e-Way bill marked as generated');
      void qc.invalidateQueries({ queryKey: ['delivery-challans', challan.id] });
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const submitMutation = useMutation({
    mutationFn: () => submitChallanEway(challan.id),
    onSuccess: () => {
      onMessage?.('e-Way bill submitted (sandbox)');
      void qc.invalidateQueries({ queryKey: ['delivery-challans', challan.id] });
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelChallanEway(challan.id),
    onSuccess: () => {
      onMessage?.('e-Way bill cancelled');
      void qc.invalidateQueries({ queryKey: ['delivery-challans', challan.id] });
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const base = challan.number ?? `challan-${challan.id}`;
  const ewayGenerated = challan.ewayStatus === 'GENERATED';

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">e-Way bill</Typography>
        <Chip
          size="small"
          label={t(`status.${challan.ewayStatus ?? 'NONE'}`)}
          color={statusColor(challan.ewayStatus)}
        />
      </Stack>
      <Alert severity="info" sx={{ mb: 2 }}>
        Sandbox submit is available for testing. Use Prepare to download JSON for manual portal
        filing, or Submit (sandbox) to simulate e-Way generation. {t('common.sandboxGstnBanner')}
      </Alert>
      {challan.ewayError ? <Alert severity="error" sx={{ mb: 1 }}>{challan.ewayError}</Alert> : null}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        <Button variant="outlined" size="small" disabled={prepareMutation.isPending} onClick={() => prepareMutation.mutate()}>
          Prepare payload
        </Button>
        {isEinvoiceSubmitEnabled() ? (
          <Button
            variant="contained"
            size="small"
            disabled={submitMutation.isPending || ewayGenerated}
            onClick={() => submitMutation.mutate()}
          >
            Submit (sandbox)
          </Button>
        ) : null}
        {ewayGenerated ? (
          <Button
            variant="outlined"
            color="warning"
            size="small"
            disabled={cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
          >
            Cancel
          </Button>
        ) : null}
        {lastPayload ? (
          <Button
            variant="outlined"
            size="small"
            onClick={() => {
              const blob = new Blob([JSON.stringify(lastPayload, null, 2)], { type: 'application/json' });
              triggerBlobDownload(blob, `${base}_eway.json`);
            }}
          >
            Download JSON
          </Button>
        ) : null}
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          label="e-Way bill no"
          size="small"
          value={ewayBillNo}
          onChange={(e) => setEwayBillNo(e.target.value)}
          fullWidth
        />
        <Button
          variant="contained"
          size="small"
          disabled={!ewayBillNo.trim() || markMutation.isPending}
          onClick={() => markMutation.mutate()}
        >
          Save e-Way
        </Button>
      </Stack>
      <Box sx={{ mt: 1 }}>
        <Typography variant="caption" color="text.secondary">
          Vehicle: {challan.vehicleNumber || '—'} · Transporter: {challan.transporterName || '—'}
        </Typography>
      </Box>
    </Paper>
  );
}
