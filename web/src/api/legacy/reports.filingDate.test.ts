import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { getGstr9FilingDate, setGstr9FilingDate } from './reports';

describe('GSTR-9 filing date api — QOS-0127', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads the filing date and maps the snake_case reply', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: { fy: '2025-26', filed_on: '2026-10-15', note_deadline: '2026-10-15' },
    });
    await expect(getGstr9FilingDate('2025-26')).resolves.toEqual({
      fy: '2025-26', filedOn: '2026-10-15', noteDeadline: '2026-10-15',
    });
    expect(get).toHaveBeenCalledWith('/reports/gstr9/filing-date/', { params: { fy: '2025-26' } });
  });

  it('maps a missing date to null', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: { fy: '2025-26', filed_on: null, note_deadline: '2026-11-30' },
    });
    expect((await getGstr9FilingDate('2025-26')).filedOn).toBeNull();
  });

  it('sends the date, and null to clear it', async () => {
    const put = vi.spyOn(apiClient, 'put').mockResolvedValue({
      data: { fy: '2025-26', filed_on: null, note_deadline: '2026-11-30' },
    });
    await setGstr9FilingDate('2025-26', '2026-10-15');
    expect(put).toHaveBeenLastCalledWith('/reports/gstr9/filing-date/', { fy: '2025-26', filed_on: '2026-10-15' });
    await setGstr9FilingDate('2025-26', null);
    expect(put).toHaveBeenLastCalledWith('/reports/gstr9/filing-date/', { fy: '2025-26', filed_on: null });
  });
});
