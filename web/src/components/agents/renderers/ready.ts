import type { AgentRenderer } from '@/api/agents';

type RawLine = Record<string, unknown>;

/** An order draft can be approved only when the customer and every line are filled in. */
export function isOrderReady(value: Record<string, unknown>): boolean {
  const lines = Array.isArray(value.lines) ? (value.lines as RawLine[]) : [];
  return (
    typeof value.customerId === 'number' &&
    lines.length > 0 &&
    lines.every((l) => typeof l.productId === 'number' && l.qty != null && String(l.qty).trim() !== '' && Number(l.qty) > 0)
  );
}

/** Can this payload be approved as it stands? Most kinds always can. */
export function isPayloadReady(renderer: AgentRenderer, value: Record<string, unknown>): boolean {
  return renderer === 'order' ? isOrderReady(value) : true;
}
