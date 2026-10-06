import { useEffect, useRef, useState, type FormEvent } from 'react';
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
import { confirmMfa, MfaEnrollmentRequiredError, MfaRequiredError, requestOtp, startMfaSetup } from '@/api/auth';
import { consumeEnrolToken, getErrorMessage } from '@/api/client';
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
  // F1-014: also reject a backslash after the leading slash (`/\evil.com`,
  // `/\/evil.com`) which some environments treat like `//`.
  if (!decoded.startsWith('/') || /^\/[\\/]/.test(decoded)) return '/';
  if (decoded.startsWith('/login') || decoded.startsWith('/register')) return '/';
  return decoded;
}

const emailSchema = z.object({
  email: z.string().trim().superRefine((value, ctx) => {
    if (!z.string().email().safeParse(value).success) {
      ctx.addIssue({ code: 'custom', message: t('cog.validEmail') });
    }
  }),
});

const otpSchema = z.object({
  phone: z.string().trim().superRefine((value, ctx) => {
    if (value.length < 8) ctx.addIssue({ code: 'custom', message: t('cog.validPhone') });
  }),
  code: z.string().trim().superRefine((value, ctx) => {
    if (value.length < 4) ctx.addIssue({ code: 'custom', message: t('cog.enterOtp') });
  }),
});

type EmailForm = z.infer<typeof emailSchema>;
type OtpForm = z.infer<typeof otpSchema>;

export function LoginPage() {
  const { login, loginWithOtp, completeMfaLogin, isAuthenticated } = useAuth();
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
  // F-SEC-02: set when the password/OTP step succeeded but the account needs a second factor.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [enrolToken, setEnrolToken] = useState<string | null>(null);
  const consumedEnrolToken = useRef<string | null | undefined>(undefined);
  const [enrolSecret, setEnrolSecret] = useState<string | null>(null);
  const [enrolDone, setEnrolDone] = useState(false);
  // Shown once, right after the authenticator is confirmed. The server never returns them again.
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [mfaRecovery, setMfaRecovery] = useState(false);

  const passwordForm = useForm<EmailForm>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: prefillEmail },
  });

  useEffect(() => {
    if (prefillEmail) {
      passwordForm.setValue('email', prefillEmail);
    }
  }, [prefillEmail, passwordForm]);

  useEffect(() => {
    // The token lives in memory only and is read once. Reading it in a state
    // initializer would run twice under StrictMode and lose it, so read it here
    // and hand it to state on the next microtask.
    // The first run consumes it; the second StrictMode run reads it back from the ref.
    if (consumedEnrolToken.current === undefined) consumedEnrolToken.current = consumeEnrolToken();
    const stored = consumedEnrolToken.current;
    if (!stored) return;
    let live = true;
    void Promise.resolve().then(() => {
      if (live) setEnrolToken(stored);
    });
    return () => {
      live = false;
    };
  }, []);
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
      setPasswordError(t('auth.passwordRequired'));
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
      if (err instanceof MfaRequiredError) {
        setMfaToken(err.mfaToken);
      } else if (err instanceof MfaEnrollmentRequiredError) {
        setEnrolToken(err.enrolToken);
      } else {
        setError(getErrorMessage(err));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEnrolment = async () => {
    if (!enrolToken) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const setup = await startMfaSetup(enrolToken);
      setEnrolSecret(setup.secret);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitEnrolment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!enrolToken) return;
    const value = String(new FormData(event.currentTarget).get('enrolCode') ?? '').trim();
    if (!value) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const codes = await confirmMfa(value, enrolToken);
      setRecoveryCodes(codes);
      setEnrolDone(true);
      setEnrolSecret(null);
      setEnrolToken(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitMfa = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mfaToken) return;
    const value = String(new FormData(event.currentTarget).get('mfaCode') ?? '').trim();
    if (!value) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await completeMfaLogin(mfaToken, mfaRecovery ? { recoveryCode: value } : { code: value });
      navigate(nextPath, { replace: true });
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 401 = wrong code; 429 = locked; anything else keeps the server's message.
      setError(status === 401 ? t('auth.mfa.invalid') : getErrorMessage(err));
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
      if (err instanceof MfaRequiredError) {
        setMfaToken(err.mfaToken);
      } else if (err instanceof MfaEnrollmentRequiredError) {
        setEnrolToken(err.enrolToken);
      } else {
        setError(getErrorMessage(err));
      }
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
          {searchParams.get('registered') === 'pending' || searchParams.get('registered') === '1' ? (
            <Alert severity="success">{t('auth.registerThenLogin')}</Alert>
          ) : null}
          {searchParams.get('invited') === '1' ? (
            <Alert severity="success">{t('auth.inviteAccepted')}</Alert>
          ) : null}
          {otpEnabled && !mfaToken && !enrolToken && !enrolDone ? (
            <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label={t('auth.loginTabs')}>
              <Tab label={t('auth.passwordLogin')} />
              <Tab label={t('auth.otpLogin')} />
            </Tabs>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {otpEnabled && otpHint ? <Alert severity="info">{otpHint}</Alert> : null}

          {enrolDone ? (
            <Alert severity="success">{t('auth.mfa.enrolDone')}</Alert>
          ) : null}
          {recoveryCodes ? (
            <Stack spacing={1}>
              <Typography fontWeight={600}>{t('auth.mfa.recoveryTitle')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('auth.mfa.recoveryHelp')}
              </Typography>
              <Box
                component="ul"
                aria-label={t('auth.mfa.recoveryTitle')}
                sx={{ m: 0, p: 1.5, listStyle: 'none', bgcolor: 'action.hover', borderRadius: 1, fontFamily: 'monospace', columnCount: 2 }}
              >
                {recoveryCodes.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </Box>
              <Box>
                <Button variant="contained" onClick={() => setRecoveryCodes(null)}>
                  {t('auth.mfa.recoveryDone')}
                </Button>
              </Box>
            </Stack>
          ) : null}
          {enrolToken ? (
            <Stack spacing={2} component="form" onSubmit={submitEnrolment} noValidate>
              <Typography variant="h6">{t('auth.mfa.enrolTitle')}</Typography>
              <Typography color="text.secondary">{t('auth.mfa.enrolPrompt')}</Typography>
              {enrolSecret ? (
                <TextField label={t('auth.mfa.manualKey')} value={enrolSecret} slotProps={{ htmlInput: { readOnly: true } }} />
              ) : (
                <Button type="button" variant="outlined" disabled={isSubmitting} onClick={() => void startEnrolment()}>
                  {t('auth.mfa.enable')}
                </Button>
              )}
              <TextField name="enrolCode" label={t('auth.mfa.enterCode')} autoComplete="one-time-code" />
              <Button type="submit" variant="contained" disabled={isSubmitting}>
                {t('auth.mfa.confirm')}
              </Button>
            </Stack>
          ) : null}
          {mfaToken && !enrolToken ? (
            <Stack spacing={2} component="form" onSubmit={submitMfa} noValidate>
              <Typography variant="h6">{t('auth.mfa.title')}</Typography>
              <Typography color="text.secondary">{t('auth.mfa.prompt')}</Typography>
              <TextField
                key={mfaRecovery ? 'recovery' : 'code'}
                name="mfaCode"
                label={mfaRecovery ? t('auth.mfa.recoveryLabel') : t('auth.mfa.codeLabel')}
                autoFocus
                autoComplete="one-time-code"
                slotProps={{
                  htmlInput: mfaRecovery
                    ? { autoCapitalize: 'characters', spellCheck: false }
                    : { inputMode: 'numeric', pattern: '[0-9]*', maxLength: 6 },
                }}
              />
              <Button type="submit" variant="contained" disabled={isSubmitting}>
                {t('auth.mfa.verify')}
              </Button>
              <Link component="button" type="button" variant="body2" onClick={() => setMfaRecovery((v) => !v)}>
                {mfaRecovery ? t('auth.mfa.useCode') : t('auth.mfa.useRecovery')}
              </Link>
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={() => {
                  setMfaToken(null);
                  setMfaRecovery(false);
                  setError(null);
                }}
              >
                {t('auth.mfa.back')}
              </Link>
            </Stack>
          ) : enrolToken || enrolDone ? null : !otpEnabled || tab === 0 ? (
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
