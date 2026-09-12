import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { theme } from '@/theme';

/**
 * UX-001 regression (QOS-0024): the guard used to call `useBlocker` unconditionally,
 * which throws a runtime exception on a standard (non-data) router route. It now
 * bails out with `null` when there is no data-router context, and still registers
 * the `beforeunload` handler for the reload / tab-close case.
 */
function renderGuard(ui: ReactElement) {
  return render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);
}

describe('UnsavedChangesGuard', () => {
  afterEach(() => vi.restoreAllMocks());

  it('does not throw when rendered outside a data router (UX-001)', () => {
    // No RouterProvider / createBrowserRouter wrapper => no UNSAFE_DataRouterContext.
    expect(() => renderGuard(<UnsavedChangesGuard when />)).not.toThrow();
  });

  it('renders nothing outside a data router', () => {
    const { container } = renderGuard(<UnsavedChangesGuard when />);
    expect(container).toBeEmptyDOMElement();
  });

  it('registers a beforeunload listener while there are unsaved changes', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');

    const { rerender, unmount } = renderGuard(<UnsavedChangesGuard when />);
    expect(add).toHaveBeenCalledWith('beforeunload', expect.any(Function));

    rerender(<ThemeProvider theme={theme}><UnsavedChangesGuard when={false} /></ThemeProvider>);
    expect(remove).toHaveBeenCalledWith('beforeunload', expect.any(Function));

    unmount();
  });

  it('does not arm beforeunload when there is nothing to lose', () => {
    const add = vi.spyOn(window, 'addEventListener');
    renderGuard(<UnsavedChangesGuard when={false} />);
    expect(add).not.toHaveBeenCalledWith('beforeunload', expect.any(Function));
  });
});
