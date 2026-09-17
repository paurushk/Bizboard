import type { ReactElement } from 'react';
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

    const complete = screen.getByRole('button', { name: 'Save & Complete' });
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

    const complete = screen.getByRole('button', { name: 'Save & Complete' });
    expect(complete).toBeDisabled();
    await user.hover(complete.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Select a customer/supplier and at least one item with valid quantity to complete',
    );
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

    const complete = screen.getByRole('button', { name: 'Save & Complete' });
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

    const complete = screen.getByRole('button', { name: 'Save & Complete' });
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

    const complete = screen.getByRole('button', { name: 'Save & Complete' });
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

    const complete = screen.getByRole('button', { name: 'Save & Complete' });
    expect(complete).toBeEnabled();
    await user.click(screen.getByTestId('field-help-tip'));
    expect(onPrimarySave).not.toHaveBeenCalled();
    expect(complete).toBeEnabled();
    await user.click(complete);
    expect(onPrimarySave).toHaveBeenCalledTimes(1);
  });
});
