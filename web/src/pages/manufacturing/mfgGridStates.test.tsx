import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { Grid, type GridQuery } from './mfgShared';

/** QOS-0098: a manufacturing grid tells loading and failure apart from "nothing yet". */
const cols = [{ key: 'n', label: 'Name', render: (r: { id: number; name: string }) => r.name }];

function q(overrides: Partial<GridQuery>): GridQuery {
  return { isLoading: false, isError: false, error: null, refetch: vi.fn(), ...overrides };
}

describe('manufacturing Grid states', () => {
  it('shows loading, not the empty line, while the query runs', () => {
    render(<Grid rows={[]} cols={cols} rowKey={(r) => r.id} empty="No recipes yet" query={q({ isLoading: true })} />);
    expect(screen.getByText(t('common.loading'))).toBeInTheDocument();
    expect(screen.queryByText('No recipes yet')).not.toBeInTheDocument();
  });

  it('shows a retryable error, not the empty line, when the query fails', async () => {
    const refetch = vi.fn();
    render(
      <Grid
        rows={[]}
        cols={cols}
        rowKey={(r) => r.id}
        empty="No recipes yet"
        query={q({ isError: true, error: new Error('Server unavailable'), refetch })}
      />,
    );
    expect(screen.queryByText('No recipes yet')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /retry|try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('shows the empty line once the query has loaded nothing, and rows when it has some', () => {
    const { rerender } = render(<Grid rows={[]} cols={cols} rowKey={(r) => r.id} empty="No recipes yet" query={q({})} />);
    expect(screen.getByText('No recipes yet')).toBeInTheDocument();
    rerender(<Grid rows={[{ id: 1, name: 'Shelf' }]} cols={cols} rowKey={(r) => r.id} query={q({})} />);
    expect(screen.getByText('Shelf')).toBeInTheDocument();
  });
});
