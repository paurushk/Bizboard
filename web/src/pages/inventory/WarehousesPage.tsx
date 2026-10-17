import { useState } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { HelpEmptyLink } from '@/pages/help/HelpEmptyLink';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { PreventionNote } from '@/pages/help/PreventionNote';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';
import { codeFromName } from '@/utils/codeGen';

type Filter = 'active' | 'off' | 'all';

export function WarehousesPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const { ask, dialog } = useConfirmPrompt();
  const query = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const [filter, setFilter] = useState<Filter>('active');
  const [editing, setEditing] = useState<Row | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [codeTouched, setCodeTouched] = useState(false);
  const [error, setError] = useState('');

  const refresh = () => void qc.invalidateQueries({ queryKey: ['warehouses'] });
  const close = () => {
    setOpen(false);
    setEditing(null);
    setError('');
  };
  const openNew = () => {
    setEditing(null);
    setName('');
    setCode('');
    setCodeTouched(false);
    setError('');
    setOpen(true);
  };
  const openEdit = (row: Row) => {
    setEditing(row);
    setName(String(row.name ?? ''));
    setCode(String(row.code ?? ''));
    setCodeTouched(true);
    setError('');
    setOpen(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = { name: name.trim(), code: code.trim() || codeFromName(name) };
      return editing ? api.updateWarehouse(Number(editing.id), payload) : api.createWarehouse(payload);
    },
    onSuccess: () => {
      close();
      refresh();
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const change = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) => api.updateWarehouse(id, patch),
    onSuccess: () => {
      setError('');
      refresh();
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteWarehouse(id),
    onSuccess: () => {
      setError('');
      refresh();
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const all = asRows(query.data);
  const activeRows = all.filter((r) => r.isActive !== false);
  const offRows = all.filter((r) => r.isActive === false);
  const rows = filter === 'active' ? activeRows : filter === 'off' ? offRows : all;
  const busy = change.isPending || remove.isPending;

  const confirmThen = async (message: string, run: () => void) => {
    if (await ask([message])) run();
  };

  return (
    <PageShell
      title={t('phase.godowns')}
      subtitle={t('phase.godownsSubtitle')}
      actions={
        <Button variant="contained" onClick={openNew} disabled={writesBlocked}>
          {t('sweep2.addGodown')}
        </Button>
      }
    >
      {error && !open ? <HelpErrorAlert message={error} onClose={() => setError('')} /> : null}
      <PreventionNote intent="edit-completed-invoice" slot="delete-with-history" />
      <Stack direction="row" spacing={1} role="group" aria-label={t('phase.godowns')}>
        {([
          ['active', 'inventory.godownFilterActive', activeRows.length],
          ['off', 'inventory.godownFilterOff', offRows.length],
          ['all', 'inventory.godownFilterAll', all.length],
        ] as const).map(([key, labelKey, count]) => (
          <Chip
            key={key}
            label={t(labelKey, { count: String(count) })}
            color={filter === key ? 'primary' : 'default'}
            variant={filter === key ? 'filled' : 'outlined'}
            onClick={() => setFilter(key)}
          />
        ))}
      </Stack>
      <DataTable
        rows={rows}
        empty={t('inventory.godownNone')}
        emptyAction={<HelpEmptyLink intent="stock-in-another-godown" />}
        columns={[
          { key: 'name', label: t('sweep.name') },
          { key: 'code', label: t('sweep.code') },
          {
            key: 'isDefault',
            label: t('inventory.godownDefault'),
            render: (row) => (row.isDefault ? <Chip size="small" color="primary" label={t('inventory.godownDefault')} /> : null),
          },
          {
            key: 'isActive',
            label: t('sweep.status'),
            render: (row) =>
              row.isActive === false ? (
                <Chip size="small" color="warning" label={t('inventory.godownOffChip')} />
              ) : (
                <Chip size="small" variant="outlined" label={t('inventory.godownOnChip')} />
              ),
          },
        ]}
        actions={(row) => {
          const id = Number(row.id);
          const label = String(row.name);
          const isOff = row.isActive === false;
          return (
            <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
              <Button size="small" disabled={writesBlocked} onClick={() => openEdit(row)}>
                {t('inventory.godownEdit')}
              </Button>
              {!isOff && !row.isDefault ? (
                <Button
                  size="small"
                  disabled={writesBlocked || busy}
                  onClick={() =>
                    void confirmThen(t('inventory.godownConfirmDefault', { name: label }), () =>
                      change.mutate({ id, patch: { isDefault: true } }),
                    )
                  }
                >
                  {t('inventory.godownMakeDefault')}
                </Button>
              ) : null}
              {isOff ? (
                <Button
                  size="small"
                  disabled={writesBlocked || busy}
                  onClick={() =>
                    void confirmThen(t('inventory.godownConfirmOn', { name: label }), () =>
                      change.mutate({ id, patch: { isActive: true } }),
                    )
                  }
                >
                  {t('inventory.godownSwitchOn')}
                </Button>
              ) : !row.isDefault ? (
                <Button
                  size="small"
                  disabled={writesBlocked || busy}
                  onClick={() =>
                    void confirmThen(t('phase.confirmDeactivateWarehouse'), () =>
                      change.mutate({ id, patch: { isActive: false } }),
                    )
                  }
                >
                  {t('inventory.godownSwitchOff')}
                </Button>
              ) : null}
              {!row.isDefault ? (
                <Button
                  size="small"
                  color="error"
                  disabled={writesBlocked || busy}
                  onClick={() =>
                    void confirmThen(t('inventory.godownConfirmDelete', { name: label }), () => remove.mutate(id))
                  }
                >
                  {t('sweep2.delete')}
                </Button>
              ) : null}
            </Stack>
          );
        }}
      />
      {dialog}
      <Dialog open={open} onClose={close} fullWidth maxWidth="xs">
        <DialogTitle>{editing ? t('inventory.godownEdit') : t('sweep2.newGodown')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('sweep.name')}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                // A new godown's code follows its name until someone types a code of their own.
                if (!editing && !codeTouched) setCode(codeFromName(e.target.value));
              }}
              autoFocus
            />
            <TextField
              label={t('sweep.code')}
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                setCodeTouched(true);
              }}
            />
            {error ? <HelpErrorAlert message={error} onClose={() => setError('')} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>{t('sweep2.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || !name.trim() || save.isPending} onClick={() => save.mutate()}>
            {t('sweep2.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
