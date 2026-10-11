import { useCallback, useEffect, useRef, useState } from 'react';
import { createReceipt } from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import {
  flushReceiptOutbox,
  listQueuedReceipts,
  removeQueuedReceipt,
  retryQueuedReceipt,
  type QueuedReceipt,
} from '@/offline/receiptOutbox';

/**
 * The receipts waiting on this device, kept in step with the connection: they are sent when the
 * page opens online and whenever the browser reports it is back online. A refused one stays listed
 * (needs attention) until a person retries or discards it.
 */
export function useReceiptOutbox(
  who: { companyId: number; userId: number } | null,
  onSent: (count: number) => void,
) {
  const [items, setItems] = useState<QueuedReceipt[]>([]);
  const [flushing, setFlushing] = useState(false);
  const busy = useRef(false);
  const onSentRef = useRef(onSent);
  useEffect(() => {
    onSentRef.current = onSent;
  });
  const companyId = who?.companyId;
  const userId = who?.userId;

  const flush = useCallback(async () => {
    if (companyId == null || userId == null || busy.current) return;
    busy.current = true;
    setFlushing(true);
    try {
      const result = await flushReceiptOutbox(
        companyId,
        userId,
        (payload, key) => createReceipt(payload, { idempotencyKey: key }),
        getErrorMessage,
      );
      if (result.sent > 0) onSentRef.current(result.sent);
    } finally {
      busy.current = false;
      setFlushing(false);
      setItems(await listQueuedReceipts(companyId, userId));
    }
  }, [companyId, userId]);

  useEffect(() => {
    if (companyId == null || userId == null) return undefined;
    let cancelled = false;
    void listQueuedReceipts(companyId, userId).then((rows) => {
      if (cancelled) return;
      setItems(rows);
      if (rows.length > 0 && (typeof navigator === 'undefined' || navigator.onLine !== false)) void flush();
    });
    const online = () => void flush();
    window.addEventListener('online', online);
    return () => {
      cancelled = true;
      window.removeEventListener('online', online);
    };
  }, [companyId, userId, flush]);

  const refresh = useCallback(async () => {
    if (companyId == null || userId == null) return;
    setItems(await listQueuedReceipts(companyId, userId));
  }, [companyId, userId]);

  return {
    items,
    flushing,
    flush,
    refresh,
    retry: async (id: string) => {
      await retryQueuedReceipt(id);
      await flush();
    },
    discard: async (id: string) => {
      if (companyId == null || userId == null) return;
      await removeQueuedReceipt(id);
      setItems(await listQueuedReceipts(companyId, userId));
    },
  };
}
