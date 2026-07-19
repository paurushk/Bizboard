import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useForm } from 'react-hook-form';
import { Link as RouterLink, Navigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';

interface RegisterForm {
  companyName: string;
  fullName: string;
  email: string;
  password: string;
  phone: string;
  state: string;
}

export function RegisterPage() {
  const { register: registerUser, isAuthenticated } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { register, handleSubmit } = useForm<RegisterForm>({
    defaultValues: {
      companyName: '',
      fullName: '',
      email: '',
      password: '',
      phone: '',
      state: '',
    },
  });

  if (isAuthenticated) return <Navigate to="/" replace />;

  const onSubmit = handleSubmit(async (values) => {
    setIsSubmitting(true);
    setError(null);
    try {
      await registerUser(values);
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
      <Paper sx={{ p: 4, width: '100%', maxWidth: 480 }}>
        <Stack spacing={2} component="form" onSubmit={onSubmit}>
          <Typography variant="h4">{t('auth.registerTitle')}</Typography>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField
            label={t('auth.companyName')}
            required
            {...register('companyName', { required: true })}
          />
          <TextField label={t('auth.fullName')} {...register('fullName')} />
          <TextField
            label={t('auth.email')}
            type="email"
            required
            {...register('email', { required: true })}
          />
          <TextField
            label={t('auth.password')}
            type="password"
            required
            {...register('password', { required: true })}
          />
          <TextField label={t('auth.phone')} {...register('phone')} />
          <TextField label={t('auth.state')} {...register('state')} />
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
