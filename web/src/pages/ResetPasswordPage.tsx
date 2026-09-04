import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { confirmPasswordReset } from '@/api/auth';
import { t } from '@/i18n';

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = useMemo(() => params.get('token') || '', [params]);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError(t('auth.resetLinkMissingToken'));
      return;
    }
    if (password.length < 8) {
      setError(t('auth.passwordMin8'));
      return;
    }
    if (password !== confirm) {
      setError(t('auth.passwordsDoNotMatch'));
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
    } catch {
      setError(t('auth.resetLinkInvalid'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
        bgcolor: 'background.default',
      }}
    >
      <Card sx={{ maxWidth: 420, width: '100%', boxShadow: 3 }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Stack spacing={3}>
            <Box textAlign="center">
              <Typography variant="h5" component="h1" fontWeight={700} gutterBottom>
                {t('auth.setNewPasswordTitle')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('auth.setNewPasswordSubtitle')}
              </Typography>
            </Box>
            {error ? <Alert severity="error">{error}</Alert> : null}
            {done ? (
              <Stack spacing={2}>
                <Alert severity="success">{t('auth.passwordUpdated')}</Alert>
                <Button component={RouterLink} to="/login" variant="contained" fullWidth>
                  {t('auth.returnToLogin')}
                </Button>
              </Stack>
            ) : (
              <Box component="form" onSubmit={handleSubmit} noValidate>
                <Stack spacing={2.5}>
                  <TextField
                    label={t('auth.newPassword')}
                    type="password"
                    required
                    fullWidth
                    autoFocus
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    error={password.length > 0 && password.length < 8}
                    helperText={t('invite.passwordHint')}
                  />
                  <TextField
                    label={t('auth.confirmPassword')}
                    type="password"
                    required
                    fullWidth
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    error={confirm.length > 0 && confirm !== password}
                  />
                  <Button type="submit" variant="contained" size="large" fullWidth disabled={busy}>
                    {busy ? t('auth.saving') : t('auth.updatePassword')}
                  </Button>
                  <Box textAlign="center">
                    <Link component={RouterLink} to="/forgot-password" variant="body2" underline="hover">
                      {t('auth.requestNewLink')}
                    </Link>
                  </Box>
                </Stack>
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
