import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getSubcontractDefaults, sendStepToJobWorker, type JobCard } from '@/api/mfg';
import { t } from '@/i18n';
import { ErrorLine, NumField, SupplierPick, useMasters, useRun } from './mfgShared';

/**
 * Send a routing step that a job worker does: pick the job worker, check the material that goes out, and the
 * job-work order and challan are raised for the step. The job worker's return receipt writes back to the card.
 */
export function SubcontractDialog({ card, onClose, onDone }: { card: JobCard | null; onClose: () => void; onDone: () => void }) {
  return card ? <Form key={card.id} card={card} onClose={onClose} onDone={onDone} /> : null;
}

function Form({ card, onClose, onDone }: { card: JobCard; onClose: () => void; onDone: () => void }) {
  const { productName } = useMasters();
  const { run, busy, error, clear } = useRun();
  const defaults = useQuery({ queryKey: ['mfg-subcontract-defaults', card.id], queryFn: () => getSubcontractDefaults(card.id) });
  // Edits sit on top of what the server suggested, so there is nothing to copy into state when it arrives.
  const [supplier, setSupplier] = useState<number | '' | null>(null);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [due, setDue] = useState('');
  const [vehicle, setVehicle] = useState('');
  const [notes, setNotes] = useState('');
  const [issueNow, setIssueNow] = useState(true);
  const chosenSupplier = supplier ?? defaults.data?.supplier ?? '';
  const lines = (defaults.data?.lines ?? []).map((l) => ({ product: l.product, qty: amounts[l.product] ?? l.qty }));
  const sending = lines.filter((l) => Number(l.qty) > 0);

  const send = async () => {
    const out = await run(() =>
      sendStepToJobWorker(card.id, {
        supplier: chosenSupplier === '' ? undefined : chosenSupplier,
        lines: sending,
        expectedReturnDate: due || undefined,
        vehicleNo: vehicle || undefined,
        notes: notes || undefined,
        issue: issueNow,
      }),
    );
    if (out) {
      onDone();
      onClose();
    }
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="send-step-title">
      <DialogTitle id="send-step-title">{t('mfg.sub.title', { step: card.name })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <ErrorLine error={error} onClose={clear} />
          <Typography variant="body2" color="text.secondary">{t('mfg.sub.help')}</Typography>
          <SupplierPick label={t('mfg.sub.jobWorker')} value={chosenSupplier} onChange={setSupplier} />
          <Typography variant="subtitle2">{t('mfg.sub.material')}</Typography>
          {lines.length === 0 ? <Typography color="text.secondary">{t('mfg.sub.noMaterial')}</Typography> : null}
          {lines.map((l) => (
            <Stack key={l.product} direction="row" spacing={2} alignItems="center">
              <Typography sx={{ flex: 1 }}>{productName(l.product)}</Typography>
              <NumField label={t('mfg.common.quantity')} value={l.qty} onChange={(v) => setAmounts({ ...amounts, [l.product]: v })} width={120} />
            </Stack>
          ))}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField size="small" type="date" label={t('mfg.sub.expectedBack')} value={due} onChange={(e) => setDue(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TextField size="small" label={t('mfg.sub.vehicle')} value={vehicle} onChange={(e) => setVehicle(e.target.value)} />
          </Stack>
          <TextField size="small" label={t('mfg.common.notes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
          <FormControlLabel control={<Switch checked={issueNow} onChange={(e) => setIssueNow(e.target.checked)} />} label={t('mfg.sub.issueNow')} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={busy || chosenSupplier === '' || sending.length === 0} onClick={send}>{t('mfg.sub.send')}</Button>
      </DialogActions>
    </Dialog>
  );
}
