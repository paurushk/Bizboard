import type { AgentRenderer } from '@/api/agents';

export type RendererProps = {
  /** The payload being shown. Edits are reported through onChange; the drawer saves them. */
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  disabled: boolean;
};

export function isKnownRenderer(renderer: AgentRenderer): boolean {
  return renderer === 'message' || renderer === 'lines' || renderer === 'comparison' || renderer === 'order';
}
