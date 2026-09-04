import { useState } from 'react';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import CancelOutlinedIcon from '@mui/icons-material/CancelOutlined';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import {
  cancelPurchase,
  completePurchase,
  deletePurchase,
  listPurchasesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { PurchaseInvoice } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { canCreatePurchases, canCancelDocuments } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

const PAGE_SIZE = 50;

function purchaseNumberLabel(p: PurchaseInvoice): string {
  if (p.number && p.number.trim()) return p.number;
  return `Draft #${p.id}`;
}

export function PurchaseHistoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [active, setActive] = useState<PurchaseInvoice | null>(null);
  const [message, setMessage] = useState<string | null>(() => {
    const flash = location.state as { message?: unknown } | null;
    return typeof flash?.message === 'string' ? flash.message : null;
  });
  const [error, setError] = useState<string | null>(() => {
    const flash = location.state as { paymentWarning?: unknown } | null;
    return typeof flash?.paymentWarning === 'string' ? flash.paymentWarning : null;
  });

  const query = useQuery({
    queryKey: ['purchases', page],
    queryFn: () => listPurchasesPage({ page, pageSize: PAGE_SIZE }),
    staleTime: 0,
    refetchOnMount: 'always',
  });

  const closeMenu = () => {
    setMenuAnchor(null);
    setActive(null);
  };

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['purchases'] });

  const completeMutation = useMutation({
    // F2-017: same confirm-retry helper the editor uses.
    mutationFn: (id: number) =>
      completeWithConfirms((extra) => completePurchase(id, extra)),
    onSuccess: (inv) => {
      setMessage(`Purchase ${purchaseNumberLabel(inv)} completed`);
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelPurchase(id),
    onSuccess: (inv) => {
      setMessage(`Purchase ${purchaseNumberLabel(inv)} cancelled`);
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePurchase(id),
    onSuccess: () => {
      setMessage('Draft deleted');
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const busy =
    completeMutation.isPending || cancelMutation.isPending || deleteMutation.isPending;

  const rows = query.data?.results ?? [];
  const showLoading = query.isPending || (query.isFetching && rows.length === 0);
  const showEmpty = !showLoading && !query.isError && rows.length === 0;
  const allowCreate = canCreatePurchases(user);
  const allowCancel = canCancelDocuments(user);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.purchaseHistory')}</Typography>
        {allowCreate ? (
          <Button component={RouterLink} to="/purchases/new" variant="contained">
            {t('nav.newPurchase')}
          </Button>
        ) : null}
      </Stack>
      {message ? (
        <Alert severity="success" onClose={() => setMessage(null)}>
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} onClose={() => setError(null)} />
      ) : null}
      {showLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState
          message={getErrorMessage(query.error)}
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {showEmpty ? (
        <EmptyState
          description="No purchases yet."
          action={
            allowCreate ? (
              <Button component={RouterLink} to="/purchases/new" variant="contained">
                {t('nav.newPurchase')}
              </Button>
            ) : undefined
          }
        />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={52}>
            {({ rows: virtualRows, totalSize, measureElement }) => (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell align="right" width={56}>
                  {t('common.actions')}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {/* Companion fix to UXW2B-007 — see SalesHistoryPage for the full explanation:
                  without these spacer rows, scrolling past the first screenful showed blank
                  space instead of the (correctly computed) later rows.
                  F3-042: spacer heights derive from the virtualizer's real
                  measured totalSize, not `rows.length * rowHeight` — a row that
                  wraps to two lines no longer desyncs the spacers. */}
              {virtualRows.length > 0 ? (
                <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={6} />
                </TableRow>
              ) : null}
              {virtualRows.map((vRow) => {
                const p = rows[vRow.index];
                if (!p) return null;
                return (
                <TableRow
                  key={p.id}
                  hover
                  data-index={vRow.index}
                  ref={measureElement}
                  style={{ height: vRow.size }}
                >
                  <TableCell>{p.invoiceDate}</TableCell>
                  <TableCell>
                    <Typography
                      component={RouterLink}
                      to={`/purchases/history/${p.id}`}
                      fontWeight={600}
                      sx={{ color: 'primary.main', textDecoration: 'none' }}
                    >
                      {purchaseNumberLabel(p)}
                    </Typography>
                  </TableCell>
                  <TableCell>{p.supplierName ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(p.status)}
                      labelKey={statusLabelKey(p.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(p.grandTotal)}</TableCell>
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      aria-label={t('common.actions')}
                      disabled={busy}
                      onClick={(e) => {
                        setActive(p);
                        setMenuAnchor(e.currentTarget);
                      }}
                    >
                      <MoreVertIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
                );
              })}
              {virtualRows.length > 0 ? (
                <TableRow
                  style={{
                    height: Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end),
                    padding: 0,
                    border: 0,
                  }}
                  aria-hidden
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={6} />
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
            )}
          </VirtualizedTable>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
            {query.data.count ? ` / ${Math.max(1, Math.ceil(query.data.count / PAGE_SIZE))}` : ''}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor) && Boolean(active)}
        onClose={closeMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem
          onClick={() => {
            if (active) navigate(`/purchases/history/${active.id}`);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <OpenInNewIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.open')}</ListItemText>
        </MenuItem>
        {allowCreate ? (
        <MenuItem
          disabled={!active || !(active.status === 'DRAFT' || active.status === 'COMPLETED')}
          onClick={() => {
            if (active) navigate(`/purchases/history/${active.id}/edit`);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <EditOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.edit')}</ListItemText>
        </MenuItem>
        ) : null}
        {allowCreate ? (
        <MenuItem
          disabled={!active || active.status !== 'DRAFT'}
          onClick={() => {
            if (active) completeMutation.mutate(active.id);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <CheckCircleOutlineIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.complete')}</ListItemText>
        </MenuItem>
        ) : null}
        {allowCancel ? (
        <MenuItem
          disabled={!active || active.status !== 'COMPLETED'}
          onClick={() => {
            // BUG-520: same one-click-cancels-a-completed-document risk as
            // the sales history page.
            if (active && window.confirm(t('history.confirmCancel', { label: purchaseNumberLabel(active) }))) {
              cancelMutation.mutate(active.id);
            }
            closeMenu();
          }}
        >
          <ListItemIcon>
            <CancelOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.cancel')}</ListItemText>
        </MenuItem>
        ) : null}
        <MenuItem
          disabled={!active || active.status !== 'DRAFT'}
          onClick={() => {
            if (active && window.confirm(t('history.confirmDeleteDraft', { label: purchaseNumberLabel(active) }))) {
              deleteMutation.mutate(active.id);
            }
            closeMenu();
          }}
        >
          <ListItemIcon>
            <DeleteOutlineIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.delete')}</ListItemText>
        </MenuItem>
      </Menu>
    </Stack>
  );
}
