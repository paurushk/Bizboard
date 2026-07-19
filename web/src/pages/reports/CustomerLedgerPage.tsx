import { useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getCustomerLedger, listCustomers } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import type { Customer } from '@/types/domain';
import { formatMoney } from '@/utils/money';

export function CustomerLedgerPage() {
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const [customer, setCustomer] = useState<Customer | null>(null);

  const ledger = useQuery({
    queryKey: ['customer-ledger', customer?.id],
    queryFn: () => getCustomerLedger(customer!.id),
    enabled: Boolean(customer?.id),
  });

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.customerLedger')}</Typography>
      <Autocomplete
        options={customers.data ?? []}
        getOptionLabel={(o) => o.name}
        value={customer}
        onChange={(_, v) => setCustomer(v)}
        sx={{ maxWidth: 420 }}
        renderInput={(params) => <TextField {...params} label={t('billing.customer')} />}
      />
      {!customer ? <EmptyState description="Select a customer to view the ledger." /> : null}
      {customer && ledger.isLoading ? <LoadingState /> : null}
      {ledger.isError ? (
        <ErrorState message={ledger.error.message} onRetry={() => void ledger.refetch()} />
      ) : null}
      {ledger.data ? (
        <>
          <Typography>
            Outstanding: <strong>{formatMoney(ledger.data.outstanding)}</strong>
          </Typography>
          {ledger.data.entries.length === 0 ? <EmptyState /> : null}
          {ledger.data.entries.length > 0 ? (
            <Paper sx={{ overflow: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('common.date')}</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>{t('common.number')}</TableCell>
                    <TableCell align="right">Debit</TableCell>
                    <TableCell align="right">Credit</TableCell>
                    <TableCell align="right">Balance</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {ledger.data.entries.map((e, idx) => (
                    <TableRow key={`${e.date}-${e.number}-${idx}`}>
                      <TableCell>{e.date}</TableCell>
                      <TableCell>{e.type}</TableCell>
                      <TableCell>{e.number ?? '—'}</TableCell>
                      <TableCell align="right">{formatMoney(e.debit)}</TableCell>
                      <TableCell align="right">{formatMoney(e.credit)}</TableCell>
                      <TableCell align="right">{formatMoney(e.balance)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
