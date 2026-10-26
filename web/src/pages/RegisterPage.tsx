import { useEffect, useState, type FormEvent } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormHelperText from '@mui/material/FormHelperText';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { Link as RouterLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { googleSignIn, MfaEnrollmentRequiredError, MfaRequiredError, requestRegisterOtp } from '@/api/auth';
import { checkReferralCode } from '@/api/billing';
import { GoogleSignInButton } from '@/components/GoogleSignInButton';
import { GoogleSignupForm } from '@/components/GoogleSignupForm';
import { getErrorMessage, getFieldErrors } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { PasswordField } from '@/components/PasswordField';
import { PhoneField, phoneErrorMessage } from '@/components/PhoneField';
import { StateSelect } from '@/components/StateSelect';
import { getStateFromGstin } from '@/utils/indianStates';
import { findPhoneCountry, isValidPhoneValue, splitPhone } from '@/utils/phone';
import { t } from '@/i18n';
import { formatOtpHint } from '@/pages/loginOtp';
import { BotCheck } from '@/components/BotCheck';

const registerSchema = z.object({
  companyName: z.string().trim().superRefine((value, ctx) => {
    if (!value) ctx.addIssue({ code: 'custom', message: t('auth.companyRequired') });
  }),
  fullName: z.string().trim().optional(),
  email: z.string().trim().superRefine((value, ctx) => {
    if (!z.string().email().safeParse(value).success) {
      ctx.addIssue({ code: 'custom', message: t('cog.validEmail') });
    }
  }),
  // Optional, but when given it must be a complete number for the picked country.
  phone: z.string().trim().superRefine((value, ctx) => {
    if (!isValidPhoneValue(value)) {
      ctx.addIssue({ code: 'custom', message: phoneErrorMessage(findPhoneCountry(splitPhone(value).iso)) });
    }
  }),
  // BB-000751: state drives GSTIN structure and place-of-supply on every
  // invoice this company issues — it must not be silently skippable.
  state: z.string().trim().superRefine((value, ctx) => {
    if (!value) ctx.addIssue({ code: 'custom', message: t('auth.stateRequired') });
  }),
  gstin: z.string().trim().optional(),
  // Mandatory sign-up email verification — sent via the "Send code" button,
  // checked server-side against the OtpChallenge it created.
  otpCode: z.string().trim().superRefine((value, ctx) => {
    if (value.length !== 6) ctx.addIssue({ code: 'custom', message: t('auth.emailCode') });
  }),
  // WP-H5 (DPDP): an account needs the person's agreement to the Terms and Privacy Policy.
  acceptTerms: z.boolean().superRefine((value, ctx) => {
    if (!value) ctx.addIssue({ code: 'custom', message: t('auth.acceptTermsRequired') });
  }),
});

const TERMS_URL = import.meta.env.VITE_TERMS_URL as string | undefined;
const PRIVACY_URL = import.meta.env.VITE_PRIVACY_URL as string | undefined;

type RegisterForm = z.infer<typeof registerSchema>;

// Fields whose server errors are shown under the field rather than in the banner.
const FORM_FIELDS = Object.keys(registerSchema.shape) as (keyof RegisterForm)[];

const REFERRAL_KEY = 'bb_referral_code';

/** D-19: the ?ref= code, kept for this tab so a detour through Google sign-in on /login keeps it. */
function referralCodeFrom(search: string): string {
  const fromUrl = (new URLSearchParams(search).get('ref') ?? '').replace(/[^A-Za-z0-9]/g, '').slice(0, 16);
  try {
    if (fromUrl) sessionStorage.setItem(REFERRAL_KEY, fromUrl);
    return fromUrl || sessionStorage.getItem(REFERRAL_KEY) || '';
  } catch {
    return fromUrl;
  }
}

export function RegisterPage() {
  const { register: registerUser, isAuthenticated, setSession } = useAuth();
  const navigate = useNavigate();
  // WP-ID5: a Google sign-in for a new email lands here with the Google token in route state.
  const location = useLocation();
  const fromLogin = (location.state ?? {}) as { googleCredential?: string; email?: string };
  const [google, setGoogle] = useState<{ credential: string; email: string } | null>(
    fromLogin.googleCredential ? { credential: fromLogin.googleCredential, email: fromLogin.email ?? '' } : null,
  );
  const [referralCode] = useState(() => referralCodeFrom(location.search));
  const [referralValid, setReferralValid] = useState(false);
  useEffect(() => {
    if (!referralCode) return undefined;
    let live = true;
    checkReferralCode(referralCode)
      .then((ok) => live && setReferralValid(ok))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [referralCode]);
  const onGoogleCredential = async (credential: string) => {
    setError(null);
    try {
      const result = await googleSignIn(credential);
      if (result.kind === 'needsSignup') {
        setGoogle({ credential, email: result.email });
        return;
      }
      await setSession(result.user, result.tokens.access);
      navigate('/', { replace: true });
    } catch (err) {
      // An existing account with two-step: finish on the sign-in page, as a Google sign-in there would.
      if (err instanceof MfaRequiredError) {
        navigate('/login', { replace: true, state: { mfaToken: err.mfaToken } });
      } else if (err instanceof MfaEnrollmentRequiredError) {
        navigate('/login', { replace: true, state: { enrolToken: err.enrolToken } });
      } else {
        setError(getErrorMessage(err));
      }
    }
  };
  const [error, setError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [otpSending, setOtpSending] = useState(false);
  const [otpHint, setOtpHint] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    setValue,
    watch,
    trigger,
    setError: setFieldError,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      companyName: '',
      fullName: '',
      email: '',
      phone: '',
      state: '',
      gstin: '',
      otpCode: '',
      acceptTerms: false,
    },
  });

  // QOS-0037: the GSTIN's first two digits ARE the state code — derive the state
  // instead of making the user pick it again. Only fills a blank field so a
  // deliberate override is never clobbered.
  const gstinValue = watch('gstin');
  const stateValue = watch('state');
  useEffect(() => {
    const derived = getStateFromGstin((gstinValue ?? '').trim());
    if (derived && !stateValue) {
      setValue('state', derived, { shouldValidate: true, shouldDirty: true });
    }
  }, [gstinValue, stateValue, setValue]);

  if (isAuthenticated) return <Navigate to="/" replace />;

  const onSendCode = async () => {
    setError(null);
    const emailValid = await trigger('email');
    if (!emailValid) return;
    setOtpSending(true);
    try {
      const res = await requestRegisterOtp(watch('email'));
      // Never surfaces "Dev OTP:" outside DEV builds — same helper LoginPage uses.
      setOtpHint(formatOtpHint(res));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setOtpSending(false);
    }
  };

  const submitRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const password = String(new FormData(event.currentTarget).get('password') ?? '');
    const passwordOk = password.length >= 8;
    setPasswordError(passwordOk ? null : 'Password must be at least 8 characters');
    await handleSubmit(async (values) => {
      if (!passwordOk) return;
      setIsSubmitting(true);
      setError(null);
      try {
        await registerUser({ ...values, password, referralCode });
        // R-068: register never issues a session — send the operator to sign in.
        navigate(
          `/login?registered=1&email=${encodeURIComponent(values.email)}`,
          { replace: true, state: { email: values.email } },
        );
      } catch (err) {
        // Show a field's server error under that field, not in the banner.
        const { fieldErrors, banner } = getFieldErrors(err, FORM_FIELDS);
        for (const [field, message] of Object.entries(fieldErrors) as [keyof RegisterForm, string][]) {
          setFieldError(field, { type: 'server', message });
        }
        setError(banner);
      } finally {
        setIsSubmitting(false);
      }
    })(event);
  };

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
      <Paper sx={{ p: 4, width: '100%', maxWidth: 480 }}>
        {google ? (
          <GoogleSignupForm
            credential={google.credential}
            email={google.email}
            onCancel={() => setGoogle(null)}
            referralCode={referralCode}
          />
        ) : (
        <Stack spacing={2} component="form" onSubmit={submitRegister} noValidate>
          <Typography variant="h4">{t('auth.registerTitle')}</Typography>
          {referralValid ? <Alert severity="success">{t('auth.referralInvited')}</Alert> : null}
          <GoogleSignInButton text="signup_with" onCredential={(c) => void onGoogleCredential(c)} />
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField
            label={t('auth.companyName')}
            error={Boolean(errors.companyName)}
            helperText={errors.companyName?.message}
            {...register('companyName')}
          />
          <TextField
            label={`${t('auth.fullName')} (optional)`}
            error={Boolean(errors.fullName)}
            helperText={errors.fullName?.message}
            {...register('fullName')}
          />
          <TextField
            label={t('auth.email')}
            type="email"
            error={Boolean(errors.email)}
            helperText={errors.email?.message}
            {...register('email')}
          />
          {otpHint ? <Alert severity="info">{otpHint}</Alert> : null}
          {/* WP-AB2: one widget; it issues a fresh token after the code request uses one. */}
          <BotCheck />
          <Button variant="outlined" disabled={otpSending} onClick={() => void onSendCode()}>
            {t('auth.sendCode')}
          </Button>
          <TextField
            label={t('auth.verificationCode')}
            error={Boolean(errors.otpCode)}
            helperText={errors.otpCode?.message}
            {...register('otpCode')}
          />
          <PasswordField
            name="password"
            label={t('auth.password')}
            autoComplete="new-password"
            error={Boolean(passwordError)}
            helperText={passwordError}
          />
          <Controller
            name="phone"
            control={control}
            render={({ field }) => (
              <PhoneField
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                optional
                error={errors.phone?.message}
              />
            )}
          />
          <Controller
            name="state"
            control={control}
            render={({ field }) => (
              <StateSelect
                value={field.value}
                onChange={field.onChange}
                error={Boolean(errors.state)}
                helperText={errors.state?.message}
              />
            )}
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
            {t('auth.stateHelper')}
          </Typography>
          <TextField
            label={t('auth.gstinOptional')}
            error={Boolean(errors.gstin)}
            helperText={errors.gstin?.message ?? t('auth.gstinHelper')}
            {...register('gstin')}
          />
          <Controller
            name="acceptTerms"
            control={control}
            render={({ field }) => (
              <Box>
                <FormControlLabel
                  control={<Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />}
                  label={
                    <Typography variant="body2">
                      {t('auth.acceptTermsPrefix')}{' '}
                      {TERMS_URL ? (
                        <Link href={TERMS_URL} target="_blank" rel="noopener">{t('auth.termsOfService')}</Link>
                      ) : t('auth.termsOfService')}{' '}
                      {t('auth.and')}{' '}
                      {PRIVACY_URL ? (
                        <Link href={PRIVACY_URL} target="_blank" rel="noopener">{t('auth.privacyPolicy')}</Link>
                      ) : t('auth.privacyPolicy')}
                    </Typography>
                  }
                />
                {errors.acceptTerms ? <FormHelperText error>{errors.acceptTerms.message}</FormHelperText> : null}
              </Box>
            )}
          />
          <Button type="submit" variant="contained" disabled={isSubmitting}>
            {t('auth.register')}
          </Button>
          <Typography variant="body2">
            <Link component={RouterLink} to="/login">
              {t('auth.login')}
            </Link>
          </Typography>
        </Stack>
        )}
      </Paper>
    </Box>
  );
}
