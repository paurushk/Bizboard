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

export function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim()) {
      setError('Please enter your registered email address or mobile number.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await requestPasswordReset(identifier.trim());
      setSubmitted(true);
    } catch {
      setError('Unable to send a reset link right now. Please try again.');
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
                Reset Password
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Enter your email address or phone number and we will send you recovery instructions.
              </Typography>
            </Box>

            {error ? <Alert severity="error">{error}</Alert> : null}

            {submitted ? (
              <Stack spacing={2}>
                <Alert severity="success">
                  If an account exists for <strong>{identifier}</strong>, a password reset link has been dispatched.
                </Alert>
                <Button component={RouterLink} to="/login" variant="contained" fullWidth>
                  Return to Login
                </Button>
              </Stack>
            ) : (
              <Box component="form" onSubmit={handleSubmit} noValidate>
                <Stack spacing={2.5}>
                  <TextField
                    label="Email or Mobile number"
                    type="text"
                    required
                    fullWidth
                    autoFocus
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="e.g. name@bizboard.local or 9876543210"
                  />
                  <Button type="submit" variant="contained" size="large" fullWidth disabled={busy}>
                    {busy ? 'Sending…' : 'Send Reset Link'}
                  </Button>
                  <Box textAlign="center">
                    <Link component={RouterLink} to="/login" variant="body2" underline="hover">
                      Back to Sign In
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
