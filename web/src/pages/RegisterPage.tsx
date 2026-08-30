import { useState, type FormEvent } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { Link as RouterLink, Navigate, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { getErrorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { PasswordField } from '@/components/PasswordField';
import { StateSelect } from '@/components/StateSelect';
import { t } from '@/i18n';

const registerSchema = z.object({
  companyName: z.string().trim().min(1, 'Company name is required'),
  fullName: z.string().trim().optional(),
  email: z.string().trim().email('Enter a valid email'),
  phone: z.string().trim().optional(),
  // BB-000751: state drives GSTIN structure and place-of-supply on every
  // invoice this company issues — it must not be silently skippable.
  state: z.string().trim().min(1, 'State is required'),
  gstin: z.string().trim().optional(),
});

type RegisterForm = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { register: registerUser, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const {
    register,
    handleSubmit,
    control,
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
    },
  });

  if (isAuthenticated) return <Navigate to="/" replace />;

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
        const result = await registerUser({ ...values, password });
        navigate(
          result === 'pending'
            ? `/login?registered=pending&email=${encodeURIComponent(values.email)}`
            : '/',
          { replace: true, state: { email: values.email } },
        );
      } catch (err) {
        setError(getErrorMessage(err));
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
        <Stack spacing={2} component="form" onSubmit={submitRegister} noValidate>
          <Typography variant="h4">{t('auth.registerTitle')}</Typography>
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
          <PasswordField
            name="password"
            label={t('auth.password')}
            autoComplete="new-password"
            error={Boolean(passwordError)}
            helperText={passwordError}
          />
          <TextField
            label={`${t('auth.phone')} (optional)`}
            error={Boolean(errors.phone)}
            helperText={errors.phone?.message}
            {...register('phone')}
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
          <Button type="submit" variant="contained" disabled={isSubmitting}>
            {t('auth.register')}
          </Button>
          <Typography variant="body2">
            <Link component={RouterLink} to="/login">
              {t('auth.login')}
            </Link>
          </Typography>
        </Stack>
      </Paper>
    </Box>
  );
}
