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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelPurchase,
  completePurchase,
  deletePurchase,
  fetchNextPage,
  listPurchasesPage,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { PurchaseInvoice } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

function purchaseNumberLabel(p: PurchaseInvoice): string {
  if (p.number && p.number.trim()) return p.number;
  return `Draft #${p.id}`;
}

export function PurchaseHistoryPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [extraRows, setExtraRows] = useState<PurchaseInvoice[]>([]);
  const [nextUrl, setNextUrl] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
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
    queryKey: ['purchases'],
    queryFn: () => listPurchasesPage(),
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

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['purchases'] });

  const loadMore = async () => {
    if (!nextUrl) return;
    setLoadingMore(true);
    try {
      const page = await fetchNextPage<PurchaseInvoice>(nextUrl);
      setExtraRows((prev) => [...prev, ...page.results]);
      setNextUrl(page.next);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  };

  const completeMutation = useMutation({
    mutationFn: (id: number) => completePurchase(id),
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

  const rows = [...(query.data?.results ?? []), ...extraRows];
  const showLoading = query.isPending || (query.isFetching && rows.length === 0);
  const showEmpty = !showLoading && !query.isError && rows.length === 0;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.purchaseHistory')}</Typography>
        <Button component={RouterLink} to="/purchases/new" variant="contained">
          {t('nav.newPurchase')}
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
          description="No purchases yet."
          action={
            <Button component={RouterLink} to="/purchases/new" variant="contained">
              {t('nav.newPurchase')}
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
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell align="right" width={56}>
                  {t('common.actions')}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id} hover>
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
            if (active) navigate(`/purchases/history/${active.id}`);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <OpenInNewIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.open')}</ListItemText>
        </MenuItem>
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
        <MenuItem
          disabled={!active || active.status !== 'COMPLETED'}
          onClick={() => {
            if (active) cancelMutation.mutate(active.id);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <CancelOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('common.cancel')}</ListItemText>
        </MenuItem>
        <MenuItem
          disabled={!active || active.status !== 'DRAFT'}
          onClick={() => {
            if (active) deleteMutation.mutate(active.id);
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
