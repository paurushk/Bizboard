import { render, screen } from '@testing-library/react';
import { PilotLimitsPage } from './PilotLimitsPage';

describe('PilotLimitsPage', () => {
  it('shows all seven pilot limitations', () => {
    render(<PilotLimitsPage />);
    const headings = screen.getAllByRole('heading');
    const text = headings.map((node) => node.textContent ?? '').join('\n');
    expect(text).toMatch(/not filing/i);
    expect(text).toMatch(/not an IRN/i);
    expect(text).toMatch(/weighted cost/i);
    expect(text).toMatch(/plaintext/i);
    expect(text).toMatch(/opt-in/i);
    expect(text).toMatch(/sandbox/i);
    expect(text).toMatch(/Payroll, manufacturing, and CRM/i);
    expect(headings).toHaveLength(8);
  });
});
