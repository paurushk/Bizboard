import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const refresh = vi.fn();

vi.mock('@/api/client', () => ({
  apiClient: { post: (...args: unknown[]) => post(...args) },
  getErrorMessage: () => 'failed',
  unwrapData: (body: { data?: unknown }) => (body && typeof body === 'object' && 'data' in body ? body.data : body),
  silentRefreshAccessToken: (...args: unknown[]) => refresh(...args),
}));

vi.mock('@/api/auth', () => ({
  fetchCurrentUser: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ setSession: vi.fn() }),
}));

vi.mock('@/auth/session', () => ({
  setAccessToken: vi.fn(),
}));

import { AcceptInvitePage } from './AcceptInvitePage';

describe('AcceptInvitePage', () => {
  beforeEach(() => {
    post.mockReset();
    refresh.mockReset();
  });

  it('a 200 mfa_required body does not call the refresh helper', async () => {
    post.mockResolvedValue({ data: { mfa_required: true, email: 'owner@example.test' } });
    render(
      <MemoryRouter initialEntries={['/invite/accept?token=abc']}>
        <AcceptInvitePage />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText(/password/i), 'StrongPass123!');
    await userEvent.click(screen.getByRole('button', { name: /activate account/i }));
    expect(post).toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });
});
