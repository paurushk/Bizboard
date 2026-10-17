/**
 * What a user may do to a serial number from the Serial numbers page.
 *
 * This mirrors `SerialNumberViewSet.transition` on the server. A unit only becomes SOLD through an
 * invoice or challan, so there is no "mark sold" here. A SOLD unit comes back through a sales
 * return (INV-IDR-03): the page links to it, and only an owner can put the unit back in stock
 * without one (a separate, reasoned action on the page). A scrapped unit is final.
 */
export type SerialStatus = 'AVAILABLE' | 'SOLD' | 'RETURNED' | 'SCRAPPED';

export interface SerialAction {
  /** Status sent to the API. */
  target: 'SCRAPPED';
  labelKey: 'inventory.serialScrap';
  confirmKey: 'inventory.serialConfirmScrap';
  tone: 'error';
}

const SCRAP: SerialAction = {
  target: 'SCRAPPED',
  labelKey: 'inventory.serialScrap',
  confirmKey: 'inventory.serialConfirmScrap',
  tone: 'error',
};
export function serialActionsFor(status: string): SerialAction[] {
  switch (status) {
    case 'AVAILABLE':
      return [SCRAP];
    case 'RETURNED':
      return [SCRAP];
    default:
      return [];
  }
}
