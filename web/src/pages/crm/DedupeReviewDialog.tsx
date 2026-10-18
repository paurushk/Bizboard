import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getDedupeCandidates, resolveDedupe, type DedupeDetails, type Lead } from '@/api/crm';
import { LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatDateTime } from '@/utils/dateTime';

/** The people a new lead might be: each with enough detail to tell them apart. */
export function CandidateList({ details }: { details: DedupeDetails }) {
  const none = details.customers.length === 0 && details.leads.length === 0;
  return (
    <Stack spacing={1}>
      {none ? <Typography variant="body2">{t('osPlan.dedupeNoCandidates')}</Typography> : null}
      {details.customers.length > 0 ? (
        <Typography variant="subtitle2">{t('osPlan.dedupeCustomersHeading')}</Typography>
      ) : null}
      {details.customers.map((c) => (
        <Paper key={`c-${c.id}`} variant="outlined" sx={{ p: 1 }}>
          <Typography variant="body2">{c.name}</Typography>
          <Typography variant="caption" color="text.secondary">
            {[c.phone, c.email, c.gstin].filter(Boolean).join(' · ') || '—'}
          </Typography>
        </Paper>
      ))}
      {details.leads.length > 0 ? (
        <Typography variant="subtitle2">{t('osPlan.dedupeLeadsHeading')}</Typography>
      ) : null}
      {details.leads.map((l) => (
        <Paper key={`l-${l.id}`} variant="outlined" sx={{ p: 1 }}>
          <Typography variant="body2">{l.name}</Typography>
          <Typography variant="caption" color="text.secondary">
            {[l.phone, l.email, l.status].filter(Boolean).join(' · ') || '—'}
            {' · '}
            {l.lastTouchedAt
              ? t('osPlan.dedupeLastTouch', { when: formatDateTime(l.lastTouchedAt) })
              : t('osPlan.dedupeNeverTouched')}
          </Typography>
        </Paper>
      ))}
    </Stack>
  );
}

/** Decide whether a lead waiting for review is someone already known. */
export function DedupeReviewDialog({
  lead,
  onClose,
  onResolved,
}: {
  lead: Lead | null;
  onClose: () => void;
  onResolved: () => void;
}) {
  const [error, setError] = useState('');
  const details = useQuery({
    queryKey: ['dedupe-candidates', lead?.id],
    queryFn: () => getDedupeCandidates(lead!.id),
    enabled: Boolean(lead),
  });
  const resolve = useMutation({
    mutationFn: (body: Parameters<typeof resolveDedupe>[1]) => resolveDedupe(lead!.id, body),
    onSuccess: () => {
      setError('');
      onResolved();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const customers = details.data?.customers ?? [];
  const leads = details.data?.leads ?? [];
  const busy = resolve.isPending;
  return (
    <Dialog open={Boolean(lead)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('osPlan.dedupeReviewTitle', { name: lead?.name ?? '' })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {[lead?.phone, lead?.email].filter(Boolean).join(' · ')}
          </Typography>
          {details.isLoading ? <LoadingState /> : null}
          {details.isError ? <Typography color="error">{getErrorMessage(details.error)}</Typography> : null}
          {details.data ? <CandidateList details={details.data} /> : null}
          {error ? <Typography color="error">{error}</Typography> : null}
          <Typography variant="caption" color="text.secondary">{t('osPlan.dedupeSameLeadHint')}</Typography>
          <Typography variant="caption" color="text.secondary">{t('osPlan.dedupeDifferentHint')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        <Button onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
        {customers.map((c) => (
          <Button
            key={`c-${c.id}`}
            disabled={busy}
            onClick={() => resolve.mutate({ decision: 'same_customer', customer_id: c.id })}
          >
            {customers.length > 1 ? `${t('osPlan.dedupeSameCustomer')}: ${c.name}` : t('osPlan.dedupeSameCustomer')}
          </Button>
        ))}
        {leads.map((l) => (
          <Button
            key={`l-${l.id}`}
            disabled={busy}
            onClick={() => resolve.mutate({ decision: 'same_lead', lead_id: l.id })}
          >
            {leads.length > 1 ? `${t('osPlan.dedupeSameLead')}: ${l.name}` : t('osPlan.dedupeSameLead')}
          </Button>
        ))}
        <Button variant="contained" disabled={busy} onClick={() => resolve.mutate({ decision: 'different' })}>
          {t('osPlan.dedupeDifferent')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
