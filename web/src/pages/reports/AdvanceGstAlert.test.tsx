import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AdvanceGstAlert } from '@/pages/reports/AdvanceGstAlert';

describe('AdvanceGstAlert', () => {
  it('says how far the books differ from the return because advance tax is reported, not posted', () => {
    render(<AdvanceGstAlert data={{ advanceGst: { enabled: true, differenceFromBooks: '180.00', postedToBooks: false } }} />);
    expect(screen.getByText(/180\.00.*reported in this return but not posted to the books/i)).toBeTruthy();
  });

  it('says nothing when advance GST is not computed', () => {
    const { container } = render(<AdvanceGstAlert data={{ advanceGst: { enabled: false } }} />);
    expect(container.textContent).toBe('');
    const none = render(<AdvanceGstAlert data={{}} />);
    expect(none.container.textContent).toBe('');
  });
});
