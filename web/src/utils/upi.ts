import { isValidUpiVpa } from '@/utils/gst';

export interface UpiUriParams {
  pa: string; // Payee VPA
  pn?: string; // Payee Name
  am: number | string; // Amount
  tn?: string; // Transaction Note
}

/**
 * Builds an NPCI-compliant UPI Intent URI.
 * Example: upi://pay?pa=merchant@upi&pn=Store&am=500.00&cu=INR&tn=Invoice_INV-101
 */
export function buildUpiUri(params: UpiUriParams): string {
  const pa = (params.pa || '').trim();
  if (!isValidUpiVpa(pa)) {
    return '';
  }
  const rawNum = typeof params.am === 'string' ? parseFloat(params.am) : params.am;
  const num = Number.isFinite(rawNum) ? Math.max(0, rawNum) : 0;
  const am = num.toFixed(2);
  const search = new URLSearchParams();
  search.set('pa', pa);
  if (params.pn) search.set('pn', params.pn.trim());
  search.set('am', am);
  search.set('cu', 'INR');
  if (params.tn) search.set('tn', params.tn.trim());

  // URLSearchParams writes a space as '+', which UPI intent parsers show literally ("Sharma+Traders").
  return `upi://pay?${search.toString().replace(/\+/g, '%20')}`;
}

export type AgingCohort = 'UPCOMING' | 'OVERDUE_1_15' | 'OVERDUE_16_45' | 'CRITICAL_45_PLUS';

export function getAgingCohort(daysOverdue: number): AgingCohort {
  if (daysOverdue <= 0) return 'UPCOMING';
  if (daysOverdue <= 15) return 'OVERDUE_1_15';
  if (daysOverdue <= 45) return 'OVERDUE_16_45';
  return 'CRITICAL_45_PLUS';
}

export interface DunningMessageParams {
  customerName: string;
  companyName: string;
  invoiceNumber: string;
  amount: number | string;
  daysOverdue: number;
  upiUri?: string;
}

/**
 * Generates an intelligent, tailored WhatsApp collection reminder based on aging severity.
 */
export function buildDunningMessage(params: DunningMessageParams): string {
  const cohort = getAgingCohort(params.daysOverdue);
  const formattedAmount = `₹${parseFloat(String(params.amount || 0)).toFixed(2)}`;
  const upiLinkText = params.upiUri ? `\n\n👉 Pay instantly via UPI:\n${params.upiUri}` : '';

  switch (cohort) {
    case 'UPCOMING':
      return (
        `Dear ${params.customerName},\n\n` +
        `This is a gentle courtesy reminder from ${params.companyName}. ` +
        `Invoice #${params.invoiceNumber} for ${formattedAmount} is coming due shortly.\n\n` +
        `We appreciate your prompt settlement.` +
        upiLinkText
      );

    case 'OVERDUE_1_15':
      return (
        `Dear ${params.customerName},\n\n` +
        `Your account with ${params.companyName} shows an overdue balance of ${formattedAmount} for Invoice #${params.invoiceNumber} ` +
        `(${params.daysOverdue} days past due).\n\n` +
        `Kindly clear this pending invoice today to ensure smooth ongoing supplies.` +
        upiLinkText
      );

    case 'OVERDUE_16_45':
      return (
        `Dear ${params.customerName},\n\n` +
        `Notice regarding overdue payment with ${params.companyName}:\n` +
        `Invoice #${params.invoiceNumber} for ${formattedAmount} is overdue by ${params.daysOverdue} days.\n\n` +
        `Please settle immediately to avoid any temporary hold on future billing or credit privileges.` +
        upiLinkText
      );

    case 'CRITICAL_45_PLUS':
    default:
      return (
        `URGENT NOTICE — ${params.companyName}\n\n` +
        `Dear ${params.customerName},\n` +
        `Invoice #${params.invoiceNumber} for ${formattedAmount} has been severely overdue for ${params.daysOverdue} days.\n\n` +
        `Please arrange payment immediately or contact our accounts desk today to avoid account escalation.` +
        upiLinkText
      );
  }
}

/**
 * Builds a direct WhatsApp share click-to-chat URL.
 */
export function buildWhatsAppShareUrl(phone: string, text: string): string {
  const digits = (phone || '').replace(/\D/g, '');
  const cleanPhone = digits.length === 10 ? `91${digits}` : digits;
  return `https://wa.me/${cleanPhone}?text=${encodeURIComponent(text)}`;
}
