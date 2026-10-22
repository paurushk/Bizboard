import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation } from '@tanstack/react-query';
import { startOwnershipTransfer } from '@/api/ownership';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

/**
 * WP-ID1: offer ownership to another active member. Asks for the owner's password (and two-step
 * code when on) because it hands over the whole company; the member must accept from the email.
 */
export function OwnershipTransferDialog({
  member,
  onClose,
}: {
  member: { user: number; email: string; fullName?: string } | null;
  onClose: () => void;
}) {
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [becomes, setBecomes] = useState<'MANAGER' | 'LEAVE'>('MANAGER');
  const send = useMutation({
    mutationFn: () =>
      startOwnershipTransfer({ toUserId: member!.user, oldOwnerBecomes: becomes, password, code }),
  });
  const close = () => {
    setPassword('');
    setCode('');
    send.reset();
    onClose();
  };

  return (
    <Dialog open={Boolean(member)} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle>{t('ownership.title', { name: member?.fullName || member?.email || '' })}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          <Alert severity="warning">{t('ownership.warning')}</Alert>
          <TextField
            select
            label={t('ownership.youBecome')}
            value={becomes}
            onChange={(e) => setBecomes(e.target.value as 'MANAGER' | 'LEAVE')}
          >
            <MenuItem value="MANAGER">{t('ownership.becomeManager')}</MenuItem>
            <MenuItem value="LEAVE">{t('ownership.leave')}</MenuItem>
          </TextField>
          <TextField
            type="password"
            label={t('ownership.password')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <TextField
            label={t('ownership.code')}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputProps={{ inputMode: 'numeric' }}
          />
          {send.isError ? <HelpErrorAlert error={send.error} /> : null}
          {send.isSuccess ? <Alert severity="success">{t('ownership.sent', { email: member?.email ?? '' })}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{send.isSuccess ? t('common.close') : t('common.cancel')}</Button>
        {!send.isSuccess ? (
          <Button variant="contained" color="warning" disabled={!password || send.isPending} onClick={() => send.mutate()}>
            {t('ownership.send')}
          </Button>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}
