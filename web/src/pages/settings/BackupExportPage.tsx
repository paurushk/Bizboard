import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { apiClient } from '@/api/client';
import { exportReport, exportTenantBackup, restoreTenantSandbox } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canExport, canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

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
  const fileRef = useRef<HTMLInputElement>(null);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreName, setRestoreName] = useState('');

  const zipMutation = useMutation({
    mutationFn: () => exportTenantBackup(),
    onSuccess: (r) => downloadBlobUrl(r.url, r.filename),
  });
  const restoreMutation = useMutation({
    mutationFn: (file: File) => restoreTenantSandbox(file),
    onSuccess: (r) => {
      setRestoreName(r.name);
      setRestoreFile(null);
      if (fileRef.current) fileRef.current.value = '';
    },
  });
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

  const isOwner = canManageUsers(user);
  const workersDown =
    health.data &&
    (health.data.celery === false ||
      health.data.celery_workers === false ||
      health.data.celery_beat === false);

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.backupExport')}</Typography>

      {isOwner ? (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {t('settings.backupEncryptedTitle')}
          </Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('settings.backupEncryptedHelp')}
          </Alert>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t('settings.backupKeyWarning')}
          </Alert>
          {workersDown ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t('settings.backupWorkersDown', { status: health.data?.status || '' })}
            </Alert>
          ) : null}
          {zipMutation.isError ? <HelpErrorAlert error={zipMutation.error} sx={{ mb: 2 }} /> : null}
          <Button
            variant="contained"
            disabled={zipMutation.isPending}
            onClick={() => zipMutation.mutate()}
          >
            {t('settings.backupDownloadEncrypted')}
          </Button>

          <Typography variant="subtitle1" sx={{ mt: 3, mb: 1 }}>
            {t('settings.backupRestoreTitle')}
          </Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('settings.backupRestoreHelp')}
          </Alert>
          {restoreMutation.isError ? (
            <HelpErrorAlert error={restoreMutation.error} sx={{ mb: 2 }} />
          ) : null}
          {restoreMutation.isSuccess && restoreName ? (
            <Alert severity="success" sx={{ mb: 2 }}>
              {t('settings.backupRestoreSuccess', { name: restoreName })}
            </Alert>
          ) : null}
          <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
            <Button variant="outlined" component="label">
              {t('settings.backupChooseFile')}
              <input
                ref={fileRef}
                type="file"
                hidden
                accept=".bin,application/octet-stream"
                onChange={(event) => setRestoreFile(event.target.files?.[0] ?? null)}
              />
            </Button>
            <Button
              variant="contained"
              disabled={!restoreFile || restoreMutation.isPending}
              onClick={() => restoreFile && restoreMutation.mutate(restoreFile)}
            >
              {t('settings.backupRestoreSandbox')}
            </Button>
            {restoreFile ? (
              <Typography variant="body2" color="text.secondary">
                {restoreFile.name}
              </Typography>
            ) : null}
          </Stack>
        </Paper>
      ) : null}

      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {t('settings.backupCsvTitle')}
        </Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('settings.backupCsvHelp')}
        </Alert>
        {exportMutation.isError ? (
          <HelpErrorAlert error={exportMutation.error} sx={{ mb: 2 }} />
        ) : null}
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {(['sales', 'purchases', 'inventory', 'customers'] as const).map((type) => (
            <Button
              key={type}
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate(type)}
            >
              {t('settings.backupExportRegister', {
                type: t(
                  type === 'sales'
                    ? 'nav.sales'
                    : type === 'purchases'
                      ? 'nav.purchases'
                      : type === 'inventory'
                        ? 'nav.inventory'
                        : 'nav.customers',
                ),
              })}
            </Button>
          ))}
        </Stack>
      </Paper>
    </Stack>
  );
}
