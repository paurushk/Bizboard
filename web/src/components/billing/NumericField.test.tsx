// F2-006: amountReceived/amountPaid had no ceiling -- a typo could
// auto-create an overpayment receipt. NumericField gained a `max` prop;
// this pins its clamping behaviour directly.
import { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NumericField } from './NumericField';

function Harness({ max, initial = 0 }: { max?: number; initial?: number }) {
  const [value, setValue] = useState(initial);
  return (
    <NumericField
      value={value}
      onValueChange={(n: number) => setValue(n)}
      min={0}
      max={max}
      decimals={2}
      inputProps={{ 'aria-label': 'amount' }}
    />
  );
}

describe('NumericField max clamp', () => {
  it('clamps a typed value above max down to max on blur', () => {
    render(<Harness max={1180} />);
    const input = screen.getByLabelText('amount') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '5000' } });
    fireEvent.blur(input);
    expect(input.value).toBe('1180');
  });

  it('leaves a value at or below max untouched', () => {
    render(<Harness max={1180} />);
    const input = screen.getByLabelText('amount') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '900' } });
    fireEvent.blur(input);
    expect(input.value).toBe('900');
  });

  it('still clamps to min when max is not set', () => {
    render(<Harness />);
    const input = screen.getByLabelText('amount') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '50' } });
    fireEvent.blur(input);
    expect(input.value).toBe('50');
  });

  it('onValueChange receives the clamped value immediately, not just on blur', () => {
    const onValueChange = vi.fn();
    render(
      <NumericField
        value={0}
        onValueChange={onValueChange}
        min={0}
        max={100}
        decimals={2}
        inputProps={{ 'aria-label': 'amount2' }}
      />,
    );
    const input = screen.getByLabelText('amount2') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '250' } });
    expect(onValueChange).toHaveBeenCalledWith(100);
  });
});
