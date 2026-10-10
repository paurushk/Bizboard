import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Link, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { t } from '@/i18n';

vi.mock('@/lib/telemetry', () => ({ trackShopFloor: vi.fn() }));

function Page({ dirty, intercept = true }: { dirty: boolean; intercept?: boolean }) {
  return (
    <>
      <UnsavedChangesGuard when={dirty} interceptLinks={intercept} />
      <nav>
        <Link to="/elsewhere">Go elsewhere</Link>
        <Link to="/elsewhere" target="_blank">New tab</Link>
        <a href="https://other.example/page">External</a>
        <a href="/elsewhere" download>Download</a>
      </nav>
      <div>editor</div>
    </>
  );
}

function mount(dirty: boolean, intercept = true) {
  return render(
    <MemoryRouter initialEntries={['/editor']}>
      <Routes>
        <Route path="/editor" element={<Page dirty={dirty} intercept={intercept} />} />
        <Route path="/elsewhere" element={<div>other page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('UnsavedChangesGuard on a plain router (in-app links)', () => {
  it('lets a link through when nothing is unsaved', async () => {
    mount(false);
    await userEvent.click(screen.getByRole('link', { name: 'Go elsewhere' }));
    expect(await screen.findByText('other page')).toBeTruthy();
  });

  it('asks before an in-app link discards unsaved changes, and Stay keeps the page', async () => {
    mount(true);
    await userEvent.click(screen.getByRole('link', { name: 'Go elsewhere' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('common.stay') }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText('editor')).toBeTruthy();
    expect(screen.queryByText('other page')).toBeNull();
  });

  it('Leave goes to the link', async () => {
    mount(true);
    await userEvent.click(screen.getByRole('link', { name: 'Go elsewhere' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('common.leave') }));
    expect(await screen.findByText('other page')).toBeTruthy();
  });

  it('does nothing to links unless the form opts in', async () => {
    mount(true, false);
    await userEvent.click(screen.getByRole('link', { name: 'Go elsewhere' }));
    expect(await screen.findByText('other page')).toBeTruthy();
  });

  it('leaves new-tab, download, external and modified clicks alone', async () => {
    mount(true);
    for (const name of ['New tab', 'Download', 'External']) {
      await userEvent.click(screen.getByRole('link', { name }));
      expect(screen.queryByRole('dialog'), name).toBeNull();
    }
    fireEvent.click(screen.getByRole('link', { name: 'Go elsewhere' }), { ctrlKey: true });
    expect(screen.queryByRole('dialog'), 'ctrl+click').toBeNull();
  });
});
