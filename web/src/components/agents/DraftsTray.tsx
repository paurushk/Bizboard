import Alert from '@mui/material/Alert';
import Badge from '@mui/material/Badge';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Typography from '@mui/material/Typography';
import EditNoteIcon from '@mui/icons-material/EditNote';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { bulkApproveProposals, type AgentProposal } from '@/api/agents';
import { t } from '@/i18n';
import { agentErrorText } from './errors';
import { AgentDraftDrawer } from './AgentDraftDrawer';
import { ProposalStatusBadge } from './ProposalStatusBadge';
import { isOpenProposal, usePendingProposals, useAgentsEnabled } from './useAgents';

/** Header icon with a count of drafts waiting, opening a list with bulk approve for bulk-approvable kinds. */
export function DraftsTray() {
  const enabled = useAgentsEnabled();
  const queryClient = useQueryClient();
  const query = usePendingProposals();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [activeId, setActiveId] = useState<number | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Drafts that share a group (a transfer and the purchase that covers the rest) sit together, marked as linked.
  const rows = useMemo(() => {
    const open = (query.data ?? []).filter(isOpenProposal);
    const firstAt = new Map<string, number>();
    open.forEach((r, i) => {
      if (r.groupKey && !firstAt.has(r.groupKey)) firstAt.set(r.groupKey, i);
    });
    return open
      .map((r, i) => ({ r, order: r.groupKey ? (firstAt.get(r.groupKey) ?? i) : i, i }))
      .sort((a, b) => a.order - b.order || a.i - b.i)
      .map((x) => x.r);
  }, [query.data]);
  const linked = (r: AgentProposal) => Boolean(r.groupKey) && rows.filter((x) => x.groupKey === r.groupKey).length > 1;
  const bulkable = rows.filter((r) => r.bulkApprovable && r.canApprove && r.status === 'PENDING');
  const activeIndex = rows.findIndex((r) => r.id === activeId);
  const active: AgentProposal | null = activeIndex >= 0 ? rows[activeIndex] : null;

  const bulk = useMutation({
    mutationFn: () => bulkApproveProposals(rows.filter((r) => selected.has(r.id)).map((r) => ({ id: r.id, revision: r.revision }))),
    onSuccess: (results) => {
      const ok = results.filter((r) => r.ok).length;
      setSummary(t('agents.tray.bulkDone', { ok, failed: results.length - ok }));
      setSelected(new Set());
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
    onError: (e) => setError(agentErrorText(e)),
  });

  if (!enabled) return null;

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <>
      <IconButton aria-label={rows.length ? t('agents.tray.count', { count: rows.length }) : t('agents.tray.open')} onClick={() => setOpen(true)}>
        <Badge color="primary" badgeContent={rows.length} invisible={rows.length === 0}>
          <EditNoteIcon aria-hidden />
        </Badge>
      </IconButton>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm" aria-labelledby="agents-tray-title">
        <DialogTitle id="agents-tray-title">{t('agents.tray.title')}</DialogTitle>
        <DialogContent dividers>
          {summary ? <Alert severity="info" sx={{ mb: 1 }}>{summary}</Alert> : null}
          {error ? <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert> : null}
          {rows.length === 0 ? (
            <Typography color="text.secondary">{t('agents.tray.empty')}</Typography>
          ) : (
            <List dense>
              {rows.map((r) => (
                <ListItem
                  key={r.id}
                  disablePadding
                  secondaryAction={<ProposalStatusBadge status={r.status} />}
                >
                  {bulkable.includes(r) ? (
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      <Checkbox
                        edge="start"
                        checked={selected.has(r.id)}
                        onChange={() => toggle(r.id)}
                        inputProps={{ 'aria-label': r.title }}
                      />
                    </ListItemIcon>
                  ) : null}
                  <ListItemButton onClick={() => setActiveId(r.id)}>
                    <ListItemText primary={r.title} secondary={linked(r) ? t('agents.tray.linked') : undefined} />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          {bulkable.length > 0 ? (
            <>
              <Button onClick={() => setSelected(new Set(bulkable.map((r) => r.id)))}>{t('agents.tray.selectAll')}</Button>
              <Button variant="contained" disabled={selected.size === 0 || bulk.isPending} onClick={() => bulk.mutate()}>
                {t('agents.tray.approveSelected')}
              </Button>
            </>
          ) : null}
          <Button onClick={() => setOpen(false)}>{t('agents.drawer.close')}</Button>
        </DialogActions>
      </Dialog>

      <AgentDraftDrawer
        proposal={active}
        open={active != null}
        onClose={() => setActiveId(null)}
        hasNext={activeIndex >= 0 && activeIndex < rows.length - 1}
        hasPrevious={activeIndex > 0}
        onNext={() => setActiveId(rows[activeIndex + 1]?.id ?? null)}
        onPrevious={() => setActiveId(rows[activeIndex - 1]?.id ?? null)}
        onSettled={(outcome) => {
          // Rapid triage: after approve or reject, move to the next waiting draft.
          if (outcome === 'approved' || outcome === 'rejected' || outcome === 'cancelled') {
            setActiveId(rows[activeIndex + 1]?.id ?? null);
          }
        }}
      />
    </>
  );
}
