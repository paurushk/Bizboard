import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BoolChip, StatusChip } from '@/pages/phase/phaseShared';

describe('phase StatusChip (ACS-00)', () => {
  it.each([
    ['OPEN', 'Open'],
    ['SOFT_CLOSED', 'Soft-closed'],
    ['CLOSED', 'Closed'],
    ['ACTIVE', 'Active'],
    ['DISPOSED', 'Disposed'],
    ['REVERSED', 'Reversed'],
    ['VOID', 'Void'],
    ['POSTED', 'Posted'],
  ])('shows %s as a plain-language label', (code, label) => {
    render(<StatusChip value={code} />);
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByText(code)).toBeNull();
  });

  it('Title-cases a status it has no label for instead of showing the raw code', () => {
    render(<StatusChip value="AWAITING_REVIEW" />);
    expect(screen.getByText('Awaiting review')).toBeTruthy();
  });

  it('an explicit label wins', () => {
    render(<StatusChip value="OPEN" label="Mine" />);
    expect(screen.getByText('Mine')).toBeTruthy();
  });
});

describe('BoolChip', () => {
  it('uses the translated Yes/No', () => {
    const { rerender } = render(<BoolChip value />);
    expect(screen.getByText('Yes')).toBeTruthy();
    rerender(<BoolChip value={false} />);
    expect(screen.getByText('No')).toBeTruthy();
  });
});
