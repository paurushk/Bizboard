import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { a11yViolations, renderRoutes } from '@/test/careHarness';
import { AttachmentPanel } from './attachments';

const client = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  apiClient: client,
}));

const list = vi.fn();
const upload = vi.fn();
const remove = vi.fn();

function panel(props: { canEdit?: boolean; lockedReason?: string } = {}) {
  return renderRoutes(
    [{
      path: '/',
      element: (
        <AttachmentPanel
          queryKey={['files', 1]}
          list={list}
          upload={upload}
          remove={remove}
          canEdit={props.canEdit ?? true}
          lockedReason={props.lockedReason}
        />
      ),
    }],
    '/',
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  list.mockResolvedValue([{ id: 5, file: 50 }, { id: 6, file: 60 }]);
  upload.mockResolvedValue({});
  remove.mockResolvedValue(undefined);
  client.get.mockImplementation(async (url: string) => ({
    data: url.endsWith('/50/')
      ? { id: 50, url: '/media/photo.png', originalName: 'photo.png', contentType: 'image/png', size: 10 }
      : { id: 60, url: '/media/bill.pdf', originalName: 'bill.pdf', contentType: 'application/pdf', size: 10 },
  }));
});

describe('AttachmentPanel', () => {
  it('shows each file by name, with a thumbnail for pictures', async () => {
    const view = panel();
    expect(await screen.findByRole('link', { name: 'photo.png' })).toHaveAttribute('href', '/media/photo.png');
    expect(screen.getByRole('link', { name: 'bill.pdf' })).toBeInTheDocument();
    expect(view.container.querySelectorAll('img')).toHaveLength(1);
    expect(await a11yViolations(view.container)).toEqual([]);
  });

  it('uploads a chosen file', async () => {
    const user = userEvent.setup();
    panel();
    await screen.findByRole('link', { name: 'photo.png' });
    const file = new File(['x'], 'new.png', { type: 'image/png' });
    await user.upload(screen.getByLabelText('Add a file', { selector: 'input' }), file);
    await waitFor(() => expect(upload).toHaveBeenCalledWith(file));
  });

  it('asks before removing a file', async () => {
    const user = userEvent.setup();
    panel();
    await user.click(await screen.findByRole('button', { name: 'Remove photo.png' }));
    expect(remove).not.toHaveBeenCalled();
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith(5));
  });

  it('shows a refusal from the server beside the files', async () => {
    upload.mockRejectedValue(Object.assign(new Error('x'), {
      isAxiosError: true,
      response: { status: 400, data: { error: { message: 'This complaint is rejected. Re-open it first.' } } },
    }));
    const user = userEvent.setup();
    panel();
    await screen.findByRole('link', { name: 'photo.png' });
    await user.upload(screen.getByLabelText('Add a file', { selector: 'input' }), new File(['x'], 'a.png', { type: 'image/png' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Re-open it first');
  });

  it('replaces the buttons with the reason when the record is finished', async () => {
    panel({ lockedReason: 'This ticket is closed.' });
    expect(await screen.findByText('This ticket is closed.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a file' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Remove / })).not.toBeInTheDocument();
  });

  it('says so when there are no files, and offers no buttons to a reader', async () => {
    list.mockResolvedValue([]);
    panel({ canEdit: false });
    expect(await screen.findByText('No files attached.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a file' })).not.toBeInTheDocument();
  });
});
