import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useForm } from 'react-hook-form';
import { Link as RouterLink, Navigate } from 'react-router-dom';
import { requestOtp } from '@/api/auth';
import { getErrorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { formatOtpHint, isOtpLoginEnabled } from '@/pages/loginOtp';

interface PasswordForm {
  email: string;
  password: string;
}

interface OtpForm {
  phone: string;
  code: string;
}

export function LoginPage() {
  const { login, loginWithOtp, isAuthenticated } = useAuth();
  const otpEnabled = isOtpLoginEnabled();
  const [tab, setTab] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [otpHint, setOtpHint] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);

  const passwordForm = useForm<PasswordForm>({
    defaultValues: { email: '', password: '' },
  });
  const otpForm = useForm<OtpForm>({ defaultValues: { phone: '', code: '' } });

  if (isAuthenticated) return <Navigate to="/" replace />;

  const onPasswordLogin = passwordForm.handleSubmit(async (values) => {
    setIsSubmitting(true);
    setError(null);
    try {
      await login(values.email, values.password);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  });

  const onRequestOtp = async () => {
    setError(null);
    setOtpRequesting(true);
    try {
      const phone = otpForm.getValues('phone');
      const res = await requestOtp(phone);
      // BUG-628 / P0-108: never surface "Dev OTP:" outside DEV builds.
      setOtpHint(formatOtpHint(res));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setOtpRequesting(false);
    }
  };

  const onOtpLogin = otpForm.handleSubmit(async (values) => {
    setIsSubmitting(true);
    setError(null);
    try {
      await loginWithOtp(values.phone, values.code);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  });

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        p: 2,
        background: 'linear-gradient(160deg, #ECFDF5 0%, #F3F6F5 45%, #FFF7ED 100%)',
      }}
    >
      <Paper sx={{ p: 4, width: '100%', maxWidth: 440 }}>
        <Stack spacing={2}>
          <Typography variant="h4">{t('app.name')}</Typography>
          <Typography color="text.secondary">{t('auth.loginTitle')}</Typography>
          {otpEnabled ? (
            <Tabs value={tab} onChange={(_, v) => setTab(v)}>
              <Tab label={t('auth.passwordLogin')} />
              <Tab label={t('auth.otpLogin')} />
            </Tabs>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {otpEnabled && otpHint ? <Alert severity="info">{otpHint}</Alert> : null}

          {!otpEnabled || tab === 0 ? (
            <Stack spacing={2} component="form" onSubmit={onPasswordLogin}>
              <TextField
                label={t('auth.email')}
                type="email"
                required
                {...passwordForm.register('email', { required: true })}
              />
              <TextField
                label={t('auth.password')}
                type="password"
                required
                {...passwordForm.register('password', { required: true })}
              />
              <Button type="submit" variant="contained" disabled={isSubmitting}>
                {t('auth.login')}
              </Button>
            </Stack>
          ) : (
            <Stack spacing={2} component="form" onSubmit={onOtpLogin}>
              <TextField
                label={t('auth.phone')}
                required
                {...otpForm.register('phone', { required: true })}
              />
              <Button
                variant="outlined"
                disabled={otpRequesting}
                onClick={() => void onRequestOtp()}
              >
                {t('auth.requestOtp')}
              </Button>
              <TextField
                label={t('auth.otp')}
                required
                {...otpForm.register('code', { required: true })}
              />
              <Button type="submit" variant="contained" disabled={isSubmitting}>
                {t('auth.verifyOtp')}
              </Button>
            </Stack>
          )}

          <Typography variant="body2" color="text.secondary">
            {t('auth.demoHint')}{' '}
            <Link component={RouterLink} to="/register">
              {t('auth.register')}
            </Link>
          </Typography>
        </Stack>
      </Paper>
    </Box>
  );
}
