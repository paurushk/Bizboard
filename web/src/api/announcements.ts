/** WP-CM3: staff announcements and the per-user "What's new" read marker. */
import { apiClient, shouldUseMocks, unwrapData } from './client';

export interface Announcement {
  id: number;
  severity: 'info' | 'warning' | 'error';
  textEn: string;
  textHi: string;
  endsAt: string;
}

export async function listAnnouncements(): Promise<Announcement[]> {
  if (shouldUseMocks()) return [];
  const { data } = await apiClient.get('/announcements/');
  const body = unwrapData<Announcement[]>(data);
  return Array.isArray(body) ? body : [];
}

export async function getWhatsNewSeen(): Promise<string> {
  if (shouldUseMocks()) return '';
  const { data } = await apiClient.get('/whats-new/seen/');
  return String(unwrapData<{ seen?: string }>(data)?.seen ?? '');
}

export async function markWhatsNewSeen(id: string): Promise<string> {
  const { data } = await apiClient.post('/whats-new/seen/', { seen: id });
  return String(unwrapData<{ seen?: string }>(data)?.seen ?? id);
}
