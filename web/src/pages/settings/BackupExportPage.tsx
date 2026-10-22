import { useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  downloadFileAsset,
  exportReport,
  exportTenantBackup,
  getBackupSchedule,
  getTenantBackupStatus,
  restoreTenantSandbox,
  setBackupSchedule,
  takeBackupNow,
} from '@/api/resources';
import type { TenantBackupStatus } from '@/api/legacy/company';
import { useAuth } from '@/auth/AuthContext';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { ReadableExportPanel } from '@/components/settings/ReadableExportPanel';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { canExport, canManageUsers } from '@/utils/permissions';

const EXPORTS = ['sales', 'purchases', 'inventory', 'customers', 'suppliers', 'products', 'price-lists'] as const;
type ExportType = (typeof EXPORTS)[number];

function downloadBlobUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // BUG-614: revoke the blob URL so repeated exports do not leak.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '';
  if (bytes >= 1024 * 1024) return t('backupPage.bytes.mb', { n: (bytes / (1024 * 1024)).toFixed(1) });
  return t('backupPage.bytes.kb', { n: String(Math.max(1, Math.round(bytes / 1024))) });
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
}

/** SET-08: what the last backup held, from the audit trail, not a general description. */
function LastBackup({ status }: { status: TenantBackupStatus | undefined }) {
  const last = status?.lastExport;
  if (!last) return <Alert severity="warning">{t('backupPage.none')}</Alert>;
  const s = last.summary;
  return (
    <Stack spacing={0.5}>
      <Typography>
        {t('backupPage.last', { date: formatWhen(last.exportedAt), who: last.by || '—', size: formatBytes(last.bytes) })}
      </Typography>
      {s ? (
        <>
          <Typography variant="body2" color="text.secondary">
            {t('backupPage.contents', {
              records: String(s.records),
              sections: String(s.sections),
              customers: String(s.customers),
              suppliers: String(s.suppliers),
              products: String(s.products),
              sales: String(s.salesInvoices),
              purchases: String(s.purchaseInvoices),
              receipts: String(s.receipts),
              journals: String(s.journals),
            })}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('backupPage.files', { inside: String(s.filesWithBytes), listed: String(s.filesListedOnly) })}
          </Typography>
          {s.fileWarnings > 0 ? (
            <Alert severity="warning">{t('backupPage.fileWarnings', { count: String(s.fileWarnings) })}</Alert>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}

/** SET-08: a weekly encrypted copy kept on the server, for owners who switch it on. */
function AutomaticBackup() {
  const qc = useQueryClient();
  const schedule = useQuery({ queryKey: ['backup-schedule'], queryFn: getBackupSchedule });
  const refresh = (data: unknown) => {
    qc.setQueryData(['backup-schedule'], data);
    void qc.invalidateQueries({ queryKey: ['backup-schedule'] });
  };
  const toggle = useMutation({ mutationFn: (on: boolean) => setBackupSchedule(on), onSuccess: refresh });
  const now = useMutation({ mutationFn: takeBackupNow, onSuccess: refresh });
  const download = useMutation({
    mutationFn: async (file: { id: number; name: string }) => {
      const blob = await downloadFileAsset(file.id);
      downloadBlobUrl(URL.createObjectURL(blob), file.name);
    },
  });
  const data = schedule.data;
  return (
    <Stack spacing={1.5} component="section" aria-labelledby="auto-backup-title">
      <Typography id="auto-backup-title" variant="h6" sx={{ pt: 1 }}>
        {t('backupPage.autoTitle')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('backupPage.autoHelp', { keep: String(data?.keep ?? 4) })}
      </Typography>
      {schedule.isError ? (
        <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => void schedule.refetch()}>{t('backupPage.retry')}</Button>}>
          {t('backupPage.autoLoadFailed')}
        </Alert>
      ) : data ? (
        <>
          <FormControlLabel
            control={<Switch checked={data.enabled} disabled={toggle.isPending} onChange={(_, on) => toggle.mutate(on)} />}
            label={t('backupPage.autoSwitch')}
          />
          {toggle.isError ? <HelpErrorAlert error={toggle.error} /> : null}
          {data.lastRun ? (
            data.lastRun.ok ? (
              <Typography variant="body2">{t('backupPage.autoLastOk', { date: formatWhen(data.lastRun.at) })}</Typography>
            ) : (
              <Alert severity="error">{t('backupPage.autoLastFailed', { date: formatWhen(data.lastRun.at), reason: data.lastRun.error })}</Alert>
            )
          ) : (
            <Typography variant="body2" color="text.secondary">
              {data.enabled ? t('backupPage.autoNoneYetOn') : t('backupPage.autoNoneYetOff')}
            </Typography>
          )}
          {data.backups.length > 0 ? (
            <Stack spacing={0.5} component="ul" sx={{ m: 0, pl: 2 }}>
              {data.backups.map((b) => (
                <li key={b.id}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2">
                      {formatWhen(b.createdAt)} · {formatBytes(b.size)}
                    </Typography>
                    <Button size="small" disabled={download.isPending} onClick={() => download.mutate({ id: b.id, name: b.name })}>
                      {t('backupPage.autoDownload')}
                    </Button>
                  </Stack>
                </li>
              ))}
            </Stack>
          ) : null}
          {download.isError ? <HelpErrorAlert error={download.error} /> : null}
          {now.isError ? <HelpErrorAlert error={now.error} /> : null}
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" size="small" disabled={now.isPending} onClick={() => now.mutate()}>
              {now.isPending ? t('backupPage.downloading') : t('backupPage.autoNow')}
            </Button>
          </Stack>
        </>
      ) : null}
    </Stack>
  );
}

export function BackupExportPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [copy, setCopy] = useState<{ name: string; expiresAt: string | null } | null>(null);
  const [busyExport, setBusyExport] = useState<ExportType | null>(null);
  const [failedExport, setFailedExport] = useState<ExportType | null>(null);

  const isOwner = canManageUsers(user);
  const status = useQuery({
    queryKey: ['tenant-backup-status'],
    queryFn: getTenantBackupStatus,
    enabled: isOwner,
  });

  const zipMutation = useMutation({
    mutationFn: () => exportTenantBackup(),
    onSuccess: (r) => {
      downloadBlobUrl(r.url, r.filename);
      void qc.invalidateQueries({ queryKey: ['tenant-backup-status'] });
    },
  });
  const restoreMutation = useMutation({
    mutationFn: (file: File) => restoreTenantSandbox(file),
    onSuccess: (r) => {
      setCopy({ name: r.name, expiresAt: r.sandboxExpiresAt });
      setRestoreFile(null);
      if (fileRef.current) fileRef.current.value = '';
    },
  });
  const exportMutation = useMutation({
    mutationFn: (type: ExportType) => exportReport(type),
    onMutate: (type) => {
      setBusyExport(type);
      setFailedExport(null);
    },
    onSuccess: (r, type) => downloadBlobUrl(r.url, `${type}-export.csv`),
    onError: (_e, type) => setFailedExport(type),
    onSettled: () => setBusyExport(null),
  });

  // BUG-405/612: the CSV exports follow the per-person export capability, not just the owner role.
  if (!canExport(user)) return <ForbiddenPage />;

  return (
    <SettingsPage title={t('nav.backupExport')} purpose={t('backupPage.purpose')}>
      {isOwner ? (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">{t('backupPage.aboutTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('backupPage.about')}
            </Typography>
            {status.isError ? (
              <HelpErrorAlert error={status.error} />
            ) : status.isLoading ? null : (
              <LastBackup status={status.data} />
            )}
            {zipMutation.isError ? <HelpErrorAlert error={zipMutation.error} /> : null}
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Button variant="contained" disabled={zipMutation.isPending} onClick={() => zipMutation.mutate()}>
                {zipMutation.isPending ? t('backupPage.downloading') : t('backupPage.download')}
              </Button>
              {zipMutation.isError ? (
                <Button onClick={() => zipMutation.mutate()}>{t('backupPage.retry')}</Button>
              ) : null}
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {t('backupPage.downloadHelp')}
            </Typography>

            <AutomaticBackup />

            <ReadableExportPanel />

            <Typography variant="h6" sx={{ pt: 1 }}>
              {t('backupPage.checkTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('backupPage.checkHelp', { max: String(status.data?.maxSandboxes ?? 3) })}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('backupPage.liveHelp')}
            </Typography>
            {restoreMutation.isError ? <HelpErrorAlert error={restoreMutation.error} /> : null}
            {copy ? (
              <Alert severity="success">
                {copy.expiresAt
                  ? t('backupPage.checked', { name: copy.name, date: formatWhen(copy.expiresAt) })
                  : t('backupPage.checkedNoDate', { name: copy.name })}
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center" useFlexGap>
              <Button variant="outlined" component="label">
                {t('backupPage.chooseFile')}
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
                {restoreMutation.isPending ? t('backupPage.checking') : t('backupPage.check')}
              </Button>
              {restoreFile ? (
                <Typography variant="body2" color="text.secondary">
                  {restoreFile.name}
                </Typography>
              ) : null}
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{t('backupPage.exportsTitle')}</Typography>
          <Typography variant="body2" color="text.secondary">
            {t('backupPage.exportsHelp')}
          </Typography>
          {failedExport && exportMutation.isError ? (
            <HelpErrorAlert error={exportMutation.error} />
          ) : null}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {EXPORTS.map((type) => (
              <Button
                key={type}
                variant="outlined"
                color={failedExport === type ? 'error' : 'primary'}
                disabled={busyExport !== null}
                onClick={() => exportMutation.mutate(type)}
              >
                {busyExport === type
                  ? t('backupPage.exportBusy')
                  : t('backupPage.exportButton', { name: t(`backupPage.export.${type}`) })}
              </Button>
            ))}
          </Stack>
          {failedExport ? (
            <Typography variant="caption" color="error">
              {t('backupPage.exportFailed')} {t('backupPage.retry')}
            </Typography>
          ) : null}
        </Stack>
      </Paper>
    </SettingsPage>
  );
}
