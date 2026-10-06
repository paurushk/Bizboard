import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CreateDialog } from './CreateDialog';

describe('CreateDialog', () => {
  it('renders nothing until opened', () => {
    render(
      <CreateDialog open={false} onClose={() => undefined} title="New thing" submitLabel="Save thing" onSubmit={() => undefined}>
        <input aria-label="field" />
      </CreateDialog>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByLabelText('field')).toBeNull();
  });

  it('shows the form, submits and cancels', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(
      <CreateDialog open onClose={onClose} title="New thing" submitLabel="Save thing" onSubmit={onSubmit}>
        <input aria-label="field" />
      </CreateDialog>,
    );
    expect(screen.getByRole('dialog', { name: 'New thing' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save thing' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('disables submit when asked', () => {
    render(
      <CreateDialog open onClose={() => undefined} title="T" submitLabel="Go" onSubmit={() => undefined} submitDisabled>
        <span />
      </CreateDialog>,
    );
    expect(screen.getByRole('button', { name: 'Go' })).toBeDisabled();
  });
});
