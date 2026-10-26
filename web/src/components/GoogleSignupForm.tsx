import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useNavigate } from 'react-router-dom';
import { googleSignIn, MfaEnrollmentRequiredError, MfaRequiredError } from '@/api/auth';
import { getErrorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { BotCheck } from '@/components/BotCheck';
import { StateSelect } from '@/components/StateSelect';
import { t } from '@/i18n';

/**
 * WP-ID5: finish a sign-up that started with Google. Google already proved the email, so no
 * email code or password is asked; the bot check and one-trial-per-business still apply.
 */
export function GoogleSignupForm({
  credential,
  email,
  onCancel,
  referralCode = '',
}: {
  credential: string;
  email: string;
  onCancel: () => void;
  referralCode?: string;
}) {
  const { setSession } = useAuth();
  const navigate = useNavigate();
  const [companyName, setCompanyName] = useState('');
  const [state, setState] = useState('');
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await googleSignIn(credential, { companyName, state, acceptTerms, referralCode });
      if (result.kind === 'session') {
        await setSession(result.user, result.tokens.access);
        navigate('/', { replace: true });
      }
    } catch (err) {
      // The account was created; an owner then sets up two-step (or enters it) on the sign-in
      // page, which picks the step up from these tokens instead of starting over.
      if (err instanceof MfaRequiredError) {
        navigate('/login?registered=1', { replace: true, state: { email, mfaToken: err.mfaToken } });
      } else if (err instanceof MfaEnrollmentRequiredError) {
        navigate('/login?registered=1', { replace: true, state: { email, enrolToken: err.enrolToken } });
      } else {
        setError(getErrorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h6">{t('googleSignup.title')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('googleSignup.help', { email })}
      </Typography>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <TextField label={t('auth.companyName')} value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
      <StateSelect label={t('googleSignup.state')} value={state} onChange={setState} required />
      <FormControlLabel
        control={<Checkbox checked={acceptTerms} onChange={(e) => setAcceptTerms(e.target.checked)} />}
        label={t('googleSignup.acceptTerms')}
      />
      <BotCheck />
      <Button variant="contained" disabled={!companyName.trim() || !state || !acceptTerms || busy} onClick={() => void submit()}>
        {t('googleSignup.create')}
      </Button>
      <Button onClick={onCancel}>{t('googleSignup.useEmail')}</Button>
    </Stack>
  );
}
