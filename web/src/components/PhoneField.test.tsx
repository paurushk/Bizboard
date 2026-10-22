import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { t } from '@/i18n';
import { PhoneField } from '@/components/PhoneField';

function Harness({ initial = '' }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <PhoneField value={value} onChange={setValue} />
      <output data-testid="value">{value}</output>
    </>
  );
}

const numberBox = () => screen.getByLabelText(t('auth.phone')) as HTMLInputElement;
const stored = () => screen.getByTestId('value').textContent;

describe('PhoneField', () => {
  it('keeps a hand-typed + until the calling code names a country', async () => {
    render(<Harness />);
    await userEvent.type(numberBox(), '+97');
    expect(numberBox().value).toBe('+97');
    expect(stored()).toBe('');
    await userEvent.type(numberBox(), '1501234567');
    expect(screen.getByRole('combobox', { name: new RegExp(`^${t('phoneField.countryCode')}`) }).textContent).toBe('+971');
    expect(numberBox().value).toBe('501234567');
    expect(stored()).toBe('+971501234567');
  });

  it('does not strip 91 when an extra digit is typed onto a 91… number', async () => {
    render(<Harness initial="+919198765432" />);
    expect(numberBox().value).toBe('9198765432');
    await userEvent.type(numberBox(), '1');
    expect(numberBox().value).toBe('9198765432');
    expect(stored()).toBe('+919198765432');
  });

  it('keeps every digit when the country is changed and changed back', async () => {
    render(<Harness initial="+919876543210" />);
    const code = screen.getByRole('combobox', { name: new RegExp(`^${t('phoneField.countryCode')}`) });
    await userEvent.click(code);
    await userEvent.click(await screen.findByRole('option', { name: /United Arab Emirates/ }));
    expect(stored()).toBe('+9719876543210');
    await userEvent.click(code);
    await userEvent.click(await screen.findByRole('option', { name: /India/ }));
    expect(numberBox().value).toBe('9876543210');
    expect(stored()).toBe('+919876543210');
  });
});
