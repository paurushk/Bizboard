import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { getAgentRun, RUN_TERMINAL, startAgentRun, type AgentRun } from '@/api/agents';
import { t } from '@/i18n';
import { agentErrorText } from './errors';
import { agentForCode, usePendingProposals, useAgentCatalog } from './useAgents';
import { AgentDraftDrawer } from './AgentDraftDrawer';

/**
 * "Prepare draft" / "Review draft" for one attention row. Renders nothing unless the catalogue has an
 * agent whose trigger codes match this row's code and the user may prepare it. Reads the draft state from
 * the proposals endpoint (a live query), never from the 60-second cached attention feed.
 */
type Props = {
  dedupeKey: string;
  /** The attention-row code, to find the agent that handles it. */
  code?: string;
  /** Name the agent directly (a button on a document page rather than on an attention row). */
  agentKind?: string;
  label?: string;
};

export function AgentPrepareButton({ code, dedupeKey, agentKind, label }: Props) {
  const catalog = useAgentCatalog();
  const agent = agentKind
    ? catalog.data?.agents.find((a) => a.kind === agentKind && a.canPrepare)
    : agentForCode(catalog.data?.agents, code ?? '');
  // One shared request for the whole page (react-query dedupes it); rows pick their own draft by key.
  const proposals = usePendingProposals();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [which, setWhich] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = useMutation({
    mutationFn: () => startAgentRun(agent!.kind, dedupeKey),
    onSuccess: (r) => {
      setError(null);
      setRun(r);
    },
    onError: (e) => setError(agentErrorText(e)),
  });

  const runEnded = run != null && RUN_TERMINAL.includes(run.status);
  const runFailed = runEnded && run.status !== 'SUCCEEDED';

  // When a run ends, refresh the drafts so the new one shows up.
  useEffect(() => {
    if (runEnded) void queryClient.invalidateQueries({ queryKey: ['agents'] });
  }, [runEnded, queryClient]);

  // Poll while the run is queued or running, with a gentle backoff.
  useEffect(() => {
    if (!run || runEnded) return undefined;
    timer.current = setTimeout(async () => {
      try {
        setRun(await getAgentRun(run.id));
      } catch (e) {
        setError(agentErrorText(e));
        setRun(null);
      }
    }, 1000);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [run, runEnded]);

  if (!agent) return null;
  // A row can have one draft (matched by its key) or several linked ones (matched by their group, e.g. a
  // transfer plus the purchase that covers the rest).
  const drafts = (proposals.data ?? []).filter(
    (p) => (p.dedupeKey === dedupeKey || p.groupKey === dedupeKey) && (p.status === 'PENDING' || p.status === 'FAILED'),
  );
  const draft = drafts[Math.min(which, Math.max(drafts.length - 1, 0))] ?? null;
  const running = start.isPending || (run != null && !RUN_TERMINAL.includes(run.status));

  if (draft) {
    return (
      <>
        <Button size="small" variant="outlined" onClick={() => setDrawer(true)}>
          {t('agents.reviewDraft')}
        </Button>
        <AgentDraftDrawer
          proposal={draft}
          open={drawer}
          onClose={() => setDrawer(false)}
          hasNext={which < drafts.length - 1}
          hasPrevious={which > 0}
          onNext={() => setWhich((w) => w + 1)}
          onPrevious={() => setWhich((w) => Math.max(w - 1, 0))}
          onSettled={() => setDrawer(drafts.length > 1)}
        />
      </>
    );
  }

  return (
    <>
      <Button size="small" variant="outlined" disabled={running} onClick={() => start.mutate()}>
        {running ? <CircularProgress size={14} sx={{ mr: 1 }} aria-label={t('agents.preparing')} /> : null}
        {running ? t('agents.preparing') : (label ?? t('agents.prepare'))}
      </Button>
      <span role="status" aria-live="polite" style={{ position: 'absolute', left: -9999 }}>{error ?? (runFailed ? t('agents.runFailed') : null)}</span>
      {runEnded && !runFailed && !error ? <span role="status">{t('agents.noFindings')}</span> : null}
    </>
  );
}
