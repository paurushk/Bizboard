import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AsyncSection } from './AsyncSection';

const base = { isLoading: false, isError: false, error: null, refetch: vi.fn() };

describe('AsyncSection', () => {
  it('shows an error with Retry and never renders children when the first load fails', () => {
    const children = vi.fn(() => <div>form</div>);
    render(<AsyncSection query={{ ...base, data: undefined, isError: true, error: new Error('boom') }}>{children}</AsyncSection>);
    expect(children).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });

  it('keeps showing data and warns when a refresh fails', () => {
    render(
      <AsyncSection query={{ ...base, data: { n: 1 }, isError: true, error: new Error('boom') }}>
        {(d) => <div>value {d.n}</div>}
      </AsyncSection>,
    );
    expect(screen.getByText('value 1')).toBeTruthy();
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('renders the empty state when told the data is empty', () => {
    render(
      <AsyncSection query={{ ...base, data: [] as number[] }} isEmpty={(d) => d.length === 0} empty={{ title: 'Nothing here' }}>
        {() => <div>list</div>}
      </AsyncSection>,
    );
    expect(screen.getByText('Nothing here')).toBeTruthy();
  });
});
