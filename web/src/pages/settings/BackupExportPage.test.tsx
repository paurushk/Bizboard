import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { BackupExportPage } from '@/pages/settings/BackupExportPage';

const auth = vi.hoisted(() => ({ user: { id: 1, role: 'OWNER', companyId: 9 } as Record<string, unknown> }));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user }) }));

const api = vi.hoisted(() => ({
  exportReport: vi.fn(),
  exportTenantBackup: vi.fn(),
  getTenantBackupStatus: vi.fn(),
  restoreTenantSandbox: vi.fn(),
  getBackupSchedule: vi.fn(),
  setBackupSchedule: vi.fn(),
  takeBackupNow: vi.fn(),
  downloadFileAsset: vi.fn(),
  // D-13 retention panel (tested in DataRetentionPanel.test.tsx).
  getCompany: vi.fn(async () => ({ id: 1, dataRetentionDays: 90, dataDeletionDueAt: null })),
  updateCompany: vi.fn(),
}));
vi.mock('@/api/resources', () => api);
// WP-DL1 panel: no readable exports in these tests.
vi.mock('@/api/readableExport', () => ({
  listReadableExports: vi.fn(async () => []),
  requestReadableExport: vi.fn(),
  downloadReadableExport: vi.fn(),
}));

const SUMMARY = {
  sections: 21,
  records: 1234,
  customers: 40,
  suppliers: 12,
  products: 300,
  salesInvoices: 800,
  purchaseInvoices: 60,
  receipts: 500,
  journals: 0,
  filesWithBytes: 5,
  filesListedOnly: 2,
  fileWarnings: 0,
};
const STATUS = {
  lastExport: { exportedAt: '2026-10-18T10:00:00Z', bytes: 2_621_440, version: 3, by: 'Asha Owner', summary: SUMMARY },
  restoreIntoLiveEnabled: false,
  maxSandboxes: 3,
};

const SCHEDULE_OFF = { enabled: false, keep: 4, schedule: 'Every Sunday', backups: [], lastRun: null };
const BACKUP = { id: 31, createdAt: '2026-10-19T10:00:00Z', size: 2048, name: 'bizboard-auto-backup-1.bin' };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BackupExportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BackupExportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.user = { id: 1, role: 'OWNER', companyId: 9 };
    api.getTenantBackupStatus.mockResolvedValue(STATUS);
    api.getBackupSchedule.mockResolvedValue(SCHEDULE_OFF);
    api.setBackupSchedule.mockResolvedValue({ ...SCHEDULE_OFF, enabled: true });
    api.takeBackupNow.mockResolvedValue({ ...SCHEDULE_OFF, backups: [BACKUP], lastRun: { at: '2026-10-19T10:00:00Z', ok: true, error: '' } });
    api.downloadFileAsset.mockResolvedValue(new Blob(['x']));
    api.exportTenantBackup.mockResolvedValue({ url: 'blob:x', filename: 'b.bin' });
    api.exportReport.mockResolvedValue({ url: 'blob:y' });
    api.restoreTenantSandbox.mockResolvedValue({ companyId: 5, mode: 'sandbox', name: 'Shop [sandbox]', sandboxExpiresAt: '2026-11-18T10:00:00Z' });
    // jsdom has no object URLs; the page only creates and revokes them around a download.
    URL.revokeObjectURL = vi.fn();
  });

  it('says what the encrypted backup is, in plain words, including that only Bizboard can open it', async () => {
    renderPage();
    expect(await screen.findByText(t('backupPage.about'))).toBeTruthy();
    expect(t('backupPage.about')).toMatch(/Only Bizboard can open it/);
  });

  it('shows when the last backup was taken, by whom, how big, and what it held', async () => {
    renderPage();
    expect(await screen.findByText(new RegExp('Asha Owner'))).toBeTruthy();
    expect(screen.getByText(new RegExp('2\\.5 MB'))).toBeTruthy();
    expect(
      screen.getByText(
        t('backupPage.contents', {
          records: '1234', sections: '21', customers: '40', suppliers: '12', products: '300',
          sales: '800', purchases: '60', receipts: '500', journals: '0',
        }),
      ),
    ).toBeTruthy();
    expect(screen.getByText(t('backupPage.files', { inside: '5', listed: '2' }))).toBeTruthy();
    expect(screen.queryByText(new RegExp(t('backupPage.fileWarnings', { count: '0' })))).toBeNull();
  });

  it('warns when files could not be read into the backup', async () => {
    api.getTenantBackupStatus.mockResolvedValue({
      ...STATUS,
      lastExport: { ...STATUS.lastExport, summary: { ...SUMMARY, fileWarnings: 3 } },
    });
    renderPage();
    expect(await screen.findByText(t('backupPage.fileWarnings', { count: '3' }))).toBeTruthy();
  });

  it('says plainly when no backup has been taken', async () => {
    api.getTenantBackupStatus.mockResolvedValue({ ...STATUS, lastExport: null });
    renderPage();
    expect(await screen.findByText(t('backupPage.none'))).toBeTruthy();
  });

  it('downloads a backup and then refreshes the last-backup line', async () => {
    renderPage();
    await screen.findByText(new RegExp('Asha Owner'));
    api.getTenantBackupStatus.mockResolvedValue({
      ...STATUS,
      lastExport: { ...STATUS.lastExport, by: 'Someone Else' },
    });
    await userEvent.click(screen.getByRole('button', { name: t('backupPage.download') }));
    expect(api.exportTenantBackup).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(new RegExp('Someone Else'))).toBeTruthy();
  });

  it('offers a retry when the backup fails', async () => {
    api.exportTenantBackup.mockRejectedValueOnce(new Error('Export is limited to once every 10 minutes per company.'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('backupPage.download') }));
    expect(await screen.findByText(/limited to once every 10 minutes/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('backupPage.retry') }));
    await waitFor(() => expect(api.exportTenantBackup).toHaveBeenCalledTimes(2));
  });

  it('describes checking a backup as a separate copy and says live restore is a support matter', async () => {
    renderPage();
    expect(await screen.findByText(t('backupPage.checkHelp', { max: '3' }))).toBeTruthy();
    expect(screen.getByText(t('backupPage.liveHelp'))).toBeTruthy();
    expect(screen.queryByText(/destroy/i)).toBeNull();
  });

  it('checks a backup file and says where the copy is and when it expires', async () => {
    renderPage();
    await screen.findByText(t('backupPage.checkTitle'));
    const file = new File(['x'], 'backup.bin', { type: 'application/octet-stream' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, file);
    await userEvent.click(screen.getByRole('button', { name: t('backupPage.check') }));
    await waitFor(() => expect(api.restoreTenantSandbox).toHaveBeenCalledWith(file));
    expect(await screen.findByText(new RegExp('Shop \\[sandbox\\]'))).toBeTruthy();
  });

  it('shows the server reason when a check is refused', async () => {
    api.restoreTenantSandbox.mockRejectedValueOnce(new Error('Restore is limited to once every 10 minutes per company.'));
    renderPage();
    await screen.findByText(t('backupPage.checkTitle'));
    await userEvent.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(['x'], 'b.bin'));
    await userEvent.click(screen.getByRole('button', { name: t('backupPage.check') }));
    expect(await screen.findByText(/Restore is limited/)).toBeTruthy();
  });

  it('lists seven spreadsheet exports, including suppliers, items and price lists', async () => {
    renderPage();
    for (const type of ['sales', 'purchases', 'inventory', 'customers', 'suppliers', 'products', 'price-lists']) {
      expect(await screen.findByRole('button', { name: t('backupPage.exportButton', { name: t(`backupPage.export.${type}`) }) })).toBeTruthy();
    }
    await userEvent.click(screen.getByRole('button', { name: t('backupPage.exportButton', { name: t('backupPage.export.price-lists') }) }));
    expect(api.exportReport).toHaveBeenCalledWith('price-lists');
  });

  it('shows a failed export on its own button and lets it be tried again', async () => {
    api.exportReport.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    const button = await screen.findByRole('button', { name: t('backupPage.exportButton', { name: t('backupPage.export.suppliers') }) });
    await userEvent.click(button);
    expect(await screen.findByText(new RegExp(t('backupPage.exportFailed')))).toBeTruthy();
    await userEvent.click(button);
    expect(api.exportReport).toHaveBeenCalledTimes(2);
  });

  it('shows only the spreadsheet exports to a staff member who may export, never the backup', async () => {
    auth.user = { id: 2, role: 'SALES_STAFF', companyId: 9, canExport: true };
    renderPage();
    expect(await screen.findByText(t('backupPage.exportsTitle'))).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('backupPage.download') })).toBeNull();
    expect(api.getTenantBackupStatus).not.toHaveBeenCalled();
  });

  it('refuses someone who may not export', async () => {
    auth.user = { id: 3, role: 'VIEWER', companyId: 9 };
    renderPage();
    expect(screen.queryByText(t('backupPage.exportsTitle'))).toBeNull();
  });

  describe('automatic weekly backup (SET-08)', () => {
    it('is off by default and says no copies are being taken', async () => {
      renderPage();
      expect(await screen.findByText(t('backupPage.autoNoneYetOff'))).toBeTruthy();
      expect((screen.getByRole('checkbox', { name: t('backupPage.autoSwitch') }) as HTMLInputElement).checked).toBe(false);
    });

    it('switches on through the schedule endpoint', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('checkbox', { name: t('backupPage.autoSwitch') }));
      await waitFor(() => expect(api.setBackupSchedule).toHaveBeenCalledWith(true));
    });

    it('takes a copy now and lists it with a download', async () => {
      renderPage();
      const taken = { ...SCHEDULE_OFF, backups: [BACKUP], lastRun: { at: '2026-10-19T10:00:00Z', ok: true, error: '' } };
      api.getBackupSchedule.mockResolvedValue(taken);
      await userEvent.click(await screen.findByRole('button', { name: t('backupPage.autoNow') }));
      await waitFor(() => expect(api.takeBackupNow).toHaveBeenCalled());
      await userEvent.click(await screen.findByRole('button', { name: t('backupPage.autoDownload') }));
      await waitFor(() => expect(api.downloadFileAsset).toHaveBeenCalledWith(31));
    });

    it('shows a failed automatic backup with its reason', async () => {
      api.getBackupSchedule.mockResolvedValue({
        ...SCHEDULE_OFF,
        enabled: true,
        lastRun: { at: '2026-10-19T10:00:00Z', ok: false, error: 'disk full' },
      });
      renderPage();
      expect(await screen.findByText(/disk full/)).toBeTruthy();
    });

    it('shows an error with Retry when the schedule cannot load', async () => {
      api.getBackupSchedule.mockRejectedValue(new Error('down'));
      renderPage();
      expect(await screen.findByText(t('backupPage.autoLoadFailed'))).toBeTruthy();
    });
  });
});
