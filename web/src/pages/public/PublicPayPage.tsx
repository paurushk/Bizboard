import Alert from '@mui/material/Alert';

import Box from '@mui/material/Box';

import Button from '@mui/material/Button';

import Card from '@mui/material/Card';

import CardContent from '@mui/material/CardContent';

import CircularProgress from '@mui/material/CircularProgress';

import Fade from '@mui/material/Fade';

import Stack from '@mui/material/Stack';

import Typography from '@mui/material/Typography';

import { useQuery } from '@tanstack/react-query';

import { useParams } from 'react-router-dom';

import { getPublicPaymentLink } from '@/api/resources';

import { formatMoney } from '@/utils/money';

import { isAllowedPaymentUrl } from '@/utils/safeUrl';



export function PublicPayPage() {

  const { token = '' } = useParams();

  const query = useQuery({

    queryKey: ['public-pay', token],

    queryFn: () => getPublicPaymentLink(token),

    retry: false,

  });



  if (query.isLoading) {

    return (

      <Stack minHeight="100vh" alignItems="center" justifyContent="center" sx={{ bgcolor: 'grey.50' }}>

        <CircularProgress />

      </Stack>

    );

  }



  if (query.isError) {
    return (
      <Stack minHeight="100vh" p={2} alignItems="center" justifyContent="center" sx={{ bgcolor: 'grey.50' }}>
        <Card sx={{ maxWidth: 480, width: '100%', p: 2, textAlign: 'center' }}>
          <CardContent>
            <Typography variant="h5" color="error" gutterBottom fontWeight={600}>
              Payment Link Unavailable
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
              This invoice payment link has expired or is invalid. Please contact the business for an updated payment link.
            </Typography>
            <Button variant="outlined" onClick={() => void query.refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </Stack>
    );
  }



  const pay = query.data!;

  const upi = (pay.upi || {}) as Record<string, unknown>;

  const intentUrl = String(upi.intentUrl || upi.intent_url || upi.uri || '');

  const providerShortUrl = pay.providerShortUrl ? String(pay.providerShortUrl) : '';

  const safeProviderUrl = providerShortUrl && isAllowedPaymentUrl(providerShortUrl) ? providerShortUrl : '';

  const safeIntentUrl = intentUrl && isAllowedPaymentUrl(intentUrl) ? intentUrl : '';

  const paid =
    Boolean(pay.paid) ||
    String(pay.paymentState || pay.payment_state || '').toUpperCase() === 'PAID' ||
    String(pay.paymentState || pay.payment_state || '').toUpperCase() === 'PAID_PENDING_BOOKS';



  return (

    <Box

      minHeight="100vh"

      sx={{

        bgcolor: 'grey.100',

        backgroundImage: 'radial-gradient(circle at top, rgba(25,118,210,0.08), transparent 55%)',

        p: 2,

        display: 'flex',

        alignItems: 'center',

        justifyContent: 'center',

      }}

    >

      <Fade in>

        <Card sx={{ width: '100%', maxWidth: 440, borderRadius: 3, boxShadow: 3 }}>

          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>

            <Stack spacing={2.5}>

              <Box textAlign="center">

                <Typography variant="overline" color="text.secondary">

                  Secure payment

                </Typography>

                <Typography variant="h5" fontWeight={700}>

                  {String(pay.companyName || 'BizBoard')}

                </Typography>

                <Typography variant="body2" color="text.secondary">

                  {pay.invoiceNumber ? `Invoice ${String(pay.invoiceNumber)}` : 'Payment request'}

                  {pay.customerName ? ` · ${String(pay.customerName)}` : ''}

                </Typography>

              </Box>



              <Typography variant="h3" textAlign="center" fontWeight={700}>

                {formatMoney(pay.amount as string | number)}

              </Typography>



              {paid ? (

                <Alert severity="success">Payment received. You can close this page.</Alert>

              ) : (

                <>

                  <Alert severity="info">Pay with UPI or the hosted checkout. Do not share OTPs or card details in chat.</Alert>

                  {safeProviderUrl ? (

                    <Button size="large" variant="contained" href={safeProviderUrl} fullWidth>

                      Pay online

                    </Button>

                  ) : null}

                  {safeIntentUrl ? (

                    <Button size="large" variant="outlined" href={safeIntentUrl} fullWidth>

                      Open UPI app

                    </Button>

                  ) : null}

                  {!safeProviderUrl && !safeIntentUrl ? (

                    <Alert severity="warning">Payment options are not configured for this business yet.</Alert>

                  ) : null}

                </>

              )}



              <Typography variant="caption" textAlign="center" color="text.secondary">

                Powered by BizBoard · Status: {String(pay.status)}

              </Typography>

            </Stack>

          </CardContent>

        </Card>

      </Fade>

    </Box>

  );

}


