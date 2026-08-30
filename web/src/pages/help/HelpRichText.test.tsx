import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HelpRichText } from './HelpRichText';

describe('HelpRichText', () => {
  it('renders bold labels and code values only', () => {
    const { container } = render(
      <HelpRichText text="Open **Settings → GST** and type `07AAAAA0000A1Z5`." />,
    );
    expect(container.querySelector('strong')?.textContent).toBe('Settings → GST');
    expect(container.querySelector('code')?.textContent).toBe('07AAAAA0000A1Z5');
    expect(container.textContent).toContain('Open');
  });

  it('resolves t: tokens to catalog labels', () => {
    const { container } = render(<HelpRichText text="Open **t:nav.settings** → **t:nav.gst**." />);
    const strongs = [...container.querySelectorAll('strong')].map((el) => el.textContent);
    expect(strongs).toEqual(['Settings', 'GST']);
  });
});
