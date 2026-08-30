import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import RestoreIcon from '@mui/icons-material/Restore';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import {
  fieldDefRowErrors,
  fieldDefsHaveErrors,
  MAX_ACTIVE_CUSTOM_FIELDS,
  MAX_KEY_LEN,
  MAX_LABEL_LEN,
  MAX_LIST_OPTIONS,
  MAX_OPTION_LEN,
  normalizeCustomFieldDefs,
  suggestCustomFieldKey,
  type ItemCustomFieldDef,
} from '@/pages/inventory/itemCustomFieldDefaults';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type FieldDef = ItemCustomFieldDef & { keyTouched?: boolean };

function reconstruct(actives: FieldDef[], inactives: FieldDef[]): FieldDef[] {
  return [...actives, ...inactives];
}

function rowErrorText(
  code: 'required' | 'format' | 'duplicate' | 'max' | 'reserved' | 'length' | undefined,
  kind: 'key' | 'label' | 'options',
  label: string,
): string | undefined {
  if (!code) return undefined;
  if (kind === 'key' && code === 'required') return t('customFields.keyAndLabelRequired');
  if (kind === 'key' && code === 'format') return t('customFields.keyFormat');
  if (kind === 'key' && code === 'duplicate') return t('customFields.keysUnique');
  if (kind === 'key' && code === 'reserved') return t('customFields.reservedName');
  if (kind === 'key' && code === 'max') return t('customFields.keyMax', { max: MAX_KEY_LEN });
  if (kind === 'label' && code === 'required') return t('customFields.keyAndLabelRequired');
  if (kind === 'label' && code === 'duplicate') return t('customFields.labelsUnique');
  if (kind === 'label' && code === 'reserved') return t('customFields.reservedName');
  if (kind === 'label' && code === 'max') return t('customFields.labelMax', { max: MAX_LABEL_LEN });
  if (kind === 'options' && code === 'required') return t('customFields.listNeedsOptions', { label });
  if (kind === 'options' && code === 'max') return t('customFields.maxOptions', { max: MAX_LIST_OPTIONS });
  if (kind === 'options' && code === 'length') return t('customFields.optionMax', { max: MAX_OPTION_LEN });
  return undefined;
}

export function ItemSettingsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const allowed = canManageUsers(user);
  const [defs, setDefs] = useState<FieldDef[]>([]);
  const [optionDraft, setOptionDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<FieldDef | null>(null);
  const [removedOpen, setRemovedOpen] = useState(false);

  const query = useQuery({
    queryKey: ['company'],
    queryFn: getCompany,
    enabled: allowed,
  });

  const savedKeys = useMemo(
    () => new Set((query.data?.itemCustomFieldDefs ?? []).map((row) => row.key)),
    [query.data?.itemCustomFieldDefs],
  );

  useEffect(() => {
    if (!query.data) return;
    setDefs(normalizeCustomFieldDefs(query.data.itemCustomFieldDefs ?? []));
  }, [query.data]);

  const actives = defs.filter((row) => row.active !== false);
  const inactives = defs.filter((row) => row.active === false);

  const setActives = (next: FieldDef[]) => setDefs(reconstruct(next, inactives));

  const mutation = useMutation({
    mutationFn: () => {
      const payload: ItemCustomFieldDef[] = reconstruct(actives, inactives).map((row) => ({
        key: row.key.trim(),
        label: row.label.trim(),
        type: row.type === 'list' ? 'list' : 'text',
        active: row.active !== false,
        options: row.type === 'list' ? (row.options ?? []).map((item) => item.trim()).filter(Boolean) : [],
      }));
      if (payload.filter((row) => row.active !== false).length > MAX_ACTIVE_CUSTOM_FIELDS) {
        throw new Error(t('customFields.maxActive', { max: MAX_ACTIVE_CUSTOM_FIELDS }));
      }
      if (fieldDefsHaveErrors(fieldDefRowErrors(payload))) {
        throw new Error(t('customFields.fixRowErrors'));
      }
      return updateCompany({ itemCustomFieldDefs: payload });
    },
    onSuccess: () => {
      setMessage(t('customFields.saved'));
      setError(null);
      void qc.invalidateQueries({ queryKey: ['company'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!allowed) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const allRowErrors = fieldDefRowErrors(reconstruct(actives, inactives));
  const activeRowErrors = allRowErrors.slice(0, actives.length);

  const move = (index: number, delta: number) => {
    const next = [...actives];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setActives(next);
  };

  const addOption = (key: string) => {
    const text = (optionDraft[key] ?? '').trim();
    if (!text) return;
    if (text.length > MAX_OPTION_LEN) return;
    setActives(
      actives.map((row) => {
        if (row.key !== key) return row;
        const options = row.options ?? [];
        if (options.some((item) => item.toLowerCase() === text.toLowerCase())) return row;
        if (options.length >= MAX_LIST_OPTIONS) return row;
        return { ...row, options: [...options, text] };
      }),
    );
    setOptionDraft((current) => ({ ...current, [key]: '' }));
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.itemSettings')}</Typography>
      <Typography color="text.secondary">{t('customFields.settingsHint')}</Typography>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          {actives.length === 0 ? (
            <Alert severity="info">{t('customFields.emptyDefs')}</Alert>
          ) : null}
          {actives.map((row, index) => {
            const locked = savedKeys.has(row.key);
            const rowErr = activeRowErrors[index] ?? {};
            const keyHelp = rowErr.key
              ? rowErrorText(rowErr.key, 'key', row.label)
              : locked
                ? t('customFields.keyLocked')
                : t('customFields.keyHint');
            const labelHelp = rowErrorText(rowErr.label, 'label', row.label);
            const optionsHelp = rowErrorText(rowErr.options, 'options', row.label);
            return (
              <Stack key={`${row.key}-${index}`} spacing={1} sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 2 }}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'flex-start' }}>
                  <TextField
                    label={t('customFields.key')}
                    value={row.key}
                    disabled={locked}
                    error={Boolean(rowErr.key)}
                    helperText={keyHelp}
                    onChange={(e) =>
                      setActives(
                        actives.map((item, i) =>
                          i === index ? { ...item, key: e.target.value, keyTouched: true } : item,
                        ),
                      )
                    }
                    sx={{ flex: 1 }}
                  />
                  <TextField
                    label={t('customFields.label')}
                    value={row.label}
                    error={Boolean(rowErr.label)}
                    helperText={labelHelp ?? ' '}
                    onChange={(e) =>
                      setActives(
                        actives.map((item, i) => {
                          if (i !== index) return item;
                          const nextLabel = e.target.value;
                          const nextKey =
                            item.keyTouched || locked ? item.key : suggestCustomFieldKey(nextLabel);
                          return { ...item, label: nextLabel, key: nextKey };
                        }),
                      )
                    }
                    sx={{ flex: 1 }}
                  />
                  <TextField
                    select
                    label={t('customFields.type')}
                    value={row.type === 'list' ? 'list' : 'text'}
                    disabled={locked}
                    helperText={locked ? t('customFields.typeLocked') : ' '}
                    onChange={(e) =>
                      setActives(
                        actives.map((item, i) =>
                          i === index
                            ? { ...item, type: e.target.value === 'list' ? 'list' : 'text', options: item.options ?? [] }
                            : item,
                        ),
                      )
                    }
                    sx={{ minWidth: 140 }}
                  >
                    <MenuItem value="text">{t('customFields.typeText')}</MenuItem>
                    <MenuItem value="list">{t('customFields.typeList')}</MenuItem>
                  </TextField>
                  <Stack direction="row">
                    <IconButton aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}>
                      <ArrowUpwardIcon />
                    </IconButton>
                    <IconButton
                      aria-label="Move down"
                      disabled={index === actives.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDownwardIcon />
                    </IconButton>
                    <IconButton aria-label="Remove" onClick={() => setRemoveTarget(row)}>
                      <DeleteOutlineIcon />
                    </IconButton>
                  </Stack>
                </Stack>
                {row.type === 'list' ? (
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {(row.options ?? []).map((option) => (
                        <Chip
                          key={option}
                          label={option}
                          onDelete={() =>
                            setActives(
                              actives.map((item, i) =>
                                i === index
                                  ? { ...item, options: (item.options ?? []).filter((entry) => entry !== option) }
                                  : item,
                              ),
                            )
                          }
                        />
                      ))}
                    </Stack>
                    {optionsHelp ? (
                      <Typography color="error" variant="caption">
                        {optionsHelp}
                      </Typography>
                    ) : null}
                    <Stack direction="row" spacing={1} maxWidth={420}>
                      <TextField
                        size="small"
                        label={t('customFields.addOption')}
                        error={Boolean(rowErr.options)}
                        value={optionDraft[row.key] ?? ''}
                        onChange={(e) => setOptionDraft((current) => ({ ...current, [row.key]: e.target.value }))}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            addOption(row.key);
                          }
                        }}
                      />
                      <Button onClick={() => addOption(row.key)}>{t('common.add')}</Button>
                    </Stack>
                  </Stack>
                ) : null}
              </Stack>
            );
          })}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              startIcon={<AddIcon />}
              disabled={actives.length >= MAX_ACTIVE_CUSTOM_FIELDS}
              onClick={() =>
                setActives([
                  ...actives,
                  { key: '', label: '', type: 'text', active: true, options: [], keyTouched: false },
                ])
              }
            >
              {t('customFields.addField')}
            </Button>
            <Button variant="contained" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              {t('common.save')}
            </Button>
          </Stack>
        </Stack>
      </Paper>
      {inactives.length ? (
        <Paper sx={{ p: 2 }}>
          <Button onClick={() => setRemovedOpen((open) => !open)}>
            {t('customFields.removedFields')} ({inactives.length})
          </Button>
          <Collapse in={removedOpen}>
            <Stack spacing={1} sx={{ mt: 1 }}>
              {inactives.map((row) => (
                <Stack key={row.key} direction="row" spacing={1} alignItems="center">
                  <Typography sx={{ flex: 1 }}>
                    {row.label} <Typography component="span" color="text.secondary">({row.key})</Typography>
                  </Typography>
                  <Button
                    startIcon={<RestoreIcon />}
                    disabled={actives.length >= MAX_ACTIVE_CUSTOM_FIELDS}
                    onClick={() => {
                      if (actives.length >= MAX_ACTIVE_CUSTOM_FIELDS) return;
                      setDefs(
                        reconstruct(
                          [...actives, { ...row, active: true }],
                          inactives.filter((item) => item.key !== row.key),
                        ),
                      );
                    }}
                  >
                    {t('customFields.restore')}
                  </Button>
                </Stack>
              ))}
            </Stack>
          </Collapse>
        </Paper>
      ) : null}

      <Dialog open={Boolean(removeTarget)} onClose={() => setRemoveTarget(null)}>
        <DialogTitle>{t('customFields.removeTitle', { label: removeTarget?.label ?? '' })}</DialogTitle>
        <DialogContent>
          <Typography>{t('customFields.removeBody')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoveTarget(null)}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              if (!removeTarget) return;
              const persisted = savedKeys.has(removeTarget.key);
              setDefs(
                reconstruct(
                  actives.filter((row) => row.key !== removeTarget.key),
                  persisted
                    ? [...inactives, { ...removeTarget, active: false }]
                    : inactives.filter((item) => item.key !== removeTarget.key),
                ),
              );
              setRemoveTarget(null);
            }}
          >
            {t('common.remove')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
