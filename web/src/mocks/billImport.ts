import type { ImportJob } from '@/types/domain';

/**
 * Mock-mode (`VITE_USE_MOCKS=true`, used by the e2e smoke runs) fixtures for the bill upload review:
 * job 1000 is a small three-row sales bill with row positions, job 999 a 150-row bill (windowed table).
 */
export const MOCK_SMALL_BILL_JOB = 1000;
export const MOCK_BIG_BILL_JOB = 999;

function mockLine(id: number, over: Record<string, unknown> = {}) {
  return {
    lineId: id,
    si: String(id),
    name: `Mock item ${id}`,
    sku: `MOCK-${id}`,
    hsnCode: '3402',
    quantity: '2',
    unitPrice: '100',
    gstRate: '18',
    mrp: '150',
    include: true,
    flags: [],
    errors: [],
    pcs: '',
    productMatch: { status: 'none', productId: null, candidates: [] },
    ...over,
  };
}

export function mockBillJob(id: number, kind: ImportJob['kind']): ImportJob | null {
  if (id !== MOCK_SMALL_BILL_JOB && id !== MOCK_BIG_BILL_JOB) return null;
  const count = id === MOCK_BIG_BILL_JOB ? 150 : 3;
  const lines = Array.from({ length: count }, (_, i) =>
    mockLine(i + 1, i === 0 ? { bbox: [0.08, 0.3, 0.84, 0.06] } : i === 1 ? { bbox: [0.08, 0.37, 0.84, 0.06] } : {}),
  );
  return {
    id,
    kind,
    status: 'PREVIEWED',
    totalRows: count,
    validRows: count,
    errorRows: 0,
    customer: null,
    supplier: null,
    fileName: 'mock-bill.png',
    clarifications: [],
    preview: {
      previewVersion: 1,
      billNumber: 'MOCK-1',
      billDate: '2026-07-05',
      buyerName: 'Mock Buyer LLP',
      supplierName: 'Mock Supplier',
      extractionConfidence: 0.9,
      priceMode: 'EXCLUSIVE',
      newProductCount: count,
      totals: {
        taxable: String(count * 200) + '.00',
        gst: String(count * 36) + '.00',
        cess: '0.00',
        charges: '0.00',
        invoiceDiscount: '0.00',
        grandTotal: String(count * 236) + '.00',
        roundedTotal: String(count * 236),
        includedLines: count,
        cgst: String(count * 18) + '.00',
        sgst: String(count * 18) + '.00',
        igst: '0.00',
        taxType: 'INTRA',
      },
      partyMatch: {
        status: 'none',
        id: null,
        candidates: [],
        extracted: { name: 'Mock Buyer LLP', gstin: '' },
        willCreate: true,
        notes: [],
      },
      companyGstinStatus: { status: 'defaulted_single', options: [], resolvedId: null },
      lines,
    },
  } as unknown as ImportJob;
}

/** A plain bill-shaped picture so the side-by-side viewer has something to show. */
export function mockBillImageUrl(): string {
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000" viewBox="0 0 800 1000">' +
    '<rect width="800" height="1000" fill="#fffef8" stroke="#999"/>' +
    '<text x="60" y="80" font-size="32" font-family="monospace">TAX INVOICE  MOCK-1</text>' +
    '<text x="60" y="140" font-size="22" font-family="monospace">Mock Buyer LLP</text>' +
    '<text x="68" y="325" font-size="22" font-family="monospace">1  Mock item 1   2  100.00  18%</text>' +
    '<text x="68" y="395" font-size="22" font-family="monospace">2  Mock item 2   2  100.00  18%</text>' +
    '</svg>';
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
