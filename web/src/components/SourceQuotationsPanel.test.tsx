import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { SourceQuotationsPanel } from '@/components/SourceQuotationsPanel';
import { t } from '@/i18n';

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

const source = (over = {}) => ({
  id: 7, number: 'QTN-0007', status: 'CONVERTED', salesmanName: 'Asha', salesChannel: 'ONLINE', primary: true, ...over,
});

function mount(ui: ReactElement) {
  return render(
    <MemoryRouter>
      <Where />
      <Routes>
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SourceQuotationsPanel', () => {
  it('renders nothing without a source', () => {
    mount(<SourceQuotationsPanel sources={[]} />);
    expect(screen.queryByText(t('phase1.quotationSourcePanel'))).toBeNull();
  });

  it('links to the quotation and names who sold it', () => {
    mount(<SourceQuotationsPanel sources={[source()]} />);
    expect(screen.getByText(/Asha/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'QTN-0007' }));
    expect(screen.getByTestId('where').textContent).toBe('/sales/quotations/7');
  });

  it('notes when several quotations disagree', () => {
    mount(<SourceQuotationsPanel sources={[source(), source({ id: 8, number: 'QTN-0008', primary: false })]} differ />);
    expect(screen.getByText(t('phase1.quotationDifferNote'))).toBeTruthy();
  });
});
