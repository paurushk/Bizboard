import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { requestPasswordReset } from '@/api/auth';
import { t } from '@/i18n';

export function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim()) {
      setError(t('auth.resetIdentifierRequired'));
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await requestPasswordReset(identifier.trim());
      setSubmitted(true);
    } catch {
      setError(t('auth.resetSendFailed'));
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
                {t('auth.resetTitle')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('auth.resetSubtitle')}
              </Typography>
            </Box>

            {error ? <Alert severity="error">{error}</Alert> : null}

            {submitted ? (
              <Stack spacing={2}>
                <Alert severity="success">{t('auth.resetDispatched', { identifier })}</Alert>
                <Button component={RouterLink} to="/login" variant="contained" fullWidth>
                  {t('auth.returnToLogin')}
                </Button>
              </Stack>
            ) : (
              <Box component="form" onSubmit={handleSubmit} noValidate>
                <Stack spacing={2.5}>
                  <TextField
                    label={t('auth.emailOrMobile')}
                    type="text"
                    required
                    fullWidth
                    autoFocus
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder={t('auth.emailOrMobilePlaceholder')}
                  />
                  <Button type="submit" variant="contained" size="large" fullWidth disabled={busy}>
                    {busy ? t('auth.sending') : t('auth.sendResetLink')}
                  </Button>
                  <Box textAlign="center">
                    <Link component={RouterLink} to="/login" variant="body2" underline="hover">
                      {t('auth.backToSignIn')}
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
