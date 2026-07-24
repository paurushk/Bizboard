import { useEffect, useState } from 'react';
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
import {
  cancelSalesInvoice,
  completeSalesInvoice,
  deleteSalesInvoice,
  downloadInvoicePdf,
  fetchNextPage,
  listSalesInvoicesPage,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

function invoiceNumberLabel(inv: SalesInvoice): string {
  if (inv.number && inv.number.trim()) return inv.number;
  return `Draft #${inv.id}`;
}

export function SalesHistoryPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [extraRows, setExtraRows] = useState<SalesInvoice[]>([]);
  const [nextUrl, setNextUrl] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
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
    queryKey: ['sales-invoices'],
    queryFn: () => listSalesInvoicesPage(),
    staleTime: 0,
    refetchOnMount: 'always',
  });

  useEffect(() => {
    if (!query.data) return;
    setExtraRows([]);
    setNextUrl(query.data.next);
  }, [query.data]);

  const closeMenu = () => {
    setMenuAnchor(null);
    setActive(null);
  };

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['sales-invoices'] });

  const completeMutation = useMutation({
    mutationFn: (id: number) => completeSalesInvoice(id),
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

  const busy =
    completeMutation.isPending || cancelMutation.isPending || deleteMutation.isPending;

  const loadMore = async () => {
    if (!nextUrl) return;
    setLoadingMore(true);
    try {
      const page = await fetchNextPage<SalesInvoice>(nextUrl);
      setExtraRows((prev) => [...prev, ...page.results]);
      setNextUrl(page.next);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  };

  const rows = [...(query.data?.results ?? []), ...extraRows];
  const showLoading = query.isPending || (query.isFetching && rows.length === 0);
  const showEmpty = !showLoading && !query.isError && rows.length === 0;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.salesHistory')}</Typography>
        <Button component={RouterLink} to="/sales/new" variant="contained">
          {t('nav.newInvoice')}
        </Button>
      </Stack>

      {message ? (
        <Alert severity="success" onClose={() => setMessage(null)}>
          {message}
        </Alert>
      ) : null}
      {error ? (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      {showLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState
          message={getErrorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {showEmpty ? (
        <EmptyState
          description={t('empty.invoices')}
          action={
            <Button component={RouterLink} to="/sales/new" variant="contained">
              {t('nav.newInvoice')}
            </Button>
          }
        />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
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
              {rows.map((inv) => (
                <TableRow key={inv.id} hover>
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
                      tone={documentStatusTone(inv.status)}
                      labelKey={statusLabelKey(inv.status)}
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
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {nextUrl ? (
        <Button variant="outlined" disabled={loadingMore} onClick={() => void loadMore()}>
          {t('history.loadMore')}
        </Button>
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

        {active?.status === 'DRAFT' || active?.status === 'COMPLETED' ? (
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

        {active?.status === 'DRAFT' ? (
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
          </>
        ) : null}

        {active?.status === 'COMPLETED' ? (
          <MenuItem
            onClick={() => {
              if (!active) return;
              const id = active.id;
              closeMenu();
              cancelMutation.mutate(id);
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
              closeMenu();
              deleteMutation.mutate(id);
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
