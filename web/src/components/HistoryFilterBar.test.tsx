import type { ReactElement } from 'react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import {
  HistoryFilterBar,
  EMPTY_HISTORY_FILTERS,
  dateRangeForPreset,
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

  it('emits a date range when a preset is clicked', async () => {
    const user = userEvent.setup();
    function PresetHarness() {
      const [value, setValue] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
      return (
        <>
          <HistoryFilterBar value={value} onChange={setValue} dateRangePresets />
          <output data-testid="state">{JSON.stringify(value)}</output>
        </>
      );
    }
    renderWithTheme(<PresetHarness />);
    await user.click(screen.getByText('Today'));
    const parsed = JSON.parse(screen.getByTestId('state').textContent || '{}') as HistoryFilters;
    expect(parsed.dateFrom).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(parsed.dateFrom).toBe(parsed.dateTo);
  });

  it('shows bulk selection count and actions', () => {
    renderWithTheme(
      <HistoryFilterBar
        value={EMPTY_HISTORY_FILTERS}
        onChange={() => undefined}
        bulkSelectedCount={3}
        bulkActions={<button type="button">Download</button>}
      />,
    );
    expect(screen.getByText(/3 selected/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument();
  });

  it('BUG-UI-028 uses the Indian financial year and quarters', () => {
    const now = new Date(2026, 9, 4);
    expect(dateRangeForPreset('currentFY', now)).toEqual({ dateFrom: '2026-04-01', dateTo: '2027-03-31' });
    expect(dateRangeForPreset('previousFY', now)).toEqual({ dateFrom: '2025-04-01', dateTo: '2026-03-31' });
    expect(dateRangeForPreset('q1', now)).toEqual({ dateFrom: '2026-04-01', dateTo: '2026-06-30' });
    expect(dateRangeForPreset('q4', now)).toEqual({ dateFrom: '2027-01-01', dateTo: '2027-03-31' });
    const january = new Date(2026, 0, 15);
    expect(dateRangeForPreset('currentFY', january).dateFrom).toBe('2025-04-01');
  });
});
