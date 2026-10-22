/** WP-ID1: hand the company to another owner. */
import { apiClient, unwrapData } from './client';

export async function startOwnershipTransfer(input: {
  toUserId: number;
  oldOwnerBecomes: 'MANAGER' | 'LEAVE';
  password: string;
  code?: string;
}): Promise<void> {
  await apiClient.post('/company/ownership/transfer/', {
    to_user_id: input.toUserId,
    old_owner_becomes: input.oldOwnerBecomes,
    password: input.password,
    code: input.code ?? '',
  });
}

export async function acceptOwnershipTransfer(token: string): Promise<void> {
  await apiClient.post('/company/ownership/accept/', { token });
}

export async function cancelOwnershipTransfer(): Promise<void> {
  await apiClient.post('/company/ownership/cancel/', {});
}

export async function getPendingOwnership(): Promise<{ pending: null | { kind: string; toEmail: string; expiresAt: string } }> {
  const { data } = await apiClient.get('/company/ownership/');
  return unwrapData(data);
}
