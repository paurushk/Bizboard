import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LimitedAccessLanding } from '@/pages/LimitedAccessLanding';
import { t } from '@/i18n';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'v@x.test', fullName: 'Viewer', role: 'VIEWER', companyId: 1, capabilities: {} },
  }),
}));

function tree() {
  return (
    <MemoryRouter initialEntries={['/']}>
      <LimitedAccessLanding />
    </MemoryRouter>
  );
}

describe('LimitedAccessLanding welcome message', () => {
  afterEach(() => localStorage.clear());

  it('welcomes a user who was just given a role, once', () => {
    localStorage.setItem('bb_role_welcome', '1');
    const first = render(tree());
    expect(screen.getByText(t('landing.roleWelcome'))).toBeTruthy();
    // The flag is consumed, so a later visit does not repeat it.
    expect(localStorage.getItem('bb_role_welcome')).toBeNull();
    first.unmount();

    render(tree());
    expect(screen.queryByText(t('landing.roleWelcome'))).toBeNull();
  });

  it('keeps the welcome on screen when the page re-renders', () => {
    localStorage.setItem('bb_role_welcome', '1');
    const { rerender } = render(tree());
    rerender(tree());
    expect(screen.getByText(t('landing.roleWelcome'))).toBeTruthy();
  });

  it('shows no welcome when the flag is not set', () => {
    render(tree());
    expect(screen.queryByText(t('landing.roleWelcome'))).toBeNull();
  });
});
