import { useEffect, useState, type FormEvent } from 'react';
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
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { Link as RouterLink, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { requestOtp } from '@/api/auth';
import { getErrorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { PasswordField } from '@/components/PasswordField';
import { t } from '@/i18n';
import { formatOtpHint, isOtpLoginEnabled } from '@/pages/loginOtp';

function safeNextPath(raw: string | null): string {
  if (!raw) return '/';
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return '/';
  }
  // Same-origin relative paths only — reject protocol-relative / absolute URLs.
  if (!decoded.startsWith('/') || decoded.startsWith('//')) return '/';
  if (decoded.startsWith('/login') || decoded.startsWith('/register')) return '/';
  return decoded;
}

const emailSchema = z.object({
  email: z.string().trim().email('Enter a valid email'),
});

const otpSchema = z.object({
  phone: z.string().trim().min(8, 'Enter a valid phone number'),
  code: z.string().trim().min(4, 'Enter the OTP code'),
});

type EmailForm = z.infer<typeof emailSchema>;
type OtpForm = z.infer<typeof otpSchema>;

export function LoginPage() {
  const { login, loginWithOtp, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const nextPath = safeNextPath(searchParams.get('next'));
  const prefillEmail =
    searchParams.get('email') ||
    ((location.state as { email?: string } | null)?.email ?? '');
  const otpEnabled = isOtpLoginEnabled();
  const [tab, setTab] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [otpHint, setOtpHint] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);

  const passwordForm = useForm<EmailForm>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: prefillEmail },
  });

  useEffect(() => {
    if (prefillEmail) {
      passwordForm.setValue('email', prefillEmail);
    }
  }, [prefillEmail, passwordForm]);
  const otpForm = useForm<OtpForm>({
    resolver: zodResolver(otpSchema),
    defaultValues: { phone: '', code: '' },
  });

  if (isAuthenticated) return <Navigate to={nextPath} replace />;

  const submitPasswordLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get('email') ?? '');
    const password = String(data.get('password') ?? '');
    passwordForm.setValue('email', email, { shouldValidate: false });
    const emailOk = await passwordForm.trigger('email');
    if (!password) {
      setPasswordError('Password is required');
      return;
    }
    setPasswordError(null);
    if (!emailOk) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(nextPath, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onRequestOtp = async () => {
    setError(null);
    const phoneValid = await otpForm.trigger('phone');
    if (!phoneValid) return;
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
      navigate(nextPath, { replace: true });
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
          {searchParams.get('registered') === 'pending' ? (
            <Alert severity="info">{t('auth.registerPending')}</Alert>
          ) : searchParams.get('registered') === '1' ? (
            <Alert severity="success">{t('auth.registerSuccess')}</Alert>
          ) : null}
          {searchParams.get('invited') === '1' ? (
            <Alert severity="success">{t('auth.inviteAccepted')}</Alert>
          ) : null}
          {otpEnabled ? (
            <Tabs value={tab} onChange={(_, v) => setTab(v)}>
              <Tab label={t('auth.passwordLogin')} />
              <Tab label={t('auth.otpLogin')} />
            </Tabs>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {otpEnabled && otpHint ? <Alert severity="info">{otpHint}</Alert> : null}

          {!otpEnabled || tab === 0 ? (
            <Stack spacing={2} component="form" onSubmit={submitPasswordLogin} noValidate>
              <TextField
                label={t('auth.email')}
                type="email"
                autoComplete="username"
                error={Boolean(passwordForm.formState.errors.email)}
                helperText={passwordForm.formState.errors.email?.message}
                {...passwordForm.register('email')}
              />
              <PasswordField
                name="password"
                label={t('auth.password')}
                autoComplete="current-password"
                autoFocus={Boolean(prefillEmail)}
                error={Boolean(passwordError)}
                helperText={passwordError}
              />
              <Button type="submit" variant="contained" disabled={isSubmitting}>
                {t('auth.login')}
              </Button>
            </Stack>
          ) : (
            <Stack spacing={2} component="form" onSubmit={onOtpLogin}>
              <TextField
                label={t('auth.phone')}
                error={Boolean(otpForm.formState.errors.phone)}
                helperText={otpForm.formState.errors.phone?.message}
                {...otpForm.register('phone')}
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
                error={Boolean(otpForm.formState.errors.code)}
                helperText={otpForm.formState.errors.code?.message}
                {...otpForm.register('code')}
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
          <Typography variant="caption" color="text.secondary">
            <Link component={RouterLink} to="/forgot-password">
              {t('auth.forgotPassword')}
            </Link>
            {' — '}
            {t('auth.forgotPasswordStaffHint')}
          </Typography>
        </Stack>
      </Paper>
    </Box>
  );
}
