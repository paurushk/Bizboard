/** Shared building blocks for the customer care, jobs and contracts screens (FND-02 … FND-10). */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { recordLinks, recordTimeline, type LinkItem, type SlaState, type TimelineRow } from '@/api/care';
import { listCompanyUsers } from '@/api/resources';
import { StatusChip } from '@/components/StatusChip';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { enumLabel, type EnumGroup } from '@/utils/enumLabels';
import type { ChipTone } from '@/utils/status';
import { formatSpan, formatStamp } from './format';

// ---- layout (FND-02) ----------------------------------------------------------------------------------------------------------

export function CareHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1}>
      <Box>
        <Typography variant="h5" component="h1">{title}</Typography>
        {subtitle ? <Typography variant="body2" color="text.secondary">{subtitle}</Typography> : null}
      </Box>
      {actions ? <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{actions}</Stack> : null}
    </Stack>
  );
}

/** List on the left and the open record on the right; one at a time on a phone. */
export function MasterDetail({
  list,
  detail,
  hasSelection,
  backTo,
  detailLabel,
}: {
  list: ReactNode;
  detail: ReactNode;
  hasSelection: boolean;
  backTo: { pathname: string; search: string };
  detailLabel: string;
}) {
  const theme = useTheme();
  const wide = useMediaQuery(theme.breakpoints.up('md'));
  if (!wide) {
    return hasSelection ? (
      <Stack spacing={1}>
        <Button component={RouterLink} to={backTo} size="small" sx={{ alignSelf: 'flex-start' }}>
          {t('care.common.backToList')}
        </Button>
        <section aria-label={detailLabel}>{detail}</section>
      </Stack>
    ) : (
      <>{list}</>
    );
  }
  return (
    <Box
      sx={{
        display: 'grid',
        gap: 2,
        alignItems: 'start',
        gridTemplateColumns: hasSelection ? 'minmax(320px, 2fr) minmax(400px, 3fr)' : '1fr',
      }}
    >
      <Box>{list}</Box>
      {hasSelection ? <Box component="section" aria-label={detailLabel}>{detail}</Box> : null}
    </Box>
  );
}

// ---- table that turns into cards on a phone (FND-02, FND-09) --------------------------------------------------------

export type CareColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: 'right';
  /** The cell that carries the row's link. Exactly one column should be primary. */
  primary?: boolean;
  /** Shown on a phone card as a small line under the title (default). Set false to drop it there. */
  mobile?: boolean;
};

export function CareTable<T>({
  columns,
  rows,
  rowKey,
  rowHref,
  caption,
  selectedId,
}: {
  columns: CareColumn<T>[];
  rows: T[];
  rowKey: (row: T) => number;
  rowHref: (row: T) => { pathname: string; search?: string } | string;
  caption: string;
  selectedId?: number | null;
}) {
  const theme = useTheme();
  const phone = useMediaQuery(theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const primary = columns.find((column) => column.primary) ?? columns[0];
  if (phone) {
    return (
      <Stack spacing={1} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)}>
            <Card variant="outlined">
              <CardActionArea component={RouterLink} to={rowHref(row)} sx={{ p: 1.5, minHeight: 48 }}>
                <Typography variant="subtitle2" component="div">{primary.render(row)}</Typography>
                {columns
                  .filter((column) => column !== primary && column.mobile !== false)
                  .map((column) => (
                    <Stack key={column.key} direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">{column.header}</Typography>
                      <Box sx={{ fontSize: 13 }}>{column.render(row)}</Box>
                    </Stack>
                  ))}
              </CardActionArea>
            </Card>
          </li>
        ))}
      </Stack>
    );
  }
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small" aria-label={caption}>
        <caption style={{ position: 'absolute', left: -9999 }}>{caption}</caption>
        <TableHead>
          <TableRow>
            {columns.map((column) => (
              <TableCell key={column.key} scope="col" align={column.align}>{column.header}</TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => {
            const href = rowHref(row);
            return (
              <TableRow
                key={rowKey(row)}
                hover
                selected={selectedId === rowKey(row)}
                onClick={() => navigate(href)}
                sx={{ cursor: 'pointer' }}
              >
                {columns.map((column) => (
                  <TableCell key={column.key} align={column.align}>
                    {column === primary ? (
                      <Link component={RouterLink} to={href} underline="hover" onClick={(event) => event.stopPropagation()}>
                        {column.render(row)}
                      </Link>
                    ) : (
                      column.render(row)
                    )}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export function Pager({
  page,
  count,
  pageSize,
  onPage,
}: {
  page: number;
  count: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <Stack direction="row" spacing={1} alignItems="center" component="nav" aria-label={t('care.common.pagination')}>
      <Button size="small" disabled={page <= 1} onClick={() => onPage(page - 1)}>{t('common.previous')}</Button>
      <Typography variant="caption" aria-live="polite">{t('care.common.pageOf', { page, pages, count })}</Typography>
      <Button size="small" disabled={page >= pages} onClick={() => onPage(page + 1)}>{t('common.next')}</Button>
    </Stack>
  );
}

/** Search box that waits for a pause in typing before it changes the list. Re-key it to clear it. */
export function SearchField({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (next: string) => void;
  label?: string;
}) {
  const [text, setText] = useState(value);
  const debounced = useDebouncedValue(text, 350);
  const last = useRef(value);
  const callback = useRef(onChange);
  useEffect(() => {
    callback.current = onChange;
  });
  useEffect(() => {
    if (debounced !== last.current) {
      last.current = debounced;
      callback.current(debounced);
    }
  }, [debounced]);
  return (
    <TextField
      size="small"
      type="search"
      label={label ?? t('care.common.search')}
      value={text}
      onChange={(event) => setText(event.target.value)}
      sx={{ minWidth: 220 }}
    />
  );
}

// ---- status chips ------------------------------------------------------------------------------------------------------------

const TONES: Partial<Record<EnumGroup, Record<string, ChipTone>>> = {
  ticketStatus: { OPEN: 'info', IN_PROGRESS: 'warning', WAITING: 'default', RESOLVED: 'success', CLOSED: 'default' },
  ticketPriority: { LOW: 'default', MEDIUM: 'info', HIGH: 'warning', URGENT: 'error' },
  complaintStatus: { OPEN: 'info', INSPECTING: 'warning', APPROVED: 'success', REJECTED: 'error', RESOLVED: 'success' },
  contractStatus: { ACTIVE: 'success', EXPIRING: 'warning', EXPIRED: 'error', CANCELLED: 'default' },
  jobStatus: { DRAFT: 'default', IN_PROGRESS: 'info', INVOICED: 'success', CANCELLED: 'default' },
  projectStatus: { OPEN: 'info', CLOSED: 'success', CANCELLED: 'default' },
  milestoneStatus: { PLANNED: 'default', READY: 'warning', INVOICED: 'success' },
};

/** A coloured status with its words (never colour alone). */
export function StatusPill({ group, value }: { group: EnumGroup; value: string | null | undefined }) {
  const tone = TONES[group]?.[String(value ?? '')] ?? 'default';
  return <StatusChip tone={tone} label={enumLabel(group, value)} />;
}

const SLA_TONE: Record<SlaState, ChipTone> = {
  none: 'default', running: 'info', paused: 'default', breached: 'error', met: 'success', breached_resolved: 'error',
};

/** The ticket clock as the server judged it; a resolved ticket keeps its verdict (TKT-01). */
export function SlaChip({ state, remainingSeconds }: { state: SlaState; remainingSeconds: number | null }) {
  if (state === 'none') return null;
  const time = formatSpan(remainingSeconds);
  const label = t(`care.sla.${state}`, { time });
  return <StatusChip tone={SLA_TONE[state]} label={label} />;
}

// ---- pickers (FND-04) -----------------------------------------------------------------------------------------------------------

/** Search-as-you-type picker. People choose by number or name, never by typing a database id. */
export function EntityPicker<T extends { id: number }>({
  label,
  value,
  onChange,
  search,
  getLabel,
  queryKey,
  disabled,
  required,
  helperText,
  minWidth = 240,
}: {
  label: string;
  value: T | null;
  onChange: (next: T | null) => void;
  search: (q: string) => Promise<T[]>;
  getLabel: (row: T) => string;
  queryKey: unknown[];
  disabled?: boolean;
  required?: boolean;
  helperText?: string;
  minWidth?: number;
}) {
  const [input, setInput] = useState('');
  const debounced = useDebouncedValue(input, 300).trim();
  const query = useQuery({
    queryKey: ['care-pick', ...queryKey, debounced],
    queryFn: () => search(debounced),
    staleTime: 30_000,
    enabled: !disabled,
  });
  let options = query.data ?? [];
  if (value && !options.some((row) => row.id === value.id)) options = [value, ...options];
  return (
    <Autocomplete
      options={options}
      value={value}
      disabled={disabled}
      loading={query.isFetching}
      filterOptions={(rows) => rows}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      getOptionLabel={getLabel}
      onChange={(_, next) => onChange(next)}
      onInputChange={(_, next, reason) => {
        if (reason === 'input') setInput(next);
      }}
      noOptionsText={t('care.common.noMatches')}
      sx={{ minWidth }}
      renderInput={(params) => (
        <TextField {...params} size="small" label={label} required={required} helperText={helperText} />
      )}
    />
  );
}

export type Member = { id: number; fullName: string; email: string };

/** A teammate. The list is short, so it is fetched once and filtered here. */
export function MemberPicker({
  label,
  value,
  onChange,
  disabled,
  minWidth = 220,
}: {
  label: string;
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  minWidth?: number;
}) {
  const users = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers, staleTime: 60_000 });
  const members = (users.data ?? []) as unknown as Member[];
  const selected = members.find((member) => member.id === value) ?? null;
  return (
    <Autocomplete
      options={members}
      value={selected}
      disabled={disabled}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      getOptionLabel={(member) => member.fullName || member.email}
      onChange={(_, next) => onChange(next ? next.id : null)}
      noOptionsText={t('care.common.noMatches')}
      sx={{ minWidth }}
      renderInput={(params) => <TextField {...params} size="small" label={label} />}
    />
  );
}

// ---- linked records and activity (FND-07, FND-10, XLK-03) -----------------------------------------------------------

export function LinkedRecords({ entity, id }: { entity: string; id: number }) {
  const links = useQuery({ queryKey: ['care-links', entity, id], queryFn: () => recordLinks(entity, id) });
  const rows: LinkItem[] = links.data ?? [];
  return (
    <Box>
      <Typography variant="subtitle2" component="h3">{t('care.common.linked')}</Typography>
      {links.isLoading ? <Typography variant="body2" color="text.secondary">{t('common.loading')}</Typography> : null}
      {links.isError ? <Typography variant="body2" color="error">{getErrorMessage(links.error)}</Typography> : null}
      {!links.isLoading && !links.isError && rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">{t('care.common.noLinks')}</Typography>
      ) : null}
      <List dense disablePadding>
        {rows.map((row) => (
          <ListItem key={`${row.kind}-${row.id}`} disableGutters secondaryAction={row.status ? <Chip size="small" label={row.status} variant="outlined" /> : undefined}>
            <ListItemText
              primary={
                <Link component={RouterLink} to={row.href} underline="hover">
                  {t(`care.kinds.${row.kind}`)} {row.number}
                </Link>
              }
              secondary={row.label}
            />
          </ListItem>
        ))}
      </List>
    </Box>
  );
}

function humanise(action: string): string {
  return action.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
}

export function ActivityTimeline({ entity, id, fetcher }: { entity: string; id: number; fetcher?: () => Promise<TimelineRow[]> }) {
  const rows = useQuery({
    queryKey: ['care-activity', entity, id],
    queryFn: fetcher ?? (() => recordTimeline(entity, id)),
  });
  return (
    <Box>
      <Typography variant="subtitle2" component="h3">{t('care.common.activity')}</Typography>
      {rows.isError ? <Typography variant="body2" color="error">{getErrorMessage(rows.error)}</Typography> : null}
      {!rows.isLoading && !rows.isError && (rows.data ?? []).length === 0 ? (
        <Typography variant="body2" color="text.secondary">{t('care.common.noActivity')}</Typography>
      ) : null}
      <List dense disablePadding>
        {(rows.data ?? []).slice(0, 30).map((row) => {
          const key = `care.activity.${row.action}`;
          const label = t(key) === key ? humanise(row.action) : t(key);
          return (
            <ListItem key={row.id} disableGutters>
              <ListItemText
                primary={label}
                secondary={`${formatStamp(row.createdAt)}${row.userName ? ` · ${row.userName}` : ''}`}
              />
            </ListItem>
          );
        })}
      </List>
    </Box>
  );
}

/** Text for screen readers only, e.g. the name of a column that holds just buttons or checkboxes. */
export function VisuallyHidden({ children }: { children: ReactNode }) {
  return (
    <Box
      component="span"
      sx={{ border: 0, clip: 'rect(0 0 0 0)', height: '1px', m: '-1px', overflow: 'hidden', p: 0, position: 'absolute', whiteSpace: 'nowrap', width: '1px' }}
    >
      {children}
    </Box>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="div">{label}</Typography>
      <Typography variant="body2" component="div">{children || '—'}</Typography>
    </Box>
  );
}

export function CustomerLink({ id, name }: { id: number; name: string }) {
  return (
    <Link component={RouterLink} to={`/sales/customers/${id}`} underline="hover">{name || `#${id}`}</Link>
  );
}
