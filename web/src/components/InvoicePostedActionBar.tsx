import { useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createInvoicePublicLink,
  downloadInvoicePdf,
  getCompany,
  prepareInvoiceEinvoice,
  prepareInvoiceEway,
  revokeInvoicePublicLink,
  submitInvoiceEinvoice,
  submitInvoiceEway,
  updateSalesInvoice,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { isEinvoiceSubmitEnabled, isEwaySubmitEnabled } from '@/config/features';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { hasLiveIrn } from '@/utils/einvoiceLock';
import { toNumber } from '@/utils/money';
import { canCreatePayments } from '@/utils/permissions';

type Props = {
  invoice: SalesInvoice;
  customerGstin?: string;
  onShareWhatsApp: () => void;
  onShareEmail: () => void;
  onRecordPayment: () => void;
  onMessage: (message: string) => void;
  onError: (err: unknown) => void;
};

type BarAction = {
  key: string;
  label: string;
  disabled?: boolean;
  reason?: string;
  onClick: (anchor: HTMLElement) => void;
};

function usePhoneLayout(): boolean {
  const [phone, setPhone] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    let mq: MediaQueryList;
    try {
      mq = window.matchMedia('(max-width:600px)');
    } catch {
      return;
    }
    const apply = () => setPhone(Boolean(mq.matches));
    apply();
    mq.addEventListener?.('change', apply);
    return () => mq.removeEventListener?.('change', apply);
  }, []);
  return phone;
}

function isServiceOnly(invoice: SalesInvoice): boolean {
  const items = invoice.items ?? [];
  if (!items.length) return false;
  return items.every((item) => {
    const extra = item as { productType?: string; isService?: boolean };
    if (extra.productType === 'SERVICE' || extra.isService === true) return true;
    return String(item.hsnCode || '').trim().startsWith('99');
  });
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  triggerBlobDownload(blob, filename);
}

export function InvoicePostedActionBar({
  invoice,
  customerGstin,
  onShareWhatsApp,
  onShareEmail,
  onRecordPayment,
  onMessage,
  onError,
}: Props) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const phone = usePhoneLayout();
  const [shareAnchor, setShareAnchor] = useState<HTMLElement | null>(null);
  const [overflowAnchor, setOverflowAnchor] = useState<HTMLElement | null>(null);
  const [manualUrl, setManualUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ewayOpen, setEwayOpen] = useState(false);
  const [distance, setDistance] = useState('');
  const [vehicle, setVehicle] = useState('');
  const [transporter, setTransporter] = useState('');

  const owner = user?.role === 'OWNER';
  const company = companyQuery.data ?? user?.company;
  const einvoiceFlagKnown = company != null && Object.prototype.hasOwnProperty.call(company, 'einvoiceEnabled');
  const gstInvoice = invoice.invoiceType === 'GST' || invoice.invoiceType === 'TAX';
  const nonGst = invoice.invoiceType === 'NON_GST';
  const b2b = Boolean((customerGstin || '').trim());
  const completed = invoice.status === 'COMPLETED';
  const showEinvoice =
    completed && gstInvoice && b2b && (!einvoiceFlagKnown || company?.einvoiceEnabled === true);
  const threshold =
    company?.ewayThresholdAmount != null && String(company.ewayThresholdAmount).trim() !== ''
      ? toNumber(company.ewayThresholdAmount)
      : 50000;
  const showEway =
    completed &&
    !nonGst &&
    !isServiceOnly(invoice) &&
    toNumber(invoice.grandTotal) > (threshold || 50000);
  const showPay = completed && toNumber(invoice.balance) > 0.01 && canCreatePayments(user);
  const liveEinvoice = isEinvoiceSubmitEnabled();
  const liveEway = isEwaySubmitEnabled();
  const einvoiceDone = hasLiveIrn(invoice) || invoice.einvoiceStatus === 'GENERATED';
  const ewayDone = invoice.ewayStatus === 'GENERATED';
  const base = invoice.number ?? `invoice-${invoice.id}`;

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['sales-invoice', invoice.id] });
  };

  const run = async (work: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await work();
    } catch (err) {
      onError(err);
    } finally {
      setBusy(false);
    }
  };

  const downloadPdf = () =>
    run(async () => {
      const blob = await downloadInvoicePdf(invoice.id, { copy: 'ORIGINAL' });
      triggerBlobDownload(blob, `${base}.pdf`);
    });

  const printPdf = () =>
    run(async () => {
      const blob = await downloadInvoicePdf(invoice.id, { copy: 'ORIGINAL' });
      printBlob(blob);
    });

  const generateEinvoice = () =>
    run(async () => {
      if (einvoiceDone) return;
      if (liveEinvoice) {
        await submitInvoiceEinvoice(invoice.id);
        onMessage(t('einvoice.submittedSandbox'));
      } else {
        const res = await prepareInvoiceEinvoice(invoice.id);
        if (res.payload) downloadJson(`${base}_einvoice.json`, res.payload);
        onMessage(t('einvoice.payloadReady'));
      }
      refresh();
    });

  const generateEway = (values?: { distance: string; vehicle: string; transporter: string }) =>
    run(async () => {
      if (ewayDone) return;
      const km = (values?.distance ?? String(invoice.transportDistanceKm ?? '')).trim();
      const vehicleNo = (values?.vehicle ?? invoice.vehicleNumber ?? '').trim();
      const transporterName = (values?.transporter ?? invoice.transporterName ?? '').trim();
      if (!km) {
        setDistance('');
        setVehicle(vehicleNo);
        setTransporter(transporterName);
        setEwayOpen(true);
        return;
      }
      await updateSalesInvoice(invoice.id, {
        vehicleNumber: vehicleNo,
        transporterName,
        transporterId: invoice.transporterId || '',
        transportDistanceKm: km,
      });
      const payload = {
        vehicleNumber: vehicleNo || undefined,
        transporterName: transporterName || undefined,
        transporterId: invoice.transporterId || undefined,
        transportDistanceKm: km,
      };
      if (liveEway) {
        await submitInvoiceEway(invoice.id, payload);
        onMessage(t('einvoice.ewaySubmittedSandbox'));
      } else {
        const res = await prepareInvoiceEway(invoice.id, payload);
        if (res.payload) downloadJson(`${base}_eway.json`, res.payload);
        onMessage(t('einvoice.ewayPayloadReady'));
      }
      setEwayOpen(false);
      refresh();
    });

  const openEway = () => {
    const distanceEmpty = !String(invoice.transportDistanceKm ?? '').trim();
    const partyEmpty = !(invoice.vehicleNumber || '').trim() && !(invoice.transporterName || '').trim() && !(invoice.transporterId || '').trim();
    if (distanceEmpty || partyEmpty) {
      setDistance(String(invoice.transportDistanceKm ?? ''));
      setVehicle(invoice.vehicleNumber ?? '');
      setTransporter(invoice.transporterName ?? '');
      setEwayOpen(true);
      return;
    }
    void generateEway();
  };

  const copyLink = () =>
    run(async () => {
      const { url } = await createInvoicePublicLink(invoice.id);
      if (!url) throw new Error(t('invoiceDetail.publicUnavailable'));
      try {
        await navigator.clipboard.writeText(url);
        setManualUrl(null);
        onMessage(t('common.linkCopied'));
      } catch {
        setManualUrl(url);
      }
    });

  const revokeLink = () =>
    run(async () => {
      await revokeInvoicePublicLink(invoice.id);
      setManualUrl(null);
      onMessage(t('common.linkRevoked'));
    });

  const actions: BarAction[] = [];
  if (showEinvoice) {
    const blocked = (liveEinvoice && !owner) || einvoiceDone;
    actions.push({
      key: 'einvoice',
      label: einvoiceDone
        ? t('invoiceDetail.irnReady', { irn: invoice.irn || invoice.ackNo || '' })
        : t('invoiceDetail.generateEinvoice'),
      disabled: blocked || busy,
      reason: liveEinvoice && !owner ? t('invoiceDetail.einvoiceOwnerOnly') : undefined,
      onClick: () => {
        if (!blocked) void generateEinvoice();
      },
    });
  }
  actions.push(
    { key: 'download', label: t('invoiceDetail.downloadPdf'), disabled: busy, onClick: () => void downloadPdf() },
    { key: 'print', label: t('invoiceDetail.printPdf'), disabled: busy, onClick: () => void printPdf() },
    { key: 'share', label: t('common.share'), onClick: (anchor) => setShareAnchor(anchor) },
  );
  if (showEway) {
    const blocked = (liveEway && !owner) || ewayDone;
    actions.push({
      key: 'eway',
      label: ewayDone
        ? t('invoiceDetail.ewayBillNumber', { number: invoice.ewayBillNo || '' })
        : t('invoiceDetail.generateEway'),
      disabled: blocked || busy,
      reason: liveEway && !owner ? t('invoiceDetail.ewayOwnerOnly') : undefined,
      onClick: () => {
        if (!blocked) openEway();
      },
    });
  }
  if (showPay) {
    actions.push({
      key: 'pay',
      label: t('invoiceDetail.recordPayment'),
      onClick: () => onRecordPayment(),
    });
  }

  const [primary, ...rest] = actions;
  const visible = phone && primary ? [primary] : actions;
  const overflow = phone ? rest : [];

  return (
    <>
      {visible.map((action, index) => (
        <Button
          key={action.key}
          variant={index === 0 ? 'contained' : 'outlined'}
          disabled={action.disabled}
          title={action.reason}
          onClick={(e) => action.onClick(e.currentTarget)}
        >
          {action.label}
        </Button>
      ))}
      {overflow.length ? (
        <Button variant="outlined" onClick={(e) => setOverflowAnchor(e.currentTarget)}>
          {t('cog.moreActions')}
        </Button>
      ) : null}
      {actions
        .filter((action) => action.disabled && action.reason)
        .map((action) => (
          <Typography key={`${action.key}-reason`} variant="caption" color="text.secondary" sx={{ flexBasis: '100%' }}>
            {action.reason}
          </Typography>
        ))}
      {manualUrl ? (
        <TextField
          size="small"
          fullWidth
          label={t('common.copyLink')}
          value={manualUrl}
          InputProps={{ readOnly: true }}
          sx={{ flexBasis: '100%' }}
        />
      ) : null}
      <Menu anchorEl={overflowAnchor} open={Boolean(overflowAnchor)} onClose={() => setOverflowAnchor(null)}>
        {overflow.map((action) => (
          <MenuItem
            key={action.key}
            disabled={action.disabled}
            onClick={(e) => {
              const anchor = overflowAnchor ?? e.currentTarget;
              setOverflowAnchor(null);
              action.onClick(anchor);
            }}
          >
            <ListItemText primary={action.label} secondary={action.reason} />
          </MenuItem>
        ))}
      </Menu>
      <Menu anchorEl={shareAnchor} open={Boolean(shareAnchor)} onClose={() => setShareAnchor(null)}>
        <MenuItem
          onClick={() => {
            setShareAnchor(null);
            onShareWhatsApp();
          }}
        >
          {t('common.whatsapp')}
        </MenuItem>
        <MenuItem
          onClick={() => {
            setShareAnchor(null);
            void copyLink();
          }}
        >
          <ListItemText primary={t('common.copyLink')} secondary={t('common.publicLinkStaffWarning')} />
        </MenuItem>
        <MenuItem
          onClick={() => {
            setShareAnchor(null);
            onShareEmail();
          }}
        >
          {t('common.email')}
        </MenuItem>
        <MenuItem
          onClick={() => {
            setShareAnchor(null);
            void revokeLink();
          }}
        >
          {t('common.revokeLink')}
        </MenuItem>
      </Menu>
      <Dialog open={ewayOpen} onClose={() => setEwayOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('invoiceDetail.ewayDistanceTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('invoiceDetail.ewayDistanceHelp')}
            </Typography>
            <TextField
              autoFocus
              label={t('invoiceDetail.distanceKm')}
              value={distance}
              onChange={(e) => setDistance(e.target.value)}
              required
            />
            <TextField
              label={t('invoiceDetail.vehicleNo')}
              value={vehicle}
              onChange={(e) => setVehicle(e.target.value)}
            />
            <TextField
              label={t('invoiceDetail.transporterName')}
              value={transporter}
              onChange={(e) => setTransporter(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEwayOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!distance.trim() || busy}
            onClick={() => void generateEway({ distance, vehicle, transporter })}
          >
            {t('invoiceDetail.generateEway')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
