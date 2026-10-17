/**
 * Which actions a sales order offers, by status (hardening plan T-2.1, H-05/H-06).
 *
 * The list and the editor both read this, so they cannot disagree again. The server stays the
 * authority (it refuses anything the order cannot do); this only decides what to *offer*, so no
 * status leaves a user on a screen with no way forward.
 *
 * | Status               | Confirm | Create invoice / challan | Cancel |
 * | DRAFT, order checks off | yes   | yes                      | yes    |
 * | DRAFT, order checks on  | yes   | no (confirm first)       | yes    |
 * | CONFIRMED            | no      | yes                      | yes    |
 * | PARTIALLY_CONVERTED  | no      | yes (the remainder)      | no     |
 * | CONVERTED, CANCELLED | no      | no                       | no     |
 */
export interface OrderActions {
  confirm: boolean;
  createInvoice: boolean;
  createChallan: boolean;
  cancel: boolean;
}

export interface OrderActionContext {
  /** ENABLE_ORDER_GATES: an order must be confirmed before it can be invoiced or shipped. */
  gatesOn: boolean;
  canWrite: boolean;
  canCancel: boolean;
}

export const NO_ORDER_ACTIONS: OrderActions = {
  confirm: false,
  createInvoice: false,
  createChallan: false,
  cancel: false,
};

export function orderActions(status: string | null | undefined, ctx: OrderActionContext): OrderActions {
  const s = String(status ?? '').toUpperCase();
  switch (s) {
    case 'DRAFT':
      return {
        confirm: ctx.canWrite,
        createInvoice: ctx.canWrite && !ctx.gatesOn,
        createChallan: ctx.canWrite && !ctx.gatesOn,
        cancel: ctx.canCancel,
      };
    case 'CONFIRMED':
      return {
        confirm: false,
        createInvoice: ctx.canWrite,
        createChallan: ctx.canWrite,
        cancel: ctx.canCancel,
      };
    case 'PARTIALLY_CONVERTED':
      return {
        confirm: false,
        createInvoice: ctx.canWrite,
        createChallan: ctx.canWrite,
        cancel: false,
      };
    default:
      return NO_ORDER_ACTIONS;
  }
}

/** Statuses that count as "open" in the list filter: the order still has something left to do. */
export const OPEN_ORDER_STATUSES = 'DRAFT,CONFIRMED,PARTIALLY_CONVERTED';
/** Statuses that count as "closed": nothing is left to do. */
export const CLOSED_ORDER_STATUSES = 'CONVERTED,CANCELLED';

export function orderStatusParam(filterStatus: string | undefined): string | undefined {
  if (filterStatus === 'OPEN') return OPEN_ORDER_STATUSES;
  if (filterStatus === 'CLOSED') return CLOSED_ORDER_STATUSES;
  return filterStatus || undefined;
}

/**
 * Orders the challan editor offers in its "link a sales order" picker. A confirmed or partly
 * processed order can ship; a draft only when order checks are off (otherwise it must be
 * confirmed first, and the server would refuse the challan).
 */
export function isOrderPickableForChallan(status: string | null | undefined, gatesOn: boolean): boolean {
  const s = String(status ?? '').toUpperCase();
  return s === 'CONFIRMED' || s === 'PARTIALLY_CONVERTED' || (s === 'DRAFT' && !gatesOn);
}
