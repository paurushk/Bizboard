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

describe('NumericField follows its value', () => {
  const field = (value: number) => (
    <NumericField value={value} onValueChange={() => {}} decimals={2} inputProps={{ 'aria-label': 'follow' }} />
  );

  it('shows a new value from outside while the field is not focused', () => {
    const { rerender } = render(field(5));
    const input = screen.getByLabelText('follow') as HTMLInputElement;
    expect(input.value).toBe('5');
    rerender(field(7.5));
    expect(input.value).toBe('7.5');
  });

  it('never overwrites what the user is typing, even if the value changes from outside', () => {
    const { rerender } = render(field(5));
    const input = screen.getByLabelText('follow') as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '12' } });
    rerender(field(7));
    expect(input.value).toBe('12');
  });

  it('shows an empty box for zero', () => {
    render(field(0));
    expect((screen.getByLabelText('follow') as HTMLInputElement).value).toBe('');
  });
});
