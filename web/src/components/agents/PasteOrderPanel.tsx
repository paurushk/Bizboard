import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Collapse from '@mui/material/Collapse';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getProposal, startAgentTextRun, type AgentProposal } from '@/api/agents';
import { t } from '@/i18n';
import { AgentDraftDrawer } from './AgentDraftDrawer';
import { agentErrorText } from './errors';
import { useAgentCatalog } from './useAgents';

const AGENT = 'ORDER_INTAKE';
const OPERATIONAL = new Set(['AGT_E_DAILY_CAP', 'AGT_E_DISABLED', 'AGT_E_GLOBAL_KILL', 'AGT_E_ROLE', 'AGT_E_PROVIDER', 'AGT_E_TIMEOUT']);

/** The run ended without a draft. Carries the run's error code so the person sees the real reason. */
class RunEnded extends Error {
  constructor(readonly code: string) {
    super(code || 'NO_DRAFT');
  }
}
const MAX_CHARS = 6000;

/**
 * Paste a customer's message (WhatsApp, SMS, a note) and get a draft sales order to check. The agent only
 * reads and matches; nothing is created until the person approves the draft, and what is created is a draft
 * order priced by the usual rules. Renders nothing unless the agent is switched on and the user may use it.
 */
export function PasteOrderPanel() {
  const catalog = useAgentCatalog();
  const agent = catalog.data?.agents.find((a) => a.kind === AGENT && a.canPrepare);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<AgentProposal | null>(null);
  const [created, setCreated] = useState<{ id: number; number: string } | null>(null);

  const read = useMutation({
    mutationFn: async () => {
      const run = await startAgentTextRun(AGENT, text.trim());
      const id = run.proposalIds?.[0];
      if (run.status !== 'SUCCEEDED' || id == null) throw new RunEnded(run.errorCode);
      return getProposal(id);
    },
    onSuccess: (p) => {
      setError(null);
      setCreated(null);
      setDraft(p);
    },
    onError: (e) => {
      if (e instanceof RunEnded) {
        // An operational reason (limit, switched off, provider trouble) is shown as is. A validation failure here
        // only ever means the text had no order lines in it.
        const key = `agents.errors.${e.code}`;
        const operational = OPERATIONAL.has(e.code) && t(key) !== key;
        setError(operational ? t(key) : t('agents.order.nothingRead'));
      } else {
        setError(agentErrorText(e));
      }
    },
  });

  if (!agent) return null;

  async function settled(outcome: 'approved' | 'rejected' | 'cancelled' | 'edited') {
    try {
      if (outcome === 'edited') {
        // Re-open the saved revision so the next approve sends the right revision number.
        if (draft) setDraft(await getProposal(draft.id));
        return;
      }
      if (outcome === 'approved' && draft) {
        const done = await getProposal(draft.id);
        const ref = done.resultRef as { id?: number; number?: string } | null;
        if (ref?.id) setCreated({ id: ref.id, number: ref.number ?? '' });
        setText('');
      }
      setDraft(null);
      void queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
    } catch (e) {
      // The approval itself succeeded; only reloading the draft failed. Say so rather than leaving a silent failure.
      setDraft(null);
      setError(agentErrorText(e));
    }
  }

  return (
    <Paper sx={{ p: 1.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="subtitle2" component="p">{t('agents.order.panelTitle')}</Typography>
        <Button size="small" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? t('agents.drawer.close') : t('agents.order.open')}
        </Button>
      </Stack>
      <Collapse in={open} unmountOnExit>
        <Stack spacing={1} sx={{ mt: 1 }}>
          <TextField
            multiline
            minRows={4}
            maxRows={12}
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
            label={t('agents.order.pasteLabel')}
            placeholder={t('agents.order.pastePlaceholder')}
            helperText={t('agents.order.limit', { count: MAX_CHARS })}
          />
          <Stack direction="row" spacing={1} alignItems="center">
            <Button variant="contained" onClick={() => read.mutate()} disabled={read.isPending || text.trim().length === 0}>
              {read.isPending ? <CircularProgress size={16} sx={{ mr: 1 }} aria-label={t('agents.order.reading')} /> : null}
              {read.isPending ? t('agents.order.reading') : t('agents.order.read')}
            </Button>
          </Stack>
          {error ? <Alert severity="error" role="alert">{error}</Alert> : null}
          {created ? (
            <Alert severity="success">
              {t('agents.order.created', { number: created.number || `#${created.id}` })}{' '}
              <RouterLink to={`/sales/orders/${created.id}`}>{t('agents.order.openOrder')}</RouterLink>
            </Alert>
          ) : null}
        </Stack>
      </Collapse>
      <AgentDraftDrawer proposal={draft} open={draft != null} onClose={() => setDraft(null)} onSettled={(o) => void settled(o)} />
    </Paper>
  );
}
