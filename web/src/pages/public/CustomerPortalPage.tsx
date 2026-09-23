import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { downloadCustomerPortalInvoice, getCustomerPortal, startCustomerPortalPayment } from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { triggerBlobDownload } from '@/utils/blob';
import { safeAppPath } from '@/utils/safeUrl';

// F1-008: payPath is server-generated today (always `/pay/{token}`), but this
// page must not rely on that staying true — every backend-sourced path gets
// validated the same way PublicPayPage.tsx validates its own URLs, rather
// than trusting an API response directly in window.location.assign.
function navigateToPayPath(payPath: unknown) {
  const safe = safeAppPath(payPath, '');
  if (safe) {
    window.location.assign(safe);
  }
}

export function CustomerPortalPage() {
  const { token = '' } = useParams();
  const query = useQuery({
    queryKey: ['customer-portal', token],
    queryFn: () => getCustomerPortal(token),
    retry: false,
  });
  const pay = useMutation({
    mutationFn: (invoiceId: number) => startCustomerPortalPayment(token, invoiceId),
    onSuccess: (data) => {
      navigateToPayPath(data.payPath);
    },
  });

  if (query.isLoading) {
    return (
      <Stack minHeight="100vh" alignItems="center" justifyContent="center">
        <CircularProgress aria-label="Loading" />
      </Stack>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Stack minHeight="100vh" p={2} alignItems="center" justifyContent="center">
        <Typography variant="h5" component="h1" color="error">{t('portal.unavailable')}</Typography>
      </Stack>
    );
  }
  const data = query.data;
  return (
    <Stack minHeight="100vh" p={2} alignItems="center" sx={{ bgcolor: 'grey.50' }}>
      <Card sx={{ maxWidth: 640, width: '100%', mt: 4 }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h5" component="h1">{t('portal.title')}</Typography>
            <Typography>{data.customerName}</Typography>
            {data.invoices.length === 0 ? <Typography>{t('portal.empty')}</Typography> : null}
            {data.invoices.map((invoice) => (
              <Stack key={invoice.id} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                <Typography sx={{ flex: 1 }}>
                  {invoice.number} · {invoice.invoiceDate} · {formatMoney(invoice.amount)} · {t('portal.outstanding')} {formatMoney(invoice.outstanding)}
                </Typography>
                <Button
                  size="small"
                  onClick={() => {
                    void downloadCustomerPortalInvoice(token, invoice.id).then((blob) => {
                      triggerBlobDownload(blob, `${invoice.number || invoice.id}.pdf`);
                    });
                  }}
                >
                  {t('portal.download')}
                </Button>
                {Number(invoice.outstanding) > 0 ? (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={pay.isPending}
                    onClick={() => {
                      if (invoice.payPath) {
                        navigateToPayPath(invoice.payPath);
                        return;
                      }
                      pay.mutate(invoice.id);
                    }}
                  >
                    {t('portal.pay')}
                  </Button>
                ) : null}
              </Stack>
            ))}
            {pay.isError ? <Typography color="error">{getErrorMessage(pay.error)}</Typography> : null}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
