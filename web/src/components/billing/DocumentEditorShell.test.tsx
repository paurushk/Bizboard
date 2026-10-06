import { useState, type ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DocumentEditorShell } from '@/components/billing/DocumentEditorShell';

const gate = vi.hoisted(() => ({ writesBlocked: false }));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({
    writesBlocked: gate.writesBlocked,
    subscription: null,
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

function wrap(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

/** CG-33: disabled Complete can show a page-specific reason. */
describe('DocumentEditorShell — CG-33 complete-disabled reason', () => {
  it('shows the page-specific reason when Complete is disabled', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    wrap(
      <DocumentEditorShell
        title="Create Purchase Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete={false}
        primaryDisabledReason="Enter a batch number for each batch-tracked item to complete"
        isEdit={false}
        onPrimarySave={() => {}}
      >
        form
      </DocumentEditorShell>,
    );

    const complete = screen.getByRole('button', { name: /^Save & Complete/ });
    expect(complete).toBeDisabled();
    await user.hover(complete.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Enter a batch number for each batch-tracked item to complete',
    );
  });

  it('falls back to the generic complete reason when none is provided', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    wrap(
      <DocumentEditorShell
        title="Create Purchase Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete={false}
        isEdit={false}
        onPrimarySave={() => {}}
      >
        form
      </DocumentEditorShell>,
    );

    const complete = screen.getByRole('button', { name: /^Save & Complete/ });
    expect(complete).toBeDisabled();
    await user.hover(complete.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Select a customer/supplier and at least one item with valid quantity to complete',
    );
  });

  it('moves focus to the missing field when nothing is chosen yet', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    const onFocusMissing = vi.fn();
    wrap(
      <DocumentEditorShell
        title="New invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave={false}
        canComplete={false}
        isEdit={false}
        onPrimarySave={() => {}}
        onFocusMissing={onFocusMissing}
      >
        form
      </DocumentEditorShell>,
    );
    await user.click(screen.getByRole('button', { name: 'Go to the missing field' }));
    expect(onFocusMissing).toHaveBeenCalledOnce();
  });
});

describe('DocumentEditorShell — CG-13 / CG-24 writes blocked and CG-32 saving', () => {
  it('CG-13 / CG-24: names the subscription write block on Complete', async () => {
    gate.writesBlocked = true;
    const user = userEvent.setup();
    wrap(
      <DocumentEditorShell
        title="Create Sales Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete
        isEdit={false}
        onPrimarySave={() => {}}
      >
        form
      </DocumentEditorShell>,
    );

    const complete = screen.getByRole('button', { name: /^Save & Complete/ });
    expect(complete).toBeDisabled();
    await user.hover(complete.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(/read-only|suspended|trial/i);
    gate.writesBlocked = false;
  });

  it('CG-32: saving greys Complete with a named reason', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    wrap(
      <DocumentEditorShell
        title="Create Sales Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete
        saving
        isEdit={false}
        onPrimarySave={() => {}}
      >
        form
      </DocumentEditorShell>,
    );

    const complete = screen.getByRole('button', { name: /^Save & Complete/ });
    expect(complete).toBeDisabled();
    await user.hover(complete.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Saving…');
  });

  it('CG-04 / CG-18: preview-pending copy is shown as the Complete tooltip', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    wrap(
      <DocumentEditorShell
        title="Create Sales Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete={false}
        primaryDisabledReason="Waiting for tax preview from the server…"
        isEdit={false}
        onPrimarySave={() => {}}
      >
        form
      </DocumentEditorShell>,
    );

    const complete = screen.getByRole('button', { name: /^Save & Complete/ });
    expect(complete).toBeDisabled();
    await user.hover(complete.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(/preview/i);
  });
});

describe('DocumentEditorShell — Complete field tip', () => {
  it('does not fire Complete when the ⓘ tip is clicked', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    const onPrimarySave = vi.fn();
    wrap(
      <DocumentEditorShell
        title="Create Sales Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete
        isEdit={false}
        onPrimarySave={onPrimarySave}
      >
        form
      </DocumentEditorShell>,
    );

    const complete = screen.getByRole('button', { name: /^Save & Complete/ });
    expect(complete).toBeEnabled();
    await user.click(screen.getByTestId('field-help-tip'));
    expect(onPrimarySave).not.toHaveBeenCalled();
    expect(complete).toBeEnabled();
    await user.click(complete);
    expect(onPrimarySave).toHaveBeenCalledTimes(1);
  });
});

/** A dismissed error must come back when the same problem happens again on a retry. */
describe('DocumentEditorShell — dismissing an error', () => {
  function Harness({ onDismiss }: { onDismiss?: () => void }) {
    const [error, setError] = useState<string | null>('Insufficient stock for Widget');
    return (
      <MemoryRouter>
        <button type="button" onClick={() => setError('Insufficient stock for Widget')}>
          try again
        </button>
        <DocumentEditorShell
          title="Create Invoice"
          primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
          canSave
          canComplete
          isEdit={false}
          error={error}
          onDismissError={() => {
            onDismiss?.();
            setError(null);
          }}
          onPrimarySave={() => {}}
        >
          form
        </DocumentEditorShell>
      </MemoryRouter>
    );
  }

  it('shows the error and hides it when dismissed, telling the page', async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(<Harness onDismiss={onDismiss} />);
    expect(screen.getByText('Insufficient stock for Widget')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Insufficient stock for Widget')).toBeNull();
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('shows the same message again when it recurs after being dismissed', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Insufficient stock for Widget')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'try again' }));
    expect(await screen.findByText('Insufficient stock for Widget')).toBeTruthy();
  });

  it('shows a different message straight away', () => {
    const { rerender } = render(
      <MemoryRouter>
        <DocumentEditorShell
          title="Create Invoice"
          primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
          canSave
          canComplete
          isEdit={false}
          error="First problem"
          onPrimarySave={() => {}}
        >
          form
        </DocumentEditorShell>
      </MemoryRouter>,
    );
    expect(screen.getByText('First problem')).toBeTruthy();
    rerender(
      <MemoryRouter>
        <DocumentEditorShell
          title="Create Invoice"
          primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
          canSave
          canComplete
          isEdit={false}
          error="Second problem"
          onPrimarySave={() => {}}
        >
          form
        </DocumentEditorShell>
      </MemoryRouter>,
    );
    expect(screen.getByText('Second problem')).toBeTruthy();
    expect(screen.queryByText('First problem')).toBeNull();
  });

  it('BUG-UI-015 saves a draft and starts another when Complete is blocked', async () => {
    const user = userEvent.setup();
    const onSaveDraftAndNew = vi.fn();
    wrap(
      <DocumentEditorShell
        title="Create Invoice"
        primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
        canSave
        canComplete={false}
        isEdit={false}
        onPrimarySave={() => {}}
        onSaveDraftAndNew={onSaveDraftAndNew}
      >
        form
      </DocumentEditorShell>,
    );
    const button = screen.getByRole('button', { name: 'Save draft and start another' });
    expect(button).toBeEnabled();
    await user.click(button);
    expect(onSaveDraftAndNew).toHaveBeenCalledOnce();
  });
});

describe('DocumentEditorShell — a repeated error shows again after it was dismissed', () => {
  it('shows the same message again when it comes from a new failure', async () => {
    gate.writesBlocked = false;
    const user = userEvent.setup();
    function Harness() {
      const [failure, setFailure] = useState<{ id: number } | null>({ id: 1 });
      return (
        <DocumentEditorShell
          title="Create Invoice"
          primarySave={{ mode: 'complete', labelKey: 'billing.saveAndComplete' }}
          canSave
          canComplete
          isEdit={false}
          error={failure ? 'Insufficient stock for Widget' : null}
          errorSource={failure ?? undefined}
          onPrimarySave={() => setFailure({ id: (failure?.id ?? 0) + 1 })}
        >
          form
        </DocumentEditorShell>
      );
    }
    wrap(<Harness />);
    expect(await screen.findByText('Insufficient stock for Widget')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Insufficient stock for Widget')).not.toBeInTheDocument();
    // Clicking Complete again fails the same way: a new failure object with the same words.
    await user.click(screen.getByRole('button', { name: /^Save & Complete/ }));
    expect(await screen.findByText('Insufficient stock for Widget')).toBeInTheDocument();
  });
});
