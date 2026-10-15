import type { RecurringRun, RecurringRunNowResult, RecurringSchedule } from '@/api/legacy/sales';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';

export const CADENCE_OPTIONS: Array<{ value: string; labelKey: string }> = [
  { value: 'WEEKLY', labelKey: 'recurring.weekly' },
  { value: 'MONTHLY', labelKey: 'recurring.monthly' },
  { value: 'QUARTERLY', labelKey: 'recurring.quarterly' },
  { value: 'HALF_YEARLY', labelKey: 'recurring.halfYearly' },
  { value: 'ANNUALLY', labelKey: 'recurring.annually' },
];

export const STOP_STAGE_OPTIONS: Array<{ value: string; labelKey: string }> = [
  { value: 'INVOICE', labelKey: 'recurring.stopInvoice' },
  { value: 'SALES_ORDER', labelKey: 'recurring.stopSalesOrder' },
  { value: 'DELIVERY_CHALLAN', labelKey: 'recurring.stopDeliveryChallan' },
];

export function cadenceLabel(value: string): string {
  const hit = CADENCE_OPTIONS.find((c) => c.value === value);
  return hit ? t(hit.labelKey) : value;
}

export function stopStageLabel(value: string): string {
  const hit = STOP_STAGE_OPTIONS.find((c) => c.value === value);
  return hit ? t(hit.labelKey) : value;
}

export type LineDraft = {
  key: string;
  productId: number | null;
  product: Product | null;
  qty: string;
  price: string;
};

let lineCounter = 0;
export function newLine(partial: Partial<LineDraft> = {}): LineDraft {
  lineCounter += 1;
  return { key: `line-${lineCounter}`, productId: null, product: null, qty: '1', price: '', ...partial };
}

export function linesFromSchedule(schedule: RecurringSchedule): LineDraft[] {
  const items = schedule.lineTemplate?.items ?? [];
  if (!items.length) return [newLine()];
  return items.map((item) =>
    newLine({
      productId: Number(item.product),
      qty: String(item.quantity ?? '1'),
      price: item.unitPrice == null ? '' : String(item.unitPrice),
    }),
  );
}

export function isValidLine(line: LineDraft): boolean {
  return Boolean(line.productId) && Number(line.qty) > 0 && !(line.price !== '' && Number(line.price) < 0);
}

export function templateItems(lines: LineDraft[]) {
  return lines
    .filter((l) => l.productId && Number(l.qty) > 0)
    .map((l) => ({
      product: Number(l.productId),
      quantity: Number(l.qty),
      unitPrice: l.price === '' ? undefined : Number(l.price),
    }));
}

const pad = (n: number) => String(n).padStart(2, '0');

/** ISO instant -> value for <input type="datetime-local"> in the viewer's time zone. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

export type ScheduleForm = {
  customerId: number | null;
  cadence: string;
  nextRunAt: string;
  stopStage: string;
  autoComplete: boolean;
  endDate: string;
  maxRuns: string;
  notes: string;
  additionalCharges: string;
  invoiceDiscount: string;
  lines: LineDraft[];
};

export function emptyForm(): ScheduleForm {
  return {
    customerId: null,
    cadence: 'MONTHLY',
    nextRunAt: '',
    stopStage: 'INVOICE',
    autoComplete: false,
    endDate: '',
    maxRuns: '',
    notes: '',
    additionalCharges: '',
    invoiceDiscount: '',
    lines: [newLine()],
  };
}

export function formFromSchedule(schedule: RecurringSchedule): ScheduleForm {
  return {
    customerId: schedule.customer,
    cadence: schedule.cadence,
    nextRunAt: toLocalInput(schedule.nextRunAt),
    stopStage: schedule.stopStage,
    autoComplete: schedule.autoComplete,
    endDate: schedule.endDate ?? '',
    maxRuns: schedule.maxOccurrences == null ? '' : String(schedule.maxOccurrences),
    notes: schedule.notes ?? '',
    additionalCharges: Number(schedule.additionalCharges) ? String(schedule.additionalCharges) : '',
    invoiceDiscount: Number(schedule.invoiceDiscount) ? String(schedule.invoiceDiscount) : '',
    lines: linesFromSchedule(schedule),
  };
}

export function formIsValid(form: ScheduleForm): boolean {
  return (
    Boolean(form.customerId) &&
    Boolean(form.nextRunAt) &&
    form.lines.some(isValidLine) &&
    !form.lines.some((l) => l.price !== '' && Number(l.price) < 0) &&
    (form.maxRuns === '' || Number(form.maxRuns) >= 1) &&
    Number(form.additionalCharges || 0) >= 0 &&
    Number(form.invoiceDiscount || 0) >= 0
  );
}

/**
 * Body for create, or for a PATCH of `original`. The next-run time is sent only when the user
 * changed it: the input has minute precision, and re-sending a truncated value would make the
 * server re-derive the schedule's anchor day from a date that is not really new.
 */
export function buildPayload(
  form: ScheduleForm,
  original: RecurringSchedule | null,
): Record<string, unknown> {
  if (original?.managedByContract) {
    return { autoComplete: form.autoComplete && original.stopStage === 'INVOICE', notes: form.notes };
  }
  const payload: Record<string, unknown> = {
    customer: form.customerId,
    cadence: form.cadence,
    stopStage: form.stopStage,
    autoComplete: form.stopStage === 'INVOICE' ? form.autoComplete : false,
    lineTemplate: { items: templateItems(form.lines) },
    notes: form.notes,
    additionalCharges: form.additionalCharges === '' ? 0 : Number(form.additionalCharges),
    invoiceDiscount: form.invoiceDiscount === '' ? 0 : Number(form.invoiceDiscount),
    endDate: form.endDate === '' ? null : form.endDate,
    maxOccurrences: form.maxRuns === '' ? null : Number(form.maxRuns),
  };
  if (!original || form.nextRunAt !== toLocalInput(original.nextRunAt)) {
    payload.nextRunAt = fromLocalInput(form.nextRunAt);
  }
  if (!original) payload.isActive = true;
  return payload;
}

export type RunOutcome = {
  severity: 'success' | 'info' | 'warning';
  text: string;
  /** Route to open the generated document, when it has a page of its own. */
  to: string | null;
};

export function runOutcome(result: RecurringRunNowResult): RunOutcome {
  const number = result.documentNumber || t('recurring.noNumber');
  let to: string | null = null;
  let text: string;
  if (result.invoiceId) {
    to = `/sales/history/${result.invoiceId}`;
    text =
      result.status === 'COMPLETED'
        ? t('recurring.runDoneCompleted', { number })
        : t('recurring.runDoneDraft', { number });
  } else if (result.deliveryChallanId) {
    to = `/sales/delivery-challans/${result.deliveryChallanId}`;
    text = t('recurring.runDoneChallan');
  } else {
    to = `/sales/orders/${result.salesOrderId}`;
    text = t('recurring.runDoneOrder');
  }
  if (result.alreadyExisted) {
    return { severity: 'info', text: t('recurring.runAlreadyExisted', { number }), to };
  }
  if (result.completionError) {
    return {
      severity: 'warning',
      text: `${text} ${t('recurring.runNotCompleted', { message: result.completionError })}`,
      to,
    };
  }
  return { severity: 'success', text, to };
}

export function runDocumentRoute(run: RecurringRun): string | null {
  if (!run.documentId) return null;
  if (run.documentType === 'invoice') return `/sales/history/${run.documentId}`;
  if (run.documentType === 'delivery_challan') return `/sales/delivery-challans/${run.documentId}`;
  if (run.documentType === 'sales_order') return `/sales/orders/${run.documentId}`;
  return null;
}

export function statusText(status: string): string {
  const key = `status.${status}`;
  const text = t(key);
  return text === key ? status : text;
}

/** True when the instant is still ahead of now. */
export function isInFuture(iso: string): boolean {
  return new Date(iso).getTime() > Date.now();
}
