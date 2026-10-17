import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '@/components/ConfirmDialog';

describe('ConfirmDialog', () => {
  it('BUG-UI-005 requires the document number before a destructive confirm', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Cancel invoice"
        body="Type the number to cancel."
        requireTyped="INV-12"
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText('INV-12'), 'INV-12');
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('asks for nothing to be typed unless the caller opts in', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Clear the cart?"
        body="The lines on this bill will be removed."
        confirmColor="error"
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('ACS-00 holds the confirm until a reason is given and hands the reason back', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Void expense"
        body="A reason is required."
        requireReason={{ label: 'Reason for voiding' }}
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/Reason for voiding/), '   ');
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/Reason for voiding/), 'Entered twice');
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith('Entered twice');
  });
});
