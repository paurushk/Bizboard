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

  it('DEP-09 — maps credit and debit note hits to their editors', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        credit_notes: [{ id: 3, kind: 'credit_note', number: 'SCN-3', party: 'Zenith', invoice_number: 'INV-9' }],
        debit_notes: [{ id: 4, kind: 'debit_note', number: 'SDN-4', party: 'Zenith', invoice_number: 'INV-9' }],
      },
    });
    const results = await universalSearch('Zenith');
    expect(results).toEqual([
      { id: 3, type: 'credit_note', title: 'SCN-3', subtitle: 'Zenith · INV-9', path: '/sales/credit-notes/3' },
      { id: 4, type: 'debit_note', title: 'SDN-4', subtitle: 'Zenith · INV-9', path: '/sales/debit-notes/4' },
    ]);
  });
});
