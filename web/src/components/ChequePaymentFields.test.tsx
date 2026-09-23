import type { ReactElement } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';

const uploadFile = vi.fn(async () => ({ id: 99, url: 'blob:cheque' }));

vi.mock('@/api/resources', () => ({
  uploadFile: (...args: unknown[]) => uploadFile(...(args as [File, string])),
}));

function wrap(ui: ReactElement) {
  return render(ui);
}

const EMPTY: ChequePaymentValues = { chequeNumber: '', chequeBankName: '', chequeDate: '2026-09-22' };

describe('ChequePaymentFields', () => {
  it('renders number, bank, date, and image controls', () => {
    wrap(<ChequePaymentFields value={EMPTY} onChange={() => undefined} />);
    expect(screen.getByLabelText(/cheque number/i)).toBeTruthy();
    expect(screen.getByLabelText(/cheque bank/i)).toBeTruthy();
    expect(screen.getByLabelText(/cheque date/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /cheque image/i })).toBeTruthy();
  });

  it('uploads a cheque image and reports the file id', async () => {
    const onChange = vi.fn();
    wrap(<ChequePaymentFields value={EMPTY} onChange={onChange} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([0xff, 0xd8])], 'cheque.jpg', { type: 'image/jpeg' });
    await userEvent.upload(input, file);
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ chequeImage: 99 })),
    );
    expect(uploadFile).toHaveBeenCalled();
    expect(await screen.findByText('cheque.jpg')).toBeTruthy();
  });
});
