import { describe, expect, it } from 'vitest';
import { en } from '@/i18n/en';
import { hi } from '@/i18n/hi';

/**
 * Every status value the backend can emit for the order-to-delivery documents must have a label in
 * both languages. A missing key renders as the raw dot path ("status.CONFIRMED"), which is how H-07
 * reached users. Add a value here when a backend enum gains one.
 */
const BACKEND_STATUSES: Record<string, string[]> = {
  Quotation: ['DRAFT', 'SENT', 'ACCEPTED', 'REJECTED', 'CONVERTED', 'CANCELLED', 'EXPIRED'],
  SalesOrder: ['DRAFT', 'CONFIRMED', 'PARTIALLY_CONVERTED', 'CONVERTED', 'CANCELLED'],
  SalesOrderDisplay: ['SHIPPED'],
  DeliveryChallan: ['DRAFT', 'COMPLETED', 'CANCELLED'],
  DeliveryChallanReturn: ['DRAFT', 'COMPLETED', 'CANCELLED'],
  DeliveryRoute: ['PLANNED', 'IN_TRANSIT', 'COMPLETED', 'CANCELLED'],
  DeliveryRouteStop: ['PENDING', 'DELIVERED', 'FAILED', 'REJECTED', 'RETURNED'],
  OrderListFilter: ['OPEN', 'CLOSED'],
};

function lookup(catalog: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog);
}

describe('status labels exist in English and Hindi for every order-to-delivery status', () => {
  for (const [model, statuses] of Object.entries(BACKEND_STATUSES)) {
    for (const status of statuses) {
      it(`${model}.${status}`, () => {
        expect(typeof lookup(en, `status.${status}`)).toBe('string');
        expect(typeof lookup(hi, `status.${status}`)).toBe('string');
      });
    }
  }
});
