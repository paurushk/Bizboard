/**
 * CR-114: shared thermal print (or warn) after POS sale / offline flush.
 */
import { downloadInvoiceThermalPdf } from '@/api/resources';
import { printBlob } from '@/utils/blob';

export type ThermalWarn = { invoiceId: number; number: string };

/** Try thermal PDF; on failure return a warn payload for the caller to surface. */
export async function printPosThermalOrWarn(invoice: {
  id: number;
  number?: string | null;
}): Promise<ThermalWarn | null> {
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
