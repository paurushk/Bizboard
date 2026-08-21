import { useState } from 'react';
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiClient, getErrorMessage } from '@/api/client';
import { t } from '@/i18n';

/** BB-000418: minimal invite accept / set-password flow. */
export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get('token') || '');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setPending(true);
    setError(null);
    try {
      await apiClient.post('/auth/invite/accept/', { token, new_password: password });
      localStorage.setItem('bb_role_welcome', '1');
      navigate('/login?invited=1', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2 }}>
      <Paper sx={{ p: 3, width: '100%', maxWidth: 420 }}>
        <Stack spacing={2}>
          <Typography variant="h5">{t('invite.title')}</Typography>
          <Typography variant="body2" color="text.secondary">
            {t('invite.description')}
          </Typography>
          {!params.get('token') ? (
            <Alert severity="info">{t('invite.tokenMissing')}</Alert>
          ) : null}
          <TextField
            label={t('invite.token')}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            fullWidth
            multiline
            minRows={2}
            helperText={!params.get('token') ? 'Paste the token only if you were given one separately.' : undefined}
          />
          <TextField
            label={t('invite.newPassword')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            fullWidth
          />
          {error ? (
            <Alert severity="error" role="alert" aria-live="assertive">
              {error}
            </Alert>
          ) : null}
          <Button variant="contained" disabled={pending || !token || !password} onClick={() => void submit()}>
            {t('invite.accept')}
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}
