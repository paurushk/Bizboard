import { useState } from 'react';
import axios from 'axios';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getPublicLeadFormMeta, submitPublicLead } from '@/api/osPlan';
import { ErrorState } from '@/components/PageState';
import { t } from '@/i18n';

export function LeadFormPage() {
  const { token = '' } = useParams();
  const [searchParams] = useSearchParams();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [website, setWebsite] = useState('');
  // The campaign is a signed value from the link the business shared; it is never typed or shown.
  const campaign = searchParams.get('campaign') ?? '';
  const [referralCode, setReferralCode] = useState(
    searchParams.get('referral_code') ?? searchParams.get('referralCode') ?? '',
  );
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);
  const meta = useQuery({
    queryKey: ['public-lead-form', token],
    queryFn: () => getPublicLeadFormMeta(token),
    retry: false,
  });

  const submit = async () => {
    setPending(true);
    setError('');
    try {
      await submitPublicLead(token, {
        name,
        phone,
        email,
        message,
        website,
        campaign,
        referral_code: referralCode.trim(),
      });
      setDone(true);
    } catch (err) {
      setError(axios.isAxiosError(err) && err.response?.status === 429 ? t('osPlan.leadFormBusy') : getErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  // QOS-0098: a dead link says so instead of showing a form whose Send can only fail.
  const metaStatus = axios.isAxiosError(meta.error) ? meta.error.response?.status : undefined;
  const linkDead = meta.isError && metaStatus !== undefined && metaStatus >= 400 && metaStatus < 500;

  return (
    <Stack spacing={2} sx={{ maxWidth: 480, mx: 'auto', mt: 6, px: 2 }}>
      <Typography variant="h5">{t('osPlan.leadFormTitle')}</Typography>
      {meta.isError ? (
        linkDead ? (
          <ErrorState message={t('osPlan.leadFormLinkInvalid')} />
        ) : (
          <ErrorState message={getErrorMessage(meta.error)} error={meta.error} onRetry={() => void meta.refetch()} />
        )
      ) : null}
      {meta.data?.companyName ? (
        <Typography variant="body2" color="text.secondary">
          {t('osPlan.leadFormFrom', { company: meta.data.companyName })}
        </Typography>
      ) : null}
      {meta.isError ? null : done ? <Typography>{t('osPlan.leadFormThanks')}</Typography> : (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <TextField label={t('common.name')} required value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label={t('common.phone')} value={phone} onChange={(e) => setPhone(e.target.value)} />
            <TextField label={t('common.email')} value={email} onChange={(e) => setEmail(e.target.value)} />
            <TextField label={t('osPlan.message')} multiline minRows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
            <TextField label={t('growth.referralCode')} value={referralCode} onChange={(e) => setReferralCode(e.target.value)} />
            <TextField
              label={t('sweep.website')}
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              autoComplete="off"
              tabIndex={-1}
              inputProps={{ 'aria-hidden': true, tabIndex: -1 }}
              sx={{ position: 'absolute', left: -10000, height: 0, overflow: 'hidden' }}
            />
            {meta.data?.consentText ? (
              <Typography variant="caption" color="text.secondary">{meta.data.consentText}</Typography>
            ) : null}
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
