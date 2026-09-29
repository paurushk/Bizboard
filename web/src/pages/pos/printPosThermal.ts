/**
 * CR-114: shared thermal print (or warn) after POS sale / offline flush.
 */
import { downloadInvoiceThermalPdf } from '@/api/resources';
import { printEscPos } from '@/lib/native';
import { printBlob } from '@/utils/blob';

export type ThermalWarn = { invoiceId: number; number: string };

/** Try thermal PDF; on failure return a warn payload for the caller to surface. */
export async function printPosThermalOrWarn(invoice: {
  id: number;
  number?: string | null;
}): Promise<ThermalWarn | null> {
  const receipt = `BizBoard\n${invoice.number ?? invoice.id}\n\n\n`;
  const bytes = new Uint8Array(receipt.length);
  for (let i = 0; i < receipt.length; i += 1) bytes[i] = receipt.charCodeAt(i);
  try {
    const mode = await printEscPos(bytes);
    if (mode === 'native') return null;
  } catch {
    // The Bluetooth plugin is missing or the printer refused the bytes.
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
