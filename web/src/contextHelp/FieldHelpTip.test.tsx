import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FieldHelpTip } from './FieldHelpTip';

describe('FieldHelpTip', () => {
  it('shows the tip on hover and is not a submit control', async () => {
    const user = userEvent.setup();
    render(
      <form>
        <FieldHelpTip slot="godown" title="Godown only" />
        <button type="submit">Save & Complete</button>
      </form>,
    );
    const tip = screen.getByTestId('field-help-tip');
    expect(tip).toHaveAttribute('type', 'button');
    expect(tip).toHaveAttribute('data-help-slot', 'godown');
    expect(screen.getByRole('button', { name: 'Save & Complete' })).toBeInTheDocument();
    await user.hover(tip);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Godown only');
  });
});
