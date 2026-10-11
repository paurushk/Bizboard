import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  canQueueReceipt,
  flushReceiptOutbox,
  isDeterministicRefusal,
  listQueuedReceipts,
  queueReceipt,
  removeQueuedReceipt,
  retryQueuedReceipt,
} from './receiptOutbox';

const company = 7;
const user = 3;

function entry(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    companyId: company,
    userId: user,
    customerName: 'Ravi',
    payload: { customer: 1, amount: 100, mode: 'CASH', receiptDate: '2026-10-09', ...over },
  } as Parameters<typeof queueReceipt>[0];
}

async function clear() {
  for (const row of await listQueuedReceipts(company, user)) await removeQueuedReceipt(row.id);
}

describe('receipt outbox', () => {
  beforeEach(clear);

  it('queues only cash and cheque', async () => {
    expect(canQueueReceipt('CASH')).toBe(true);
    expect(canQueueReceipt('CHEQUE')).toBe(true);
    expect(canQueueReceipt('UPI')).toBe(false);
    await expect(queueReceipt(entry('k0', { mode: 'UPI' }))).rejects.toThrow(/cannot be saved offline/);
  });

  it('keeps the date the cashier saw and sends under the original key, oldest first', async () => {
    await queueReceipt(entry('k1'));
    await queueReceipt(entry('k2', { amount: 50 }));
    const send = vi.fn().mockResolvedValue({});
    const result = await flushReceiptOutbox(company, user, send);
    expect(result).toEqual({ sent: 2, conflicts: 0, remaining: 0 });
    expect(send.mock.calls.map((call) => call[1])).toEqual(['k1', 'k2']);
    expect(send.mock.calls[0][0].receiptDate).toBe('2026-10-09');
    expect(await listQueuedReceipts(company, user)).toEqual([]);
  });

  it('does not send another user\'s or another company\'s receipts', async () => {
    await queueReceipt(entry('mine'));
    await queueReceipt({ ...entry('theirs'), userId: 99 });
    await queueReceipt({ ...entry('other-co'), companyId: 8 });
    const send = vi.fn().mockResolvedValue({});
    await flushReceiptOutbox(company, user, send);
    expect(send.mock.calls.map((call) => call[1])).toEqual(['mine']);
    for (const id of ['theirs', 'other-co']) await removeQueuedReceipt(id);
  });

  it('moves a refused send to needs-attention and carries on with the rest', async () => {
    await queueReceipt(entry('bad'));
    await queueReceipt(entry('good'));
    const send = vi.fn(async (_payload: unknown, key: string) => {
      if (key === 'bad') throw Object.assign(new Error('closed'), { response: { status: 400 } });
    });
    const result = await flushReceiptOutbox(company, user, send, () => 'GST period is closed');
    expect(result).toEqual({ sent: 1, conflicts: 1, remaining: 0 });
    const left = await listQueuedReceipts(company, user);
    expect(left).toHaveLength(1);
    expect(left[0]).toMatchObject({ id: 'bad', status: 'conflict', error: 'GST period is closed' });
    // A refused row is not retried by the next flush, but can be put back by hand.
    await flushReceiptOutbox(company, user, send);
    expect(send).toHaveBeenCalledTimes(2);
    await retryQueuedReceipt('bad');
    expect((await listQueuedReceipts(company, user))[0].status).toBe('queued');
  });

  it('stops at a lost connection and leaves everything queued', async () => {
    await queueReceipt(entry('a'));
    await queueReceipt(entry('b'));
    const send = vi.fn().mockRejectedValue(new Error('Network Error'));
    const result = await flushReceiptOutbox(company, user, send);
    expect(result).toEqual({ sent: 0, conflicts: 0, remaining: 2 });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('tells a refusal from an outage', () => {
    expect(isDeterministicRefusal({ response: { status: 400 } })).toBe(true);
    expect(isDeterministicRefusal({ response: { status: 409 } })).toBe(true);
    expect(
      isDeterministicRefusal({ response: { status: 409, data: { error: { code: 'idempotency_in_flight' } } } }),
    ).toBe(false);
    expect(isDeterministicRefusal({ response: { status: 429 } })).toBe(false);
    expect(isDeterministicRefusal({ response: { status: 500 } })).toBe(false);
    expect(isDeterministicRefusal(new Error('Network Error'))).toBe(false);
  });
});
