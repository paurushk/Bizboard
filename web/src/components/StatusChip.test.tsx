import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import { StatusChip } from '@/components/StatusChip';
import { theme } from '@/theme';

function renderWithTheme(ui: ReactElement) {
  return render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);
}

describe('StatusChip', () => {
  it('renders status label from i18n key', () => {
    renderWithTheme(<StatusChip tone="success" labelKey="status.completed" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('renders explicit label', () => {
    renderWithTheme(<StatusChip tone="warning" label="Below reorder" />);
    expect(screen.getByText('Below reorder')).toBeInTheDocument();
  });
});
