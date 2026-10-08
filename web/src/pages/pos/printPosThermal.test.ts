import { beforeEach, describe, expect, it, vi } from 'vitest';

const getSalesInvoice = vi.fn();
const downloadInvoiceThermalPdf = vi.fn();
const printEscPos = vi.fn();
const isNative = vi.fn();
const printBlob = vi.fn();

vi.mock('@/api/resources', () => ({
  getSalesInvoice: (...args: unknown[]) => getSalesInvoice(...args),
  downloadInvoiceThermalPdf: (...args: unknown[]) => downloadInvoiceThermalPdf(...args),
}));
vi.mock('@/lib/native', () => ({
  DRAWER_KICK: new Uint8Array([0x1b, 0x70]),
  isNative: () => isNative(),
  printEscPos: (...args: unknown[]) => printEscPos(...args),
}));
vi.mock('@/utils/blob', () => ({ printBlob: (...args: unknown[]) => printBlob(...args) }));

const { printPosThermalOrWarn } = await import('./printPosThermal');

const invoice = {
  number: 'INV-9',
  customerName: 'Ravi',
  invoiceDate: '2026-10-08',
  grandTotal: '118.00',
  items: [{ description: 'Widget', quantity: 1, lineTotal: '118.00', hsnCode: '1234', gstRate: '18', cgst: 9, sgst: 9, igst: 0 }],
};

beforeEach(() => {
  vi.clearAllMocks();
  getSalesInvoice.mockResolvedValue(invoice);
  downloadInvoiceThermalPdf.mockResolvedValue(new Blob(['pdf']));
});

describe('printPosThermalOrWarn', () => {
  it('sends a real bill to a native printer and skips the PDF', async () => {
    isNative.mockReturnValue(true);
    printEscPos.mockResolvedValue('native');
    expect(await printPosThermalOrWarn({ id: 9, number: 'INV-9' })).toBeNull();
    const bytes = printEscPos.mock.calls[0][0] as Uint8Array;
    const text = new TextDecoder().decode(bytes);
    expect(text).toContain('INV-9');
    expect(text).toContain('GST 18%');
    expect(Array.from(bytes.slice(-3))).toEqual([0x1d, 0x56, 0x00]);
    expect(downloadInvoiceThermalPdf).not.toHaveBeenCalled();
  });

  it('falls back to the PDF when the printer refuses the bytes', async () => {
    isNative.mockReturnValue(true);
    printEscPos.mockRejectedValue(new Error('no printer'));
    expect(await printPosThermalOrWarn({ id: 9, number: 'INV-9' })).toBeNull();
    expect(printBlob).toHaveBeenCalledTimes(1);
  });

  it('uses the PDF on the desktop browser', async () => {
    isNative.mockReturnValue(false);
    await printPosThermalOrWarn({ id: 9, number: 'INV-9' });
    expect(printEscPos).not.toHaveBeenCalled();
    expect(printBlob).toHaveBeenCalledTimes(1);
  });

  it('returns a warning when neither path prints', async () => {
    isNative.mockReturnValue(false);
    downloadInvoiceThermalPdf.mockRejectedValue(new Error('server down'));
    expect(await printPosThermalOrWarn({ id: 9, number: 'INV-9' })).toEqual({ invoiceId: 9, number: 'INV-9' });
  });
});
