import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { addMilestone, closeProject, createProject, deleteMilestone, invoiceMilestone, listProjects, markMilestoneReady, updateMilestone } from '@/api/roadmap';
import { isProjectsEnabled } from '@/config/features';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { CustomerField, ProductField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

function rowsOf(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const results = (data as { results?: Record<string, unknown>[] } | null)?.results;
  return results ?? [];
}

type MilestoneDraft = { name: string; amount: string; service: Product | null; targetDate: string };

const emptyDraft = (): MilestoneDraft => ({ name: '', amount: '', service: null, targetDate: '' });

export function ProjectsPage() {
  if (!isProjectsEnabled()) {
    return <PageShell title={t('nav.projects')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <ProjectsInner />;
}

function ProjectsInner() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [name, setName] = useState('');
  const [drafts, setDrafts] = useState<Record<string, MilestoneDraft>>({});
  const [editing, setEditing] = useState<{ projectId: number; milestoneId: number } | null>(null);
  const [editName, setEditName] = useState('');
  const [editAmount, setEditAmount] = useState('');
  const [editDate, setEditDate] = useState('');
  const [pendingClose, setPendingClose] = useState<number | null>(null);
  const [error, setError] = useState('');
  const list = useQuery({ queryKey: ['projects'], queryFn: listProjects });
  const patchDraft = (projectId: string, patch: Partial<MilestoneDraft>) => {
    setDrafts((current) => {
      const prev = current[projectId] ?? emptyDraft();
      return { ...current, [projectId]: { ...prev, ...patch } };
    });
  };
  const create = useMutation({
    mutationFn: () => createProject({ customer: customer!.id, name }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });
  const add = useMutation({
    mutationFn: (projectId: number) => {
      const draft = drafts[String(projectId)] ?? emptyDraft();
      return addMilestone(projectId, {
        name: draft.name,
        amount: draft.amount,
        serviceProduct: draft.service!.id,
        targetCompletionDate: draft.targetDate || undefined,
      });
    },
    onSuccess: (_row, projectId) => {
      setDrafts((current) => ({ ...current, [String(projectId)]: emptyDraft() }));
      void qc.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const ready = useMutation({
    mutationFn: (args: { projectId: number; milestoneId: number }) => markMilestoneReady(args.projectId, args.milestoneId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });
  const invoice = useMutation({
    mutationFn: (args: { projectId: number; milestoneId: number }) => invoiceMilestone(args.projectId, args.milestoneId),
    onSuccess: (row, args) => {
      const milestones = (row.milestones as { id?: number; salesInvoice?: number }[] | undefined) ?? [];
      const match = milestones.find((item) => Number(item.id) === args.milestoneId);
      if (match?.salesInvoice) navigate(`/sales/history/${match.salesInvoice}`);
      else void qc.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const close = useMutation({
    mutationFn: (projectId: number) => closeProject(projectId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });
  const saveMilestone = useMutation({
    mutationFn: () => updateMilestone(editing!.projectId, editing!.milestoneId, {
      name: editName,
      amount: editAmount,
      target_completion_date: editDate || null,
    }),
    onSuccess: () => {
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const removeMilestone = useMutation({
    mutationFn: (args: { projectId: number; milestoneId: number }) => deleteMilestone(args.projectId, args.milestoneId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.projects')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.projectMilestone')}</Typography>
      {error ? <Typography color="error" role="alert">{error}</Typography> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField size="small" label={t('growth.name')} value={name} onChange={(e) => setName(e.target.value)} />
        <Button variant="contained" disabled={!customer || !name.trim() || create.isPending} onClick={() => create.mutate()}>{t('growth.startProject')}</Button>
      </Stack>
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rowsOf(list.data).length === 0 ? (
        <EmptyState description={t('cog.emptyProjects')} />
      ) : null}
      {rowsOf(list.data).map((project) => {
        const projectKey = String(project.id);
        const draft = drafts[projectKey] ?? emptyDraft();
        return (
          <Stack key={projectKey} spacing={0.5}>
            <Typography>{String(project.number)} · {String(project.name)} · {String(project.status)}</Typography>
            {project.status === 'OPEN' ? (
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                <TextField size="small" label={t('growth.milestone')} value={draft.name} onChange={(e) => patchDraft(projectKey, { name: e.target.value })} />
                <TextField size="small" label={t('growth.amount')} value={draft.amount} onChange={(e) => patchDraft(projectKey, { amount: e.target.value })} />
                <TextField size="small" type="date" label={t('growth.targetDate')} value={draft.targetDate} onChange={(e) => patchDraft(projectKey, { targetDate: e.target.value })} InputLabelProps={{ shrink: true }} />
                <ProductField value={draft.service} onChange={(service) => patchDraft(projectKey, { service })} label={t('growth.service')} />
                <Button
                  size="small"
                  disabled={!draft.name.trim() || !draft.amount.trim() || !draft.service || add.isPending}
                  onClick={() => add.mutate(Number(project.id))}
                >
                  {t('growth.addMilestone')}
                </Button>
                <Button size="small" disabled={close.isPending} onClick={() => setPendingClose(Number(project.id))}>{t('growth.closeProject')}</Button>
              </Stack>
            ) : null}
            {((project.milestones as Record<string, unknown>[] | undefined) ?? []).map((milestone) => {
              const due = String(milestone.targetCompletionDate ?? milestone.target_completion_date ?? '');
              const isEditing = editing?.projectId === Number(project.id) && editing.milestoneId === Number(milestone.id);
              return (
              <Stack key={String(milestone.id)} spacing={0.5}>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Typography variant="body2">
                  {String(milestone.name)} · {String(milestone.amount ?? '')} · {due || '—'} · {String(milestone.status)}
                </Typography>
                {milestone.status === 'PLANNED' && !milestone.salesInvoice ? (
                  <>
                    <Button size="small" disabled={ready.isPending} onClick={() => ready.mutate({ projectId: Number(project.id), milestoneId: Number(milestone.id) })}>{t('growth.ready')}</Button>
                    <Button size="small" onClick={() => {
                      setEditing({ projectId: Number(project.id), milestoneId: Number(milestone.id) });
                      setEditName(String(milestone.name ?? ''));
                      setEditAmount(String(milestone.amount ?? ''));
                      setEditDate(due);
                    }}>{t('growth.editMilestone')}</Button>
                    <Button size="small" disabled={removeMilestone.isPending} onClick={() => { if (window.confirm(`${t('growth.deleteMilestone')}?`)) removeMilestone.mutate({ projectId: Number(project.id), milestoneId: Number(milestone.id) }); }}>{t('growth.deleteMilestone')}</Button>
                  </>
                ) : null}
                {milestone.status === 'READY' ? (
                  <Button
                    size="small"
                    disabled={invoice.isPending}
                    onClick={() => invoice.mutate({ projectId: Number(project.id), milestoneId: Number(milestone.id) })}
                  >
                    {milestone.salesInvoice ? t('growth.openInvoice') : t('growth.invoice')}
                  </Button>
                ) : null}
                {milestone.status === 'INVOICED' && milestone.salesInvoice ? (
                  <Button size="small" onClick={() => navigate(`/sales/history/${String(milestone.salesInvoice)}`)}>{t('growth.viewInvoice')}</Button>
                ) : null}
                </Stack>
                {isEditing ? (
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                    <TextField size="small" label={t('growth.milestone')} value={editName} onChange={(e) => setEditName(e.target.value)} />
                    <TextField size="small" label={t('growth.amount')} value={editAmount} onChange={(e) => setEditAmount(e.target.value)} />
                    <TextField size="small" type="date" label={t('growth.targetDate')} value={editDate} onChange={(e) => setEditDate(e.target.value)} InputLabelProps={{ shrink: true }} />
                    <Button size="small" variant="contained" disabled={!editName.trim() || !editAmount.trim() || saveMilestone.isPending} onClick={() => saveMilestone.mutate()}>{t('growth.save')}</Button>
                  </Stack>
                ) : null}
              </Stack>
              );
            })}
          </Stack>
        );
      })}
      <ConfirmDialog
        open={pendingClose != null}
        title={t('growth.closeProject')}
        body={t('growth.closeProjectConfirm')}
        confirmLabel={t('common.confirm')}
        confirming={close.isPending}
        onClose={() => setPendingClose(null)}
        onConfirm={() => {
          if (pendingClose != null) close.mutate(pendingClose);
          setPendingClose(null);
        }}
      />
    </Stack>
  );
}
