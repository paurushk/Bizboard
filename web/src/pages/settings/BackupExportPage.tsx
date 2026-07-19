import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Navigate } from 'react-router-dom';
import { exportReport } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { canManageUsers } from '@/utils/permissions';

export function BackupExportPage() {
  const { user } = useAuth();
  if (!canManageUsers(user)) return <Navigate to="/" replace />;

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.backupExport')}</Typography>
      <Paper sx={{ p: 3 }}>
        <Alert severity="info" sx={{ mb: 2 }}>
          Full database backup is handled by ops (daily restore drill). From the app you can export
          business registers via the Report Service.
        </Alert>
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {(['sales', 'purchases', 'inventory', 'customers'] as const).map((type) => (
            <Button
              key={type}
              variant="outlined"
              onClick={() => void exportReport(type).then((r) => window.open(r.url, '_blank'))}
            >
              Export {type}
            </Button>
          ))}
        </Stack>
      </Paper>
    </Stack>
  );
}
