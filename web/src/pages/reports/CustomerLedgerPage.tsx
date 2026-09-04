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
import { getCustomerLedger } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { t } from '@/i18n';
import type { Customer } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';

export function CustomerLedgerPage() {
  const [customer, setCustomer] = useState<Customer | null>(null);
  // F2-025: search-as-you-type instead of loading every customer up front.
  const customerSearch = useCustomerSearch({ selected: customer });
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const ledger = useQuery({
    queryKey: ['customer-ledger', customer?.id, dateFrom, dateTo],
    queryFn: () =>
      getCustomerLedger(customer!.id, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    enabled: Boolean(customer?.id),
  });

  const entries = useMemo(() => ledger.data?.entries ?? [], [ledger.data?.entries]);

  const handleWhatsAppShare = () => {
    if (!customer || !ledger.data) return;
    let formattedPhone = (customer.phone ?? '').replace(/\D/g, '');
    if (formattedPhone.length === 10) {
      formattedPhone = `91${formattedPhone}`;
    }
    const text = encodeURIComponent(
      `Hello ${customer.name},\nYour account statement from our shop:\nTotal Outstanding Balance: ${formatMoney(ledger.data.outstanding)}\nThank you for your business!`,
    );
    const url = formattedPhone ? `https://wa.me/${formattedPhone}?text=${text}` : `https://wa.me/?text=${text}`;
    openShareUrl(url);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.customerLedger')}</Typography>
      <Stack
        className="no-print"
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', md: 'center' }}
      >
        <Autocomplete
          options={customerSearch.options}
          getOptionLabel={(o) => `${o.name}${o.phone ? ` (${o.phone})` : ''}`}
          filterOptions={(opts) => opts}
          value={customer}
          onChange={(_, v) => setCustomer(v)}
          onInputChange={(_, v) => customerSearch.setQuery(v)}
          loading={customerSearch.isFetching}
          sx={{ minWidth: 280, flex: 1 }}
          slotProps={{
            popper: { sx: { zIndex: 1400 } },
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t('billing.customer')}
              placeholder="Type to search name, phone, or GSTIN"
              helperText={!customerSearch.enabled ? t('common.typeToSearch') : undefined}
            />
          )}
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
        {customer && ledger.data ? (
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

      {!customer ? <EmptyState description="Select a customer to view ledger transactions and outstanding balance." /> : null}
      {customer && ledger.isLoading ? <LoadingState /> : null}
      {ledger.isError ? (
        <ErrorState message={ledger.error.message} error={ledger.error} onRetry={() => void ledger.refetch()} />
      ) : null}
      {ledger.data ? (
        <>
          <Paper sx={{ p: 2, bgcolor: 'background.paper', borderRadius: 1.5 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
              <Typography variant="subtitle1">
                {customer?.name} {customer?.phone ? `· ${customer.phone}` : ''}
              </Typography>
              <Typography variant="h6" color="primary.main">
                {t('reports.dueBalance')}: <strong>{formatMoney(ledger.data.outstanding)}</strong>
              </Typography>
            </Stack>
          </Paper>

          {entries.length === 0 ? (
            <EmptyState description="No transactions found for the selected date range." />
          ) : (
            // F3-017: deliberately NOT virtualized — the Print button above
            // relies on every row being in the DOM (a windowed list would
            // only print the currently-visible rows).
            <Paper sx={{ overflow: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('common.date')}</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>{t('common.number')}</TableCell>
                    <TableCell align="right">{t('reports.billedAmount')}</TableCell>
                    <TableCell align="right">{t('reports.receivedAmount')}</TableCell>
                    <TableCell align="right">{t('reports.dueBalance')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {entries.map((e, idx) => (
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
                      <TableCell align="right" sx={{ color: Number(e.debit) > 0 ? 'text.primary' : 'text.secondary' }}>
                        {formatMoney(e.debit)}
                      </TableCell>
                      <TableCell align="right" sx={{ color: Number(e.credit) > 0 ? 'success.main' : 'text.secondary', fontWeight: Number(e.credit) > 0 ? 600 : 400 }}>
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
