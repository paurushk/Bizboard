import type { ReceiptSendResult } from '@/api/resources';

/** Open WhatsApp on this device with the message, so the person picks the chat. Nothing is recorded as delivered. */
export function openDeviceShare(result: ReceiptSendResult) {
  const text = result.text ?? result.documentUrl ?? '';
  if (typeof window !== 'undefined') {
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank', 'noopener');
  }
}
