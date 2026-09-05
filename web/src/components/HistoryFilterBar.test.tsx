import type { ReactElement } from 'react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import {
  HistoryFilterBar,
  EMPTY_HISTORY_FILTERS,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { theme } from '@/theme';

function renderWithTheme(ui: ReactElement) {
  return render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);
}

function Harness({ showDateRange = true }: { showDateRange?: boolean }) {
  const [value, setValue] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  return (
    <>
      <HistoryFilterBar
        value={value}
        onChange={setValue}
        showDateRange={showDateRange}
        statusOptions={[
          { value: 'DRAFT', label: 'Draft' },
          { value: 'COMPLETED', label: 'Completed' },
        ]}
      />
      <output data-testid="state">{JSON.stringify(value)}</output>
    </>
  );
}

describe('HistoryFilterBar', () => {
  it('toggles a status chip on and back off', async () => {
    const user = userEvent.setup();
    renderWithTheme(<Harness />);
    await user.click(screen.getByText('Draft'));
    expect(screen.getByTestId('state')).toHaveTextContent('"status":"DRAFT"');
    await user.click(screen.getByText('Draft'));
    expect(screen.getByTestId('state')).toHaveTextContent('"status":""');
  });

  it('selecting "All" clears the status', async () => {
    const user = userEvent.setup();
    renderWithTheme(<Harness />);
    await user.click(screen.getByText('Completed'));
    expect(screen.getByTestId('state')).toHaveTextContent('"status":"COMPLETED"');
    await user.click(screen.getByText('All'));
    expect(screen.getByTestId('state')).toHaveTextContent('"status":""');
  });

  it('types into the search field', async () => {
    const user = userEvent.setup();
    renderWithTheme(<Harness />);
    await user.type(screen.getByPlaceholderText('Search'), 'INV-42');
    expect(screen.getByTestId('state')).toHaveTextContent('"q":"INV-42"');
  });

  it('hides the date range when showDateRange is false', () => {
    renderWithTheme(<Harness showDateRange={false} />);
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument();
  });
});
