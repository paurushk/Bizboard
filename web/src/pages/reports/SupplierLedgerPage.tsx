import { useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';
import PrintIcon from '@mui/icons-material/Print';
import { useQuery } from '@tanstack/react-query';
import { getSupplierLedger, listSuppliers } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import type { Supplier } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';

export function SupplierLedgerPage() {
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const ledger = useQuery({
    queryKey: ['supplier-ledger', supplier?.id],
    queryFn: () => getSupplierLedger(supplier!.id),
    enabled: Boolean(supplier?.id),
  });

  const filteredEntries = useMemo(() => {
    const entries = ledger.data?.entries ?? [];
    return entries.filter((e) => {
      if (dateFrom && e.date < dateFrom) return false;
      if (dateTo && e.date > dateTo) return false;
      return true;
    });
  }, [ledger.data?.entries, dateFrom, dateTo]);

  const handleWhatsAppShare = () => {
    if (!supplier || !ledger.data) return;
    const phone = (supplier.phone ?? '').replace(/\D/g, '');
    const text = encodeURIComponent(
      `Hello ${supplier.name},\nAccount statement summary:\nTotal Payable Balance: ₹${ledger.data.outstanding}`,
    );
    const url = phone ? `https://wa.me/91${phone}?text=${text}` : `https://wa.me/?text=${text}`;
    openShareUrl(url);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.supplierLedger')}</Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'stretch', md: 'center' }}>
        <Autocomplete
          options={suppliers.data ?? []}
          getOptionLabel={(o) => `${o.name}${o.phone ? ` (${o.phone})` : ''}`}
          value={supplier}
          onChange={(_, v) => setSupplier(v)}
          sx={{ minWidth: 280, flex: 1 }}
          renderInput={(params) => <TextField {...params} label={t('billing.supplier')} />}
        />
        <TextField
          type="date"
          size="small"
          label={t('common.dateFrom')}
          InputLabelProps={{ shrink: true }}
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <TextField
          type="date"
          size="small"
          label={t('common.dateTo')}
          InputLabelProps={{ shrink: true }}
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />
        {supplier && ledger.data ? (
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              color="success"
              startIcon={<WhatsAppIcon />}
              onClick={handleWhatsAppShare}
            >
              {t('reports.shareOnWhatsapp')}
            </Button>
            <Button
              variant="outlined"
              startIcon={<PrintIcon />}
              onClick={() => window.print()}
            >
              {t('common.print')}
            </Button>
          </Stack>
        ) : null}
      </Stack>

      {!supplier ? <EmptyState description="Select a supplier to view ledger transactions and outstanding payables." /> : null}
      {supplier && ledger.isLoading ? <LoadingState /> : null}
      {ledger.isError ? (
        <ErrorState message={ledger.error.message} onRetry={() => void ledger.refetch()} />
      ) : null}
      {ledger.data ? (
        <>
          <Paper sx={{ p: 2, bgcolor: 'background.paper', borderRadius: 1.5 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
              <Typography variant="subtitle1">
                {supplier?.name} {supplier?.phone ? `· ${supplier.phone}` : ''}
              </Typography>
              <Typography variant="h6" color="primary.main">
                {t('dashboard.payables')}: <strong>{formatMoney(ledger.data.outstanding)}</strong>
              </Typography>
            </Stack>
          </Paper>

          {filteredEntries.length === 0 ? (
            <EmptyState description="No transactions found for the selected date range." />
          ) : (
            <Paper sx={{ overflow: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('common.date')}</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>{t('common.number')}</TableCell>
                    <TableCell align="right">Paid (−) / डेबिट</TableCell>
                    <TableCell align="right">Billed (+) / क्रेडिट</TableCell>
                    <TableCell align="right">{t('reports.dueBalance')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredEntries.map((e, idx) => (
                    <TableRow key={`${e.date}-${e.number}-${idx}`}>
                      <TableCell>{e.date}</TableCell>
                      <TableCell>{e.type}</TableCell>
                      <TableCell>
                        {e.number ?? '—'}
                        {e.jvNumber && e.jvNumber !== e.number ? (
                          <Typography variant="caption" display="block" color="text.secondary">
                            {e.jvNumber}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right" sx={{ color: Number(e.debit) > 0 ? 'success.main' : 'text.secondary' }}>
                        {formatMoney(e.debit)}
                      </TableCell>
                      <TableCell align="right" sx={{ color: Number(e.credit) > 0 ? 'text.primary' : 'text.secondary', fontWeight: Number(e.credit) > 0 ? 600 : 400 }}>
                        {formatMoney(e.credit)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        {formatMoney(e.balance)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </>
      ) : null}
    </Stack>
  );
}
