import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { apiClient, getErrorMessage } from '@/api/client';
import { setDeliveryRouteStopStatus } from '@/api/resources';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { capturePodPhoto } from '@/lib/native';
import { queuePodPhoto } from '@/offline/photoOutbox';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import {
  RECORDED_STATUSES,
  STOP_OUTCOMES,
  cameBack,
  returnedLinesPayload,
  validateOutcome,
  type OutcomeFormValues,
  type RouteStop,
  type StopOutcome,
} from './routeTypes';

const TOUCH = { minHeight: 44 } as const;

interface Props {
  routeId: number;
  routeStatus: string;
  stop: RouteStop;
  canWrite: boolean;
  canLinkReceipt: boolean;
  onChanged: () => void;
  onError: (message: string | null) => void;
  onLinkReceipt: (stop: RouteStop) => void;
  triggerBlobDownload: (blob: Blob, filename: string) => void;
}

const EMPTY_FORM: OutcomeFormValues = {
  outcome: 'DELIVERED',
  receivedBy: '',
  cash: '',
  upi: '',
  upiReference: '',
  reason: '',
  note: '',
  byOffice: true,
  code: '',
  returned: {},
  someCameBack: false,
};

/**
 * One stop, with everything the office needs to act on it: who and where, what the bill is and what to
 * collect, and a single form to record the outcome. The page used to share one "received by" and one
 * code box above a list of drop-downs.
 */
export function StopCard({
  routeId,
  routeStatus,
  stop,
  canWrite,
  canLinkReceipt,
  onChanged,
  onError,
  onLinkReceipt,
  triggerBlobDownload,
}: Props) {
  const status = stop.status ?? 'PENDING';
  const recorded = RECORDED_STATUSES.has(status);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<OutcomeFormValues>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const set = <K extends keyof OutcomeFormValues>(key: K, value: OutcomeFormValues[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const canRecord = canWrite && routeStatus === 'IN_TRANSIT';
  const showForm = canRecord && (!recorded || editing);
  const bill = stop.bill ?? null;
  const collected = toNumber(stop.collectedCash) + toNumber(stop.collectedUpi);

  const save = useMutation({
    mutationFn: async () => {
      const problem = validateOutcome(form, { changing: recorded, returnable: stop.returnableLines });
      if (problem) throw new Error(t(problem));
      let podNote = form.note.trim();
      if (form.outcome === 'DELIVERED' && !form.byOffice) {
        const photo = await capturePodPhoto();
        if (photo) {
          await queuePodPhoto(`${routeId}-${stop.id}`, photo, { routeId, stopId: stop.id, receivedByName: form.receivedBy });
          podNote = podNote || 'photo';
        }
      }
      return setDeliveryRouteStopStatus(routeId, stop.id, form.outcome, {
        completionSource: form.byOffice ? 'OFFICE' : 'PHONE',
        otp: !form.byOffice && form.code ? form.code : undefined,
        podNote: podNote || undefined,
        receivedByName: form.outcome === 'DELIVERED' ? form.receivedBy.trim() : undefined,
        collectedCash: form.outcome === 'DELIVERED' && form.cash.trim() ? form.cash.trim() : undefined,
        collectedUpi: form.outcome === 'DELIVERED' && form.upi.trim() ? form.upi.trim() : undefined,
        upiReference: form.outcome === 'DELIVERED' && form.upi.trim() ? form.upiReference.trim() : undefined,
        reason: recorded ? form.reason.trim() : undefined,
        returnedLines: returnedLinesPayload(form, stop.returnableLines),
      });
    },
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setEditing(false);
      setFormError(null);
      onError(null);
      onChanged();
    },
    onError: (err) => {
      const message = err instanceof Error && !('response' in err) ? err.message : getErrorMessage(err);
      setFormError(message);
      onError(null);
    },
  });

  const billText = bill?.billStatus ? t(`routes.bill.${bill.billStatus}`) : null;
  const returnable = stop.returnableLines ?? [];
  // Delivered, but nothing has been billed for it yet: the office may want to invoice it now.
  const deliveredNotBilled =
    status === 'DELIVERED' && (bill?.billStatus === 'order_only' || bill?.billStatus === 'challan');

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid={`stop-${stop.id}`}>
      <Stack spacing={1.25}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="subtitle2">#{stop.sequence ?? ''}</Typography>
            <Link component={RouterLink} to={`/sales/orders/${stop.salesOrder}`} underline="hover" sx={{ ...TOUCH, display: 'inline-flex', alignItems: 'center' }}>
              {stop.orderNumber ?? stop.salesOrder}
            </Link>
            <Typography variant="body1" fontWeight={600}>{stop.customerName ?? '—'}</Typography>
          </Stack>
          <StatusChip tone={documentStatusTone(status)} labelKey={statusLabelKey(status)} />
        </Stack>

        {stop.customerPhone ? (
          <Link href={`tel:${stop.customerPhone}`} underline="hover" sx={{ ...TOUCH, display: 'inline-flex', alignItems: 'center' }}>
            {stop.customerPhone}
          </Link>
        ) : (
          <Typography variant="body2" color="text.secondary">{t('routes.noPhone')}</Typography>
        )}
        <Typography variant="body2" color={stop.deliveryAddress ? 'text.primary' : 'warning.main'}>
          {stop.deliveryAddress || t('routes.noAddress')}
        </Typography>

        {bill ? (
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <Typography variant="body2">{t('routes.orderTotal')}: <b>{formatMoney(toNumber(bill.orderTotal))}</b></Typography>
            {billText ? <Typography variant="body2">{t('routes.billLabel')}: {billText}</Typography> : null}
            {bill.onCredit ? (
              <Typography variant="body2">{t('routes.onCredit', { days: bill.paymentTermsDays ?? 0 })}</Typography>
            ) : (
              <Typography variant="body2">{t('routes.toCollect')}: <b>{formatMoney(toNumber(bill.amountToCollect))}</b></Typography>
            )}
            {bill.advanceAvailable && toNumber(bill.advanceAvailable) > 0 ? (
              <Typography variant="body2">{t('routes.advanceOnAccount')}: {formatMoney(toNumber(bill.advanceAvailable))}</Typography>
            ) : null}
            {(bill.invoices ?? []).map((inv) => (
              <Link key={inv.id} component={RouterLink} to={`/sales/history/${inv.id}`} underline="hover" variant="body2">
                {inv.number || `#${inv.id}`}
              </Link>
            ))}
          </Stack>
        ) : null}

        {stop.activeInvoice ? (
          <Alert severity="warning">
            {t('routes.invoiceStillActive', { number: stop.activeInvoice.number || `#${stop.activeInvoice.id}` })}{' '}
            <Link component={RouterLink} to={`/sales/history/${stop.activeInvoice.id}`}>
              {t('routes.openInvoice')}
            </Link>
          </Alert>
        ) : null}

        {deliveredNotBilled ? (
          <Alert severity="info">
            {t('routes.deliveredNotBilled')}{' '}
            <Link component={RouterLink} to={`/sales/orders/${stop.salesOrder}`}>
              {t('routes.openOrder')}
            </Link>
          </Alert>
        ) : null}

        {recorded ? (
          <Stack spacing={0.5}>
            {status === 'DELIVERED' ? (
              <Typography variant="body2">
                {t('routes.receivedBy')}: <b>{stop.receivedByName || '—'}</b>
                {stop.completionSource === 'OFFICE' ? ` · ${t('routes.recordedByOffice')}` : ''}
              </Typography>
            ) : null}
            {collected > 0 ? (
              <Typography variant="body2">
                {t('routes.collected')}: {formatMoney(toNumber(stop.collectedCash))} {t('routes.cash')}
                {toNumber(stop.collectedUpi) > 0
                  ? ` + ${formatMoney(toNumber(stop.collectedUpi))} UPI (${stop.upiReference || '—'})`
                  : ''}
              </Typography>
            ) : null}
            {stop.notes ? (
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>{stop.notes}</Typography>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {status === 'DELIVERED' ? (
                <Button
                  size="small"
                  sx={TOUCH}
                  onClick={() => {
                    void apiClient
                      .get(`/sales/delivery-routes/${routeId}/stops/${stop.id}/pod.pdf`, { responseType: 'blob' })
                      .then((res) => triggerBlobDownload(res.data as Blob, `pod-${stop.id}.pdf`))
                      .catch((err) => onError(getErrorMessage(err)));
                  }}
                >
                  {t('routes.printSlip')}
                </Button>
              ) : null}
              {canLinkReceipt && collected > 0 ? (
                stop.customerReceipt ? (
                  <Typography variant="body2" color="success.main" sx={{ alignSelf: 'center' }}>
                    {t('routes.receiptLinked')}
                  </Typography>
                ) : (
                  <Button size="small" variant="outlined" sx={TOUCH} onClick={() => onLinkReceipt(stop)}>
                    {t('routes.linkReceipt')}
                  </Button>
                )
              ) : null}
              {canRecord && !editing ? (
                <Button size="small" sx={TOUCH} onClick={() => { setEditing(true); setForm({ ...EMPTY_FORM, outcome: status as StopOutcome }); }}>
                  {t('routes.changeOutcome')}
                </Button>
              ) : null}
            </Stack>
          </Stack>
        ) : null}

        {showForm ? (
          <Box component="form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} noValidate>
            <Stack spacing={1.25}>
              {formError ? <Alert severity="error">{formError}</Alert> : null}
              {recorded ? <Alert severity="info">{t('routes.changeOutcomeHint')}</Alert> : null}
              <TextField
                select
                size="small"
                label={t('routes.outcome')}
                value={form.outcome}
                onChange={(e) => set('outcome', e.target.value as StopOutcome)}
                fullWidth
                inputProps={{ 'aria-label': t('routes.outcome') }}
              >
                {STOP_OUTCOMES.map((o) => (
                  <MenuItem key={o} value={o}>{t(`routes.outcomes.${o}`)}</MenuItem>
                ))}
              </TextField>
              {form.outcome === 'DELIVERED' ? (
                <>
                  <TextField size="small" required label={t('routes.receivedBy')} value={form.receivedBy} onChange={(e) => set('receivedBy', e.target.value)} fullWidth />
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                    <TextField size="small" type="number" label={t('routes.cashCollected')} value={form.cash} onChange={(e) => set('cash', e.target.value)} inputProps={{ min: 0, step: '0.01' }} fullWidth />
                    <TextField size="small" type="number" label={t('routes.upiCollected')} value={form.upi} onChange={(e) => set('upi', e.target.value)} inputProps={{ min: 0, step: '0.01' }} fullWidth />
                  </Stack>
                  {form.upi.trim() && Number(form.upi) > 0 ? (
                    <TextField size="small" required label={t('routes.upiReference')} value={form.upiReference} onChange={(e) => set('upiReference', e.target.value)} fullWidth />
                  ) : null}
                  <FormControlLabel
                    control={<Checkbox checked={!form.byOffice} onChange={(e) => set('byOffice', !e.target.checked)} />}
                    label={t('routes.customerGaveCode')}
                  />
                  {!form.byOffice ? (
                    <TextField size="small" label={t('routes.otp')} value={form.code} onChange={(e) => set('code', e.target.value)} fullWidth />
                  ) : null}
                </>
              ) : (
                <TextField size="small" label={t('routes.failureNote')} value={form.note} onChange={(e) => set('note', e.target.value)} fullWidth />
              )}
              {form.outcome === 'DELIVERED' && returnable.length > 0 ? (
                <FormControlLabel
                  control={<Checkbox checked={form.someCameBack} onChange={(e) => set('someCameBack', e.target.checked)} />}
                  label={t('routes.someCameBack')}
                />
              ) : null}
              {cameBack(form) && returnable.length > 0 ? (
                <Stack spacing={1}>
                  <Typography variant="body2">{t('routes.cameBackHelp')}</Typography>
                  {returnable.map((line) => (
                    <TextField
                      key={line.product}
                      size="small"
                      type="number"
                      label={`${line.productName} (${t('routes.upTo', { n: Number(line.quantity) })})`}
                      value={form.returned[line.product] ?? (form.outcome === 'DELIVERED' ? '' : String(Number(line.quantity)))}
                      onChange={(e) => setForm((prev) => ({ ...prev, returned: { ...prev.returned, [line.product]: e.target.value } }))}
                      inputProps={{ min: 0, step: 'any' }}
                      fullWidth
                    />
                  ))}
                </Stack>
              ) : null}
              {recorded ? (
                <TextField size="small" required label={t('routes.reasonForChange')} value={form.reason} onChange={(e) => set('reason', e.target.value)} fullWidth />
              ) : null}
              <Stack direction="row" spacing={1}>
                <Button type="submit" variant="contained" sx={TOUCH} disabled={save.isPending}>
                  {t(recorded ? 'routes.saveChange' : 'routes.recordOutcome')}
                </Button>
                {editing ? (
                  <Button sx={TOUCH} onClick={() => { setEditing(false); setFormError(null); setForm(EMPTY_FORM); }}>
                    {t('common.cancel')}
                  </Button>
                ) : null}
              </Stack>
            </Stack>
          </Box>
        ) : null}
      </Stack>
    </Paper>
  );
}
