import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { t } from '@/i18n';
import { universalSearch } from './misc';

describe('universalSearch', () => {
  afterEach(() => vi.restoreAllMocks());

  it('maps quotation hits to the quotation page', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: { quotations: [{ id: 7, kind: 'quotation', number: 'QTN-0007', status: 'DRAFT', customer_name: 'Zenith' }] },
    });
    const results = await universalSearch('QTN');
    expect(results).toEqual([
      { id: 7, type: 'quotation', title: 'QTN-0007', subtitle: `${t('nav.quotations')} · Zenith`, path: '/sales/quotations/7' },
    ]);
  });
});
