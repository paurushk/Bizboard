import Alert from '@mui/material/Alert';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { canManageUsers } from '@/utils/permissions';

export function InvoiceTemplatesPage() {
  const { user } = useAuth();
  if (!canManageUsers(user)) return <Navigate to="/" replace />;

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.invoiceTemplates')}</Typography>
      <Paper sx={{ p: 3 }}>
        <Alert severity="info" sx={{ mb: 2 }}>
          GST-compliant A4 template (logo, UPI QR, HSN/SAC, CGST/SGST/IGST breakup) is assembled by
          the Invoice Service. Template customization ships with async PDF in pilot hardening.
        </Alert>
        <Typography color="text.secondary">
          Default template: GST Invoice · A4 · company logo · bank/UPI · terms & signature block.
        </Typography>
      </Paper>
    </Stack>
  );
}
