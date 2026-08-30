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
      setError('This reset link is missing a token. Request a new link from the login page.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
    } catch {
      setError('This reset link is invalid or has expired. Please request a new one.');
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
                Choose a new password
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Enter a new password for your BizBoard account.
              </Typography>
            </Box>
            {error ? <Alert severity="error">{error}</Alert> : null}
            {done ? (
              <Stack spacing={2}>
                <Alert severity="success">Your password has been updated. You can sign in now.</Alert>
                <Button component={RouterLink} to="/login" variant="contained" fullWidth>
                  Return to Login
                </Button>
              </Stack>
            ) : (
              <Box component="form" onSubmit={handleSubmit} noValidate>
                <Stack spacing={2.5}>
                  <TextField
                    label="New password"
                    type="password"
                    required
                    fullWidth
                    autoFocus
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <TextField
                    label="Confirm password"
                    type="password"
                    required
                    fullWidth
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                  <Button type="submit" variant="contained" size="large" fullWidth disabled={busy}>
                    {busy ? 'Saving…' : 'Update password'}
                  </Button>
                  <Box textAlign="center">
                    <Link component={RouterLink} to="/forgot-password" variant="body2" underline="hover">
                      Request a new link
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
