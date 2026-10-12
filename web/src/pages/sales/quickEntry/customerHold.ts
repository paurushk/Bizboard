import type { Customer } from '@/types/domain';
import { isCollectionHoldStatus } from '@/utils/collectionHold';

/** The customer record carries a collection status when the collections module is on. */
export function collectionHoldFor(customer: Customer | null | undefined): boolean {
  return isCollectionHoldStatus(customer?.collectionStatus);
}
