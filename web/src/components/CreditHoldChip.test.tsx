import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CreditHoldChip } from '@/components/CreditHoldChip';

describe('CreditHoldChip', () => {
  it('renders the credit-hold label', () => {
    render(<CreditHoldChip />);
    expect(screen.getByText('Credit hold')).toBeTruthy();
  });
});
