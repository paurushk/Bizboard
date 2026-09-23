import { useState } from 'react';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { submitPublicLead } from '@/api/osPlan';
import { t } from '@/i18n';

export function LeadFormPage() {
  const { token = '' } = useParams();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [website, setWebsite] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  const submit = async () => {
    setPending(true);
    setError('');
    try {
      await submitPublicLead(token, { name, phone, email, message, website });
      setDone(true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <Stack spacing={2} sx={{ maxWidth: 480, mx: 'auto', mt: 6, px: 2 }}>
      <Typography variant="h5">{t('osPlan.leadFormTitle')}</Typography>
      {done ? <Typography>{t('osPlan.leadFormThanks')}</Typography> : (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <TextField label={t('common.name')} required value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label={t('common.phone')} value={phone} onChange={(e) => setPhone(e.target.value)} />
            <TextField label={t('common.email')} value={email} onChange={(e) => setEmail(e.target.value)} />
            <TextField label={t('osPlan.message')} multiline minRows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
            <TextField
              label="Website"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              autoComplete="off"
              tabIndex={-1}
              inputProps={{ 'aria-hidden': true, tabIndex: -1 }}
              sx={{ position: 'absolute', left: -10000, height: 0, overflow: 'hidden' }}
            />
            {error ? <Typography color="error">{error}</Typography> : null}
            <Button variant="contained" disabled={pending || !name.trim() || (!phone.trim() && !email.trim())} onClick={() => void submit()}>
              {t('osPlan.sendLead')}
            </Button>
          </Stack>
        </Paper>
      )}
    </Stack>
  );
}
