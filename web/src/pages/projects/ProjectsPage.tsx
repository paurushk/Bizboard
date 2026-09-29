import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { addMilestone, closeProject, createProject, invoiceMilestone, listProjects, markMilestoneReady } from '@/api/roadmap';
import { isProjectsEnabled } from '@/config/features';
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

type MilestoneDraft = { name: string; amount: string; service: Product | null };

const emptyDraft = (): MilestoneDraft => ({ name: '', amount: '', service: null });

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
        name: draft.name, amount: draft.amount, serviceProduct: draft.service!.id,
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
      if (match?.salesInvoice) navigate(`/sales/invoices/${match.salesInvoice}`);
      else void qc.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const close = useMutation({
    mutationFn: (projectId: number) => closeProject(projectId),
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
        <TextField size="small" label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Button variant="contained" disabled={!customer || !name.trim() || create.isPending} onClick={() => create.mutate()}>{t('growth.create')}</Button>
      </Stack>
      {rowsOf(list.data).map((project) => {
        const projectKey = String(project.id);
        const draft = drafts[projectKey] ?? emptyDraft();
        return (
          <Stack key={projectKey} spacing={0.5}>
            <Typography>{String(project.number)} · {String(project.name)} · {String(project.status)}</Typography>
            {project.status === 'OPEN' ? (
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                <TextField size="small" label="Milestone" value={draft.name} onChange={(e) => patchDraft(projectKey, { name: e.target.value })} />
                <TextField size="small" label="Amount" value={draft.amount} onChange={(e) => patchDraft(projectKey, { amount: e.target.value })} />
                <ProductField value={draft.service} onChange={(service) => patchDraft(projectKey, { service })} label="Service" />
                <Button
                  size="small"
                  disabled={!draft.name.trim() || !draft.amount.trim() || !draft.service || add.isPending}
                  onClick={() => add.mutate(Number(project.id))}
                >
                  Add milestone
                </Button>
                <Button size="small" disabled={close.isPending} onClick={() => close.mutate(Number(project.id))}>Close</Button>
              </Stack>
            ) : null}
            {((project.milestones as Record<string, unknown>[] | undefined) ?? []).map((milestone) => (
              <Stack key={String(milestone.id)} direction="row" spacing={1}>
                <Typography variant="body2">{String(milestone.name)} · {String(milestone.status)}</Typography>
                {milestone.status === 'PLANNED' ? (
                  <Button size="small" disabled={ready.isPending} onClick={() => ready.mutate({ projectId: Number(project.id), milestoneId: Number(milestone.id) })}>Ready</Button>
                ) : null}
                {milestone.status === 'READY' ? (
                  <Button
                    size="small"
                    disabled={invoice.isPending}
                    onClick={() => invoice.mutate({ projectId: Number(project.id), milestoneId: Number(milestone.id) })}
                  >
                    {milestone.salesInvoice ? 'Open invoice' : 'Invoice'}
                  </Button>
                ) : null}
                {milestone.status === 'INVOICED' && milestone.salesInvoice ? (
                  <Button size="small" onClick={() => navigate(`/sales/invoices/${String(milestone.salesInvoice)}`)}>View invoice</Button>
                ) : null}
              </Stack>
            ))}
          </Stack>
        );
      })}
    </Stack>
  );
}
