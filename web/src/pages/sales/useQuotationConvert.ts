import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  convertQuotation,
  convertQuotationToOrder,
  listSalesInvoicesPage,
} from '@/api/resources';
import { t } from '@/i18n';
import type { Quotation } from '@/types/domain';
import { createIdempotencyKeyFor } from '@/utils/idempotencyKeyFor';
import { quotationHasRemainingAfterConvert, type ConvertLinePayload } from '@/utils/quotationConvert';

export type ConvertTarget = { quotation: Quotation; mode: 'invoice' | 'order' };

/** Quotation to order or invoice: the dialog's target, the two mutations and what follows them.
 * One copy serves the list and the editor, so they cannot drift apart. */
export function useQuotationConvert(opts: { onDone: (message: string) => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [target, setTarget] = useState<ConvertTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // An identical retry reuses its key; a finished request must not lend it to the next one.
  const key = useRef(createIdempotencyKeyFor());

  const finish = () => {
    key.current = createIdempotencyKeyFor();
    setBusyId(null);
    setTarget(null);
    void qc.invalidateQueries({ queryKey: ['quotations'] });
    void qc.invalidateQueries({ queryKey: ['quotation'] });
  };

  const toInvoice = useMutation({
    mutationFn: ({ id, items, confirmExpired }: { id: number; items: ConvertLinePayload[]; confirmExpired?: boolean }) =>
      convertQuotation(id, { items, confirmExpired, idempotencyKey: key.current({ id, items, mode: 'invoice' }) }),
    onSuccess: async (invoice, vars) => {
      const remaining = quotationHasRemainingAfterConvert(target?.quotation.items ?? [], vars.items);
      finish();
      if (remaining) {
        opts.onDone(t('common.convertedPartialInvoice', { id: invoice.id }));
        return;
      }
      const flash = t('phase1.convertedToInvoice', { id: invoice.id });
      try {
        await qc.fetchQuery({ queryKey: ['sales-invoices'], queryFn: () => listSalesInvoicesPage(), staleTime: 0 });
      } catch {
        void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      }
      void navigate('/sales/history', { state: { message: flash } });
    },
    onError: (err) => {
      setBusyId(null);
      setError(getErrorMessage(err));
    },
  });

  const toOrder = useMutation({
    mutationFn: ({ id, items, confirmExpired }: { id: number; items: ConvertLinePayload[]; confirmExpired?: boolean }) =>
      convertQuotationToOrder(id, { items, confirmExpired, idempotencyKey: key.current({ id, items, mode: 'order' }) }),
    onSuccess: (order, vars) => {
      const remaining = quotationHasRemainingAfterConvert(target?.quotation.items ?? [], vars.items);
      finish();
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      if (remaining) {
        opts.onDone(t('common.convertedPartialOrder', { id: order.id }));
        return;
      }
      void navigate('/sales/orders', { state: { message: t('phase1.convertedToOrder', { id: order.id }) } });
    },
    onError: (err) => {
      setBusyId(null);
      setError(getErrorMessage(err));
    },
  });

  return {
    target,
    error,
    pending: toInvoice.isPending || toOrder.isPending,
    busyId,
    open: (quotation: Quotation, mode: 'invoice' | 'order') => {
      setError(null);
      setBusyId(quotation.id);
      setTarget({ quotation, mode });
    },
    close: () => {
      setTarget(null);
      setBusyId(null);
      setError(null);
    },
    confirm: (items: ConvertLinePayload[], confirmExpired?: boolean) => {
      if (!target) return;
      const vars = { id: target.quotation.id, items, confirmExpired };
      if (target.mode === 'order') toOrder.mutate(vars);
      else toInvoice.mutate(vars);
    },
  };
}
