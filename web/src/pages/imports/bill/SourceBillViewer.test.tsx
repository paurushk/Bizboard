import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SourceBillViewer } from './SourceBillViewer';

const api = vi.hoisted(() => ({ fetchImportSourceFile: vi.fn() }));
vi.mock('@/api/resources', () => api);

beforeEach(() => {
  vi.clearAllMocks();
  URL.revokeObjectURL = vi.fn();
  api.fetchImportSourceFile.mockResolvedValue({ url: 'blob:bill-1', contentType: 'image/png' });
});

describe('SourceBillViewer', () => {
  it('fetches the uploaded bill for its job and shows it as a picture', async () => {
    render(<SourceBillViewer jobId={7} />);
    const img = await screen.findByRole('img', { name: 'Original bill' });
    expect(img).toHaveAttribute('src', 'blob:bill-1');
    expect(api.fetchImportSourceFile).toHaveBeenCalledWith(7);
  });

  it('shows a spinner until the file arrives', async () => {
    let resolve!: (v: { url: string; contentType: string }) => void;
    api.fetchImportSourceFile.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<SourceBillViewer jobId={7} />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    resolve({ url: 'blob:late', contentType: 'image/png' });
    expect(await screen.findByRole('img', { name: 'Original bill' })).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('says so when the file cannot be shown, and offers no zoom for nothing', async () => {
    api.fetchImportSourceFile.mockRejectedValue(new Error('gone'));
    render(<SourceBillViewer jobId={7} />);
    expect(await screen.findByText('The original file could not be shown.')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Original bill' })).not.toBeInTheDocument();
  });

  it('zooms in and out within limits', async () => {
    const user = userEvent.setup();
    render(<SourceBillViewer jobId={7} />);
    const img = await screen.findByRole('img', { name: 'Original bill' });
    const wrapper = img.parentElement as HTMLElement;
    expect(wrapper).toHaveStyle({ width: '100%' });
    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(wrapper).toHaveStyle({ width: '125%' });
    for (let i = 0; i < 20; i += 1) await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(wrapper).toHaveStyle({ width: '400%' });
    for (let i = 0; i < 30; i += 1) await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    expect(wrapper).toHaveStyle({ width: '50%' });
  });

  it('outlines the highlighted row at its position on the picture', async () => {
    const { rerender } = render(<SourceBillViewer jobId={7} />);
    await screen.findByRole('img', { name: 'Original bill' });
    expect(screen.queryByTestId('bill-row-highlight')).not.toBeInTheDocument();
    rerender(<SourceBillViewer jobId={7} highlight={[0.1, 0.2, 0.8, 0.05]} />);
    expect(screen.getByTestId('bill-row-highlight')).toHaveStyle({
      left: '10%',
      top: '20%',
      width: '80%',
      height: '5%',
    });
    rerender(<SourceBillViewer jobId={7} highlight={[0.1, 0.2]} />);
    expect(screen.queryByTestId('bill-row-highlight')).not.toBeInTheDocument();
    rerender(<SourceBillViewer jobId={7} highlight={null} />);
    expect(screen.queryByTestId('bill-row-highlight')).not.toBeInTheDocument();
  });

  it('shows a PDF in an embedded viewer, with no zoom buttons or outline', async () => {
    api.fetchImportSourceFile.mockResolvedValue({ url: 'blob:pdf', contentType: 'application/pdf' });
    const { container } = render(<SourceBillViewer jobId={7} highlight={[0.1, 0.2, 0.8, 0.05]} />);
    await waitFor(() => expect(container.querySelector('object[type="application/pdf"]')).toBeTruthy());
    expect(container.querySelector('object')).toHaveAttribute('data', 'blob:pdf');
    expect(screen.queryByRole('button', { name: 'Zoom in' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('bill-row-highlight')).not.toBeInTheDocument();
  });

  it('lets go of the temporary file address when it goes away', async () => {
    const { unmount } = render(<SourceBillViewer jobId={7} />);
    await screen.findByRole('img', { name: 'Original bill' });
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:bill-1');
  });

  it('lets go of a file that arrives after it was closed', async () => {
    let resolve!: (v: { url: string; contentType: string }) => void;
    api.fetchImportSourceFile.mockReturnValue(new Promise((r) => (resolve = r)));
    const { unmount } = render(<SourceBillViewer jobId={7} />);
    unmount();
    resolve({ url: 'blob:too-late', contentType: 'image/png' });
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:too-late'));
  });
});
