import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelInvoiceEinvoice,
  cancelInvoiceEway,
  markInvoiceEinvoiceGenerated,
  markInvoiceEwayGenerated,
  prepareInvoiceEinvoice,
  prepareInvoiceEway,
  submitInvoiceEinvoice,
  submitInvoiceEway,
} from '@/api/resources';
import { isEinvoiceSubmitEnabled, isEwaySubmitEnabled } from '@/config/features';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type Props = {
  invoice: SalesInvoice;
  onError?: (message: string) => void;
  onMessage?: (message: string) => void;
  transport?: {
    vehicleNumber?: string;
    transporterName?: string;
    transporterId?: string;
    transportDistanceKm?: string;
  };
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

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  triggerBlobDownload(blob, filename);
}

export function EinvoiceEwayPanel({ invoice, onError, onMessage, transport }: Props) {
  const qc = useQueryClient();
  const [irn, setIrn] = useState(invoice.irn ?? '');
  const [ackNo, setAckNo] = useState(invoice.ackNo ?? '');
  const [manualReason, setManualReason] = useState('');
  const [ewayBillNo, setEwayBillNo] = useState(invoice.ewayBillNo ?? '');
  const transportFromParent = transport != null;
  const [vehicleNumber, setVehicleNumber] = useState(
    transport?.vehicleNumber ?? invoice.vehicleNumber ?? '',
  );
  const [transporterName, setTransporterName] = useState(
    transport?.transporterName ?? invoice.transporterName ?? '',
  );
  const [transporterId, setTransporterId] = useState(
    transport?.transporterId ?? invoice.transporterId ?? '',
  );
  const [transportDistanceKm, setTransportDistanceKm] = useState(
    transport?.transportDistanceKm ?? String(invoice.transportDistanceKm ?? ''),
  );
  const [cnlRsn, setCnlRsn] = useState('1');
  const [cnlRem, setCnlRem] = useState('');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [lastEwayPayload, setLastEwayPayload] = useState<unknown>(null);
  const [lastEinvoicePayload, setLastEinvoicePayload] = useState<unknown>(null);

  useEffect(() => {
    setIrn(invoice.irn ?? '');
    setAckNo(invoice.ackNo ?? '');
    setEwayBillNo(invoice.ewayBillNo ?? '');
  }, [invoice.irn, invoice.ackNo, invoice.ewayBillNo]);

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['sales-invoice', invoice.id] });

  const resolvedTransport = transportFromParent
    ? {
        vehicleNumber: transport.vehicleNumber ?? '',
        transporterName: transport.transporterName ?? '',
        transporterId: transport.transporterId ?? '',
        transportDistanceKm: transport.transportDistanceKm ?? '',
      }
    : {
        vehicleNumber,
        transporterName,
        transporterId,
        transportDistanceKm,
      };

  const ewayPayload = () => ({
    vehicleNumber: resolvedTransport.vehicleNumber.trim() || undefined,
    transporterName: resolvedTransport.transporterName.trim() || undefined,
    transporterId: resolvedTransport.transporterId.trim() || undefined,
    transportDistanceKm: resolvedTransport.transportDistanceKm.trim() || undefined,
  });

  const prepareEinvoiceMutation = useMutation({
    mutationFn: () => prepareInvoiceEinvoice(invoice.id),
    onSuccess: (res) => {
      setLastEinvoicePayload(res.payload ?? null);
      onMessage?.('e-Invoice payload ready');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const submitEinvoiceMutation = useMutation({
    mutationFn: () => submitInvoiceEinvoice(invoice.id),
    onSuccess: () => {
      onMessage?.('e-Invoice submitted (sandbox)');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const cancelEinvoiceMutation = useMutation({
    mutationFn: () => cancelInvoiceEinvoice(invoice.id, { cnlRsn, cnlRem: cnlRem.trim() }),
    onSuccess: () => {
      onMessage?.(t('einvoice.cancelled'));
      setCancelOpen(false);
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const markEinvoiceMutation = useMutation({
    mutationFn: () => markInvoiceEinvoiceGenerated(invoice.id, { irn, ackNo, reason: manualReason.trim() }),
    onSuccess: () => {
      onMessage?.('e-Invoice marked as generated');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const prepareEwayMutation = useMutation({
    mutationFn: () => prepareInvoiceEway(invoice.id, ewayPayload()),
    onSuccess: (res) => {
      setLastEwayPayload(res.payload ?? null);
      onMessage?.('e-Way payload ready');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const submitEwayMutation = useMutation({
    mutationFn: () => submitInvoiceEway(invoice.id, ewayPayload()),
    onSuccess: () => {
      onMessage?.('e-Way bill submitted (sandbox)');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const cancelEwayMutation = useMutation({
    mutationFn: () => cancelInvoiceEway(invoice.id),
    onSuccess: () => {
      onMessage?.('e-Way bill cancelled');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const markEwayMutation = useMutation({
    mutationFn: () => markInvoiceEwayGenerated(invoice.id, { ewayBillNo, reason: manualReason.trim() }),
    onSuccess: () => {
      onMessage?.('e-Way bill marked as generated');
      invalidate();
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const base = invoice.number ?? `invoice-${invoice.id}`;
  const einvoiceGenerated = invoice.einvoiceStatus === 'GENERATED';
  const ewayGenerated = invoice.ewayStatus === 'GENERATED';
  const canSubmitEinvoice = isEinvoiceSubmitEnabled();
  const canSubmitEway = isEwaySubmitEnabled();

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>
        e-Invoice / e-Way
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('common.sandboxGstnBanner')}. Sandbox submit is available for testing.
        Use Prepare to download JSON for manual portal filing, or Submit (sandbox)
        to simulate IRN / e-Way generation.
      </Alert>

      <Stack spacing={2}>
        <Box>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle2">e-Invoice</Typography>
            <Chip
              size="small"
              label={t(`status.${invoice.einvoiceStatus ?? 'NONE'}`)}
              color={statusColor(invoice.einvoiceStatus)}
            />
          </Stack>
          {invoice.einvoiceError ? <HelpErrorAlert message={invoice.einvoiceError} sx={{ mb: 1 }} /> : null}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
            <Button
              variant="outlined"
              size="small"
              disabled={prepareEinvoiceMutation.isPending}
              onClick={() => prepareEinvoiceMutation.mutate()}
            >
              Prepare payload
            </Button>
            {canSubmitEinvoice ? (
              <Button
                variant="contained"
                size="small"
                disabled={submitEinvoiceMutation.isPending || einvoiceGenerated}
                onClick={() => submitEinvoiceMutation.mutate()}
              >
                Submit (sandbox)
              </Button>
            ) : null}
            {einvoiceGenerated ? (
              <Button
                variant="outlined"
                color="warning"
                size="small"
                disabled={cancelEinvoiceMutation.isPending}
                onClick={() => setCancelOpen(true)}
              >
                {t('einvoice.cancel')}
              </Button>
            ) : null}
            {lastEinvoicePayload ? (
              <Button
                variant="outlined"
                size="small"
                onClick={() => downloadJson(`${base}_einvoice.json`, lastEinvoicePayload)}
              >
                Download JSON
              </Button>
            ) : null}
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField label="IRN" size="small" value={irn} onChange={(e) => setIrn(e.target.value)} fullWidth />
            <TextField label="Ack No" size="small" value={ackNo} onChange={(e) => setAckNo(e.target.value)} fullWidth />
          </Stack>
          <TextField
            label="Audit reason"
            size="small"
            value={manualReason}
            onChange={(e) => setManualReason(e.target.value)}
            fullWidth
            sx={{ mt: 1 }}
            helperText="Required for manual IRN / e-Way attestation (Owner only)."
          />
          <Button
            variant="contained"
            size="small"
            sx={{ mt: 1 }}
            disabled={!irn.trim() || !ackNo.trim() || !manualReason.trim() || markEinvoiceMutation.isPending}
            onClick={() => markEinvoiceMutation.mutate()}
          >
            Save IRN
          </Button>
          {invoice.irn ? (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              Saved IRN: {invoice.irn}
            </Typography>
          ) : null}
        </Box>

        <Divider />

        <Box>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle2">e-Way bill</Typography>
            <Chip
              size="small"
              label={t(`status.${invoice.ewayStatus ?? 'NONE'}`)}
              color={statusColor(invoice.ewayStatus)}
            />
          </Stack>
          {invoice.ewayError ? <HelpErrorAlert message={invoice.ewayError} sx={{ mb: 1 }} /> : null}
          {transportFromParent ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Vehicle: {resolvedTransport.vehicleNumber || '—'} · Transporter:{' '}
              {resolvedTransport.transporterName || '—'}
              {resolvedTransport.transporterId
                ? ` (${resolvedTransport.transporterId})`
                : ''}
              {resolvedTransport.transportDistanceKm
                ? ` · ${resolvedTransport.transportDistanceKm} km`
                : ''}
            </Typography>
          ) : (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1 }}>
              <TextField
                label="Vehicle no"
                size="small"
                value={vehicleNumber}
                onChange={(e) => setVehicleNumber(e.target.value)}
                fullWidth
              />
              <TextField
                label="Transporter"
                size="small"
                value={transporterName}
                onChange={(e) => setTransporterName(e.target.value)}
                fullWidth
              />
              <TextField
                label="Transporter ID"
                size="small"
                value={transporterId}
                onChange={(e) => setTransporterId(e.target.value)}
                fullWidth
              />
              <TextField
                label="Distance (km)"
                size="small"
                value={transportDistanceKm}
                onChange={(e) => setTransportDistanceKm(e.target.value)}
                fullWidth
              />
            </Stack>
          )}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
            <Button
              variant="outlined"
              size="small"
              disabled={prepareEwayMutation.isPending}
              onClick={() => prepareEwayMutation.mutate()}
            >
              Prepare payload
            </Button>
            {canSubmitEway ? (
              <Button
                variant="contained"
                size="small"
                disabled={submitEwayMutation.isPending || ewayGenerated}
                onClick={() => submitEwayMutation.mutate()}
              >
                Submit (sandbox)
              </Button>
            ) : null}
            {ewayGenerated ? (
              <Button
                variant="outlined"
                color="warning"
                size="small"
                disabled={cancelEwayMutation.isPending}
                onClick={() => cancelEwayMutation.mutate()}
              >
                Cancel
              </Button>
            ) : null}
            {lastEwayPayload ? (
              <Button
                variant="outlined"
                size="small"
                onClick={() => downloadJson(`${base}_eway.json`, lastEwayPayload)}
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
              disabled={!ewayBillNo.trim() || !manualReason.trim() || markEwayMutation.isPending}
              onClick={() => markEwayMutation.mutate()}
            >
              Save e-Way
            </Button>
          </Stack>
        </Box>
      </Stack>
      <Dialog open={cancelOpen} onClose={() => setCancelOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('einvoice.cancelTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('einvoice.cancelReason')}
              size="small"
              value={cnlRsn}
              onChange={(e) => setCnlRsn(e.target.value)}
            >
              <MenuItem value="1">{t('einvoice.cnl1')}</MenuItem>
              <MenuItem value="2">{t('einvoice.cnl2')}</MenuItem>
              <MenuItem value="3">{t('einvoice.cnl3')}</MenuItem>
              <MenuItem value="4">{t('einvoice.cnl4')}</MenuItem>
            </TextField>
            <TextField
              label={t('einvoice.cancelRemarks')}
              size="small"
              value={cnlRem}
              onChange={(e) => setCnlRem(e.target.value)}
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!cnlRem.trim() || cancelEinvoiceMutation.isPending}
            onClick={() => cancelEinvoiceMutation.mutate()}
          >
            {t('einvoice.cancel')}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
