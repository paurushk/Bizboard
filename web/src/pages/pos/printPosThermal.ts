/**
 * CR-114: shared thermal print (or warn) after POS sale / offline flush.
 */
import { downloadInvoiceThermalPdf, getSalesInvoice } from '@/api/resources';
import { DRAWER_KICK, isNative, printEscPos } from '@/lib/native';
import { printBlob } from '@/utils/blob';
import { encodeEscPosReceipt } from '@/pages/pos/escposReceipt';

export { DRAWER_KICK };

function hasNonAscii(text: string): boolean {
  for (const ch of text) {
    if (ch.charCodeAt(0) > 127) return true;
  }
  return false;
}

export type ThermalWarn = { invoiceId: number; number: string };

/** Native printers get a real ESC/POS bill. Every other screen gets the PDF. */
export async function printPosThermalOrWarn(invoice: {
  id: number;
  number?: string | null;
}): Promise<ThermalWarn | null> {
  if (isNative()) {
    try {
      const full = await getSalesInvoice(invoice.id);
      const unicode = (full.items ?? [])
        .map((item) => item.description || item.productName || '')
        .filter(hasNonAscii);
      const bytes = encodeEscPosReceipt({
        rasterLines: unicode,
        number: full.number ?? invoice.number,
        customerName: full.customerName,
        invoiceDate: full.invoiceDate,
        grandTotal: full.grandTotal,
        pulseDrawer: true,
        items: (full.items ?? []).map((item) => ({
          name: item.description || item.productName,
          quantity: item.quantity,
          lineTotal: item.lineTotal,
          hsn: item.hsnCode,
          gstRate: item.gstRate,
          tax: Number(item.cgst || 0) + Number(item.sgst || 0) + Number(item.igst || 0),
        })),
        paperColumns: (typeof localStorage !== 'undefined' && localStorage.getItem('bb_pos_paper_mm') === '80') ? 48 : 32,
      });
      const mode = await printEscPos(bytes);
      if (mode === 'native') return null;
    } catch {
      // The printer plugin is missing or refused the bill. The PDF is next.
    }
  }
  try {
    const blob = await downloadInvoiceThermalPdf(invoice.id);
    printBlob(blob);
    return null;
  } catch {
    return {
      invoiceId: invoice.id,
      number: String(invoice.number ?? `#${invoice.id}`),
    };
  }
}
