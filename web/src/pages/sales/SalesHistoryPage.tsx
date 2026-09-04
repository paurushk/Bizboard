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
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined';
import PictureAsPdfOutlinedIcon from '@mui/icons-material/PictureAsPdfOutlined';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import {
  cancelSalesInvoice,
  completeSalesInvoice,
  deleteSalesInvoice,
  downloadInvoicePdf,
  downloadInvoiceThermalPdf,
  listSalesInvoicesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { HelpEmptyLink } from '@/pages/help/HelpEmptyLink';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { formatMoney } from '@/utils/money';
import { canCreateSales, canCancelDocuments } from '@/utils/permissions';
import { documentStatusTone, paidAwareStatus, statusLabelKey } from '@/utils/status';
import { isSetupWizardEnabled } from '@/config/features';

const PAGE_SIZE = 50;

function invoiceNumberLabel(inv: SalesInvoice): string {
  if (inv.number && inv.number.trim()) return inv.number;
  return `Draft #${inv.id}`;
}

export function SalesHistoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [active, setActive] = useState<SalesInvoice | null>(null);
  const [message, setMessage] = useState<string | null>(() => {
    const flash = location.state as { message?: unknown } | null;
    return typeof flash?.message === 'string' ? flash.message : null;
  });
  const [error, setError] = useState<string | null>(() => {
    const flash = location.state as { paymentWarning?: unknown } | null;
    return typeof flash?.paymentWarning === 'string' ? flash.paymentWarning : null;
  });

  const query = useQuery({
    queryKey: ['sales-invoices', page],
    queryFn: () => listSalesInvoicesPage({ page, pageSize: PAGE_SIZE }),
    staleTime: 0,
    refetchOnMount: 'always',
  });

  const closeMenu = () => {
    setMenuAnchor(null);
    setActive(null);
  };

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['sales-invoices'] });

  const completeMutation = useMutation({
    // F2-017: go through the same confirm-retry helper the editor uses so a
    // blank-place-of-supply / GSTIN-total-changed invoice doesn't dead-end here.
    mutationFn: (id: number) =>
      completeWithConfirms((extra) => completeSalesInvoice(id, extra)),
    onSuccess: (inv) => {
      setMessage(`Invoice ${invoiceNumberLabel(inv)} completed`);
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelSalesInvoice(id),
    onSuccess: (inv) => {
      setMessage(`Invoice ${invoiceNumberLabel(inv)} cancelled`);
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteSalesInvoice(id),
    onSuccess: () => {
      setMessage('Draft deleted');
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const runPdf = async (mode: 'print' | 'download') => {
    if (!active) return;
    const id = active.id;
    closeMenu();
    try {
      const blob = await downloadInvoicePdf(id, { copy: 'ORIGINAL' });
      if (mode === 'print') printBlob(blob);
      else triggerBlobDownload(blob, `${invoiceNumberLabel(active)}.pdf`);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const runThermalPrint = async (width: 80 | 58) => {
    if (!active) return;
    const id = active.id;
    closeMenu();
    try {
      const blob = await downloadInvoiceThermalPdf(id, width);
      printBlob(blob);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const busy =
    completeMutation.isPending || cancelMutation.isPending || deleteMutation.isPending;

  const rows = query.data?.results ?? [];
  const showLoading = query.isPending || (query.isFetching && rows.length === 0);
  const showEmpty = !showLoading && !query.isError && rows.length === 0;
  const allowCreate = canCreateSales(user);
  const allowCancel = canCancelDocuments(user);
  const canContinueSetup =
    isSetupWizardEnabled() &&
    user?.role === 'OWNER' &&
    !user.company?.onboarding?.activationDone;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.salesHistory')}</Typography>
        {allowCreate ? (
          <Button component={RouterLink} to="/sales/new" variant="contained">
            {t('nav.newInvoice')}
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
          description={t('empty.invoices')}
          action={
            <HelpEmptyLink intent="cannot-complete-invoice">
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                {canContinueSetup ? (
                  <Button component={RouterLink} to="/setup?step=first_bill" variant="contained">
                    {t('setup.continueSetup')}
                  </Button>
                ) : null}
                {allowCreate ? (
                  <Button component={RouterLink} to="/sales/new" variant={canContinueSetup ? 'outlined' : 'contained'}>
                    {t('nav.newInvoice')}
                  </Button>
                ) : null}
              </Stack>
            </HelpEmptyLink>
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
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell align="right" width={56}>
                  {t('common.actions')}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {/* Companion fix to UXW2B-007: VirtualizedTable's outer spacer reserves the
                  full scrollable height, but only the current window of rows is rendered
                  in normal flow — without these leading/trailing spacer rows they'd always
                  render right after the header, so scrolling past the first screenful showed
                  blank space instead of the (correctly computed) later rows.
                  F3-042: spacer heights derive from the virtualizer's real
                  measured totalSize, not `rows.length * rowHeight`. */}
              {virtualRows.length > 0 && virtualRows[0].start > 0 ? (
                <TableRow
                  style={{ height: virtualRows[0].start, padding: 0, border: 0 }}
                  aria-hidden
                  role="presentation"
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={6} />
                </TableRow>
              ) : null}
              {virtualRows.map((vRow) => {
                const inv = rows[vRow.index];
                if (!inv) return null;
                return (
                <TableRow
                  key={inv.id}
                  hover
                  data-index={vRow.index}
                  ref={measureElement}
                  style={{ height: vRow.size }}
                >
                  <TableCell>{inv.invoiceDate}</TableCell>
                  <TableCell>
                    <Typography
                      component={RouterLink}
                      to={`/sales/history/${inv.id}`}
                      fontWeight={600}
                      sx={{ color: 'primary.main', textDecoration: 'none' }}
                    >
                      {invoiceNumberLabel(inv)}
                    </Typography>
                  </TableCell>
                  <TableCell>{inv.customerName ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(paidAwareStatus(inv.status, inv.balance, inv.paymentState))}
                      labelKey={statusLabelKey(paidAwareStatus(inv.status, inv.balance, inv.paymentState))}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(inv.grandTotal)}</TableCell>
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      aria-label={t('common.actions')}
                      disabled={busy}
                      onClick={(e) => {
                        setActive(inv);
                        setMenuAnchor(e.currentTarget);
                      }}
                    >
                      <MoreVertIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
                );
              })}
              {virtualRows.length > 0 &&
              Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end) > 0 ? (
                <TableRow
                  style={{
                    height: Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end),
                    padding: 0,
                    border: 0,
                  }}
                  aria-hidden
                  role="presentation"
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
            if (active) navigate(`/sales/history/${active.id}`);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <OpenInNewIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.open')}</ListItemText>
        </MenuItem>

        {allowCreate && (active?.status === 'DRAFT' || active?.status === 'COMPLETED') ? (
          <MenuItem
            onClick={() => {
              if (active) navigate(`/sales/history/${active.id}/edit`);
              closeMenu();
            }}
          >
            <ListItemIcon>
              <EditOutlinedIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>{t('common.edit')}</ListItemText>
          </MenuItem>
        ) : null}

        {allowCreate && active?.status === 'DRAFT' ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              const id = active.id;
              closeMenu();
              completeMutation.mutate(id);
            }}
          >
            <ListItemIcon>
              <CheckCircleOutlineIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>{t('common.complete')}</ListItemText>
          </MenuItem>
        ) : null}

        {active?.status === 'COMPLETED' || active?.status === 'RETURNED' ? (
          <>
            <MenuItem onClick={() => void runPdf('print')}>
              <ListItemIcon>
                <PrintOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('common.print')}</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => void runPdf('download')}>
              <ListItemIcon>
                <PictureAsPdfOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>{t('common.download')}</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => void runThermalPrint(80)}>
              <ListItemIcon>
                <PrintOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Print receipt (80mm)</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => void runThermalPrint(58)}>
              <ListItemIcon>
                <PrintOutlinedIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Print receipt (58mm)</ListItemText>
            </MenuItem>
          </>
        ) : null}

        {active?.status === 'COMPLETED' && allowCancel ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              const id = active.id;
              const label = invoiceNumberLabel(active);
              closeMenu();
              // BUG-520: a single mis-click on this menu used to cancel a
              // completed, potentially already-shared GST invoice.
              if (window.confirm(t('history.confirmCancel', { label }))) {
                cancelMutation.mutate(id);
              }
            }}
          >
            <ListItemIcon>
              <CancelOutlinedIcon fontSize="small" color="error" />
            </ListItemIcon>
            <ListItemText>{t('common.cancel')}</ListItemText>
          </MenuItem>
        ) : null}

        {active?.status === 'DRAFT' ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              const id = active.id;
              const label = invoiceNumberLabel(active);
              closeMenu();
              if (window.confirm(t('history.confirmDeleteDraft', { label }))) {
                deleteMutation.mutate(id);
              }
            }}
          >
            <ListItemIcon>
              <DeleteOutlineIcon fontSize="small" color="error" />
            </ListItemIcon>
            <ListItemText>{t('common.delete')}</ListItemText>
          </MenuItem>
        ) : null}
      </Menu>
    </Stack>
  );
}
