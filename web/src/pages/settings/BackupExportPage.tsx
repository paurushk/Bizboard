import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient, getErrorMessage } from '@/api/client';
import { exportReport } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canExport, canManageUsers } from '@/utils/permissions';

function downloadBlobUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // BUG-614: the previous window.open-based flow never revoked the blob
  // URL — harmless once, but it leaks across repeated exports in one session.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

async function fetchSystemHealth() {
  const { data } = await apiClient.get('/health/?ready=1', {
    // Owner ready probes return 503 when workers are down — still need the payload.
    validateStatus: (s) => s === 200 || s === 503,
  });
  return data as {
    status: string;
    celery?: boolean;
    celery_workers?: boolean;
    celery_beat?: boolean;
    pdf_queue_depth?: number;
  };
}

export function BackupExportPage() {
  const { user } = useAuth();
  const exportMutation = useMutation({
    mutationFn: (type: 'sales' | 'purchases' | 'inventory' | 'customers') => exportReport(type),
    onSuccess: (r, type) => downloadBlobUrl(r.url, `${type}-export.csv`),
  });
  // UXW2-009: surface worker health for owners so async export stalls are actionable.
  const health = useQuery({
    queryKey: ['system-health-ready'],
    queryFn: fetchSystemHealth,
    enabled: canManageUsers(user),
    staleTime: 30_000,
    retry: false,
  });

  // BUG-405/612: this page's exports were gated on canManageUsers (owner
  // only) even though a dedicated canExport capability flag exists and is
  // configurable per staff member in Users Settings — an owner granting a
  // staff member "can export" had no way to actually let them use it.
  // (Hooks above this line, per Rules of Hooks.)
  if (!canExport(user)) return <ForbiddenPage />;

  const workersDown =
    health.data &&
    (health.data.celery === false ||
      health.data.celery_workers === false ||
      health.data.celery_beat === false);

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.backupExport')}</Typography>
      <Paper sx={{ p: 3 }}>
        <Alert severity="info" sx={{ mb: 2 }}>
          Full database backup is handled by ops (daily restore drill). From the app you can export
          business registers via the Report Service.
        </Alert>
        {workersDown ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Background workers look unhealthy (status: {health.data?.status}). Scheduled jobs,
            email digests, and some exports may stall until Celery worker/beat are running again.
          </Alert>
        ) : null}
        {exportMutation.isError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            {getErrorMessage(exportMutation.error)}
          </Alert>
        ) : null}
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {(['sales', 'purchases', 'inventory', 'customers'] as const).map((type) => (
            <Button
              key={type}
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate(type)}
            >
              Export {type}
            </Button>
          ))}
        </Stack>
      </Paper>
    </Stack>
  );
}
