import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

/** WP-8: the help catalogue is fetched on first use; the `?` appears once it has arrived. */
describe('ContextHelp lazy catalogue', () => {
  it('renders nothing until the catalogue loads, then shows the page help button', async () => {
    vi.resetModules(); // a fresh loader: the test setup's preloaded copy is not used
    const loader = await import('./catalogLoader');
    expect(loader.loadedContextHelpCatalog()).toBeNull();
    const { ContextHelp } = await import('./ContextHelp');
    render(
      <MemoryRouter initialEntries={['/sales/new']}>
        <ContextHelp />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('context-help-trigger')).toBeNull();
    expect(await screen.findByTestId('context-help-trigger')).toBeInTheDocument();
    expect(loader.loadedContextHelpCatalog()).not.toBeNull();
  });
});
