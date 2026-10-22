import { useQuery } from '@tanstack/react-query';
import { getAgentCatalog, listProposals, type AgentInfo, type AgentProposal } from '@/api/agents';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';

/** True when this company has agents switched on. Everything agent-related hides when it is false. */
export function useAgentsEnabled(): boolean {
  useFeatureFlagEpoch();
  return isRuntimeFlagEnabled('ENABLE_AGENTS');
}

/** The catalogue the UI renders from. A new agent appears here with no frontend registration. */
export function useAgentCatalog() {
  const enabled = useAgentsEnabled();
  return useQuery({
    queryKey: ['agents', 'catalog'],
    queryFn: getAgentCatalog,
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** Does a "Prepare draft" action exist for this attention-row code? */
export function agentForCode(agents: AgentInfo[] | undefined, code: string): AgentInfo | undefined {
  if (!agents) return undefined;
  return agents.find(
    (a) =>
      a.canPrepare &&
      a.triggerCodes.some((p) => (p.endsWith('*') ? code.startsWith(p.slice(0, -1)) : p === code)),
  );
}

export function usePendingProposals(options?: { dedupeKey?: string }) {
  const enabled = useAgentsEnabled();
  return useQuery({
    queryKey: ['agents', 'proposals', options?.dedupeKey ?? 'all'],
    queryFn: () => listProposals({ dedupeKey: options?.dedupeKey }),
    enabled,
    staleTime: 15_000,
    retry: false,
  });
}

export function isOpenProposal(p: AgentProposal): boolean {
  return p.status === 'PENDING' || p.status === 'FAILED';
}
