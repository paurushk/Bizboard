import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import type { BillPartyMatch } from '@/types/domain';
import { isValidGstin } from '@/utils/gst';

type Props = {
  isSales: boolean;
  /** True when a party is already chosen in the picker above. */
  hasSelectedParty: boolean;
  /** The party chosen in the picker, so a different name or GSTIN on the bill can be pointed out. */
  selected?: { name: string; gstin?: string | null } | null;
  match?: BillPartyMatch;
  name: string;
  gstin: string;
  onNameChange: (value: string) => void;
  onGstinChange: (value: string) => void;
  onPickCandidate: (id: number) => void;
  error?: string;
};

/**
 * What the AI read as the other party on the bill, editable, with the outcome
 * spelled out (matched / will be created / pick one) so the reviewer is never
 * surprised by who the draft is for.
 */
export function PartyBlock({
  isSales,
  hasSelectedParty,
  selected,
  match,
  name,
  gstin,
  onNameChange,
  onGstinChange,
  onPickCandidate,
  error,
}: Props) {
  const squash = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  if (hasSelectedParty) {
    // U-05: the person picked a party from the list; say so if the bill printed someone else.
    const billName = squash(name);
    const pickedName = squash(selected?.name ?? '');
    const billGstin = gstin.trim().toUpperCase();
    const savedGstin = (selected?.gstin ?? '').trim().toUpperCase();
    const nameDiffers = billName !== '' && pickedName !== '' && !pickedName.includes(billName) && !billName.includes(pickedName);
    const gstinDiffers = billGstin !== '' && savedGstin !== '' && billGstin !== savedGstin;
    if (!selected || (!nameDiffers && !gstinDiffers)) return null;
    return (
      <Alert severity="warning" sx={{ maxWidth: 560 }}>
        {gstinDiffers
          ? t('billUpload.partyGstinDiffers', { bill: billGstin, picked: selected.name, saved: savedGstin })
          : t('billUpload.partyDiffers', { bill: name.trim(), picked: selected.name })}
      </Alert>
    );
  }
  const gstinBad = gstin.trim().length === 15 && !isValidGstin(gstin.trim());
  return (
    <Stack spacing={1} sx={{ maxWidth: 560 }}>
      <Typography variant="subtitle2">
        {t(isSales ? 'billUpload.partySalesHeading' : 'billUpload.partyPurchaseHeading')}
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          size="small"
          label={t('billUpload.partyNameOnBill')}
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          error={Boolean(error)}
          helperText={error}
          sx={{ flex: 2 }}
        />
        <TextField
          size="small"
          label={t('billUpload.partyGstinOnBill')}
          value={gstin}
          onChange={(e) => onGstinChange(e.target.value.toUpperCase())}
          inputProps={{ maxLength: 15 }}
          error={gstinBad}
          helperText={gstinBad ? t('billUpload.gstinCheckDigit') : undefined}
          sx={{ flex: 1 }}
        />
      </Stack>
      {match?.status === 'matched' ? (
        <Chip
          size="small"
          color="success"
          sx={{ alignSelf: 'flex-start' }}
          label={t('billUpload.partyMatched', { name: match.candidates[0]?.name ?? '' })}
        />
      ) : null}
      {(match?.status === 'candidates' || match?.status === 'conflict') && match.candidates.length > 0 ? (
        <Alert severity="warning">
          <Typography variant="body2">
            {t(match.status === 'conflict' ? 'billUpload.partyConflict' : 'billUpload.partyPick')}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 0.5 }}>
            {match.candidates.map((candidate) => (
              <Button key={candidate.id} size="small" variant="outlined" onClick={() => onPickCandidate(candidate.id)}>
                {candidate.name}
                {candidate.gstin ? ` · ${candidate.gstin}` : ''}
              </Button>
            ))}
          </Stack>
        </Alert>
      ) : null}
      {match?.status === 'inactive_match' ? (
        <Alert severity="error">{match.notes.join(' ')}</Alert>
      ) : null}
      {match?.willCreate && (match.status === 'none' || match.status === 'candidates') ? (
        <Chip
          size="small"
          variant="outlined"
          sx={{ alignSelf: 'flex-start' }}
          label={t('billUpload.partyWillCreate', { name: match.extracted.name })}
        />
      ) : null}
      {match && match.status !== 'inactive_match' && match.notes.length > 0 ? (
        <Typography variant="caption" color="warning.dark">
          {match.notes.join(' ')}
        </Typography>
      ) : null}
    </Stack>
  );
}
