import { useState } from 'react';
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
import { apiClient, getErrorMessage, unwrapData } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { setAccessToken } from '@/auth/session';
import { t } from '@/i18n';
import type { User } from '@/types/domain';

/** BB-000418: minimal invite accept / set-password flow. */
export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get('token') || '');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    if (password.trim().length < 8) {
      setError(t('invite.passwordTooShort'));
      return;
    }
    setPending(true);
    setError(null);
    try {
      const { data } = await apiClient.post('/auth/invite/accept/', {
        token,
        new_password: password,
      });
      const body = unwrapData<{
        access?: string | null;
        refresh?: string;
        user?: User;
        email?: string;
        detail?: string;
      }>(data);
      localStorage.setItem('bb_role_welcome', '1');
      if (body.access) {
        setAccessToken(body.access);
        const user = body.user ?? (await fetchCurrentUser());
        await setSession(user, body.access);
        navigate('/', { replace: true });
        return;
      }
      const qs = new URLSearchParams({ invited: '1' });
      if (body.email) qs.set('email', body.email);
      navigate(`/login?${qs.toString()}`, { replace: true });
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
            helperText={!params.get('token') ? t('invite.tokenHint') : undefined}
          />
          <TextField
            label={t('invite.newPassword')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            fullWidth
            error={password.length > 0 && password.trim().length < 8}
            helperText={t('invite.passwordHint')}
          />
          {error ? (
            <Alert severity="error" role="alert" aria-live="assertive">
              {error}
            </Alert>
          ) : null}
          <Button
            variant="contained"
            disabled={pending || !token || password.trim().length < 8}
            onClick={() => void submit()}
          >
            {t('invite.accept')}
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}
