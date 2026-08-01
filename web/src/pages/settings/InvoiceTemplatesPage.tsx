import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canManageUsers } from '@/utils/permissions';

const LAYOUT_LEGEND = [
  'Seller header with GSTIN, phone, and address',
  'TAX INVOICE title with ORIGINAL / DUPLICATE stamp',
  'BILL TO and SHIP TO party blocks',
  'Item table: HSN, Qty, MRP, Rate, Tax, Amount',
  'Tax-by-rate breakup (CGST/SGST or IGST)',
  'UPI QR, terms & conditions, authorized signatory',
];

export function InvoiceTemplatesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [terms, setTerms] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const allowed = canManageUsers(user);

  const query = useQuery({
    queryKey: ['company'],
    queryFn: getCompany,
    enabled: allowed,
  });

  useEffect(() => {
    if (query.data?.invoiceTerms != null) {
      setTerms(query.data.invoiceTerms);
    }
  }, [query.data?.invoiceTerms]);

  const mutation = useMutation({
    mutationFn: () => updateCompany({ invoiceTerms: terms }),
    onSuccess: () => {
      setMessage('Invoice terms saved');
      void qc.invalidateQueries({ queryKey: ['company'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!allowed) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  }
  if (!query.data) return <EmptyState />;

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.invoiceTemplates')}</Typography>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}

      <Paper
        sx={{
          p: 3,
          borderLeft: 4,
          borderColor: 'primary.main',
          background: (theme) =>
            `linear-gradient(135deg, ${theme.palette.primary.main}08 0%, ${theme.palette.background.paper} 55%)`,
        }}
      >
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} justifyContent="space-between">
          <Box>
            <Typography variant="overline" color="primary.main" fontWeight={700}>
              Default template
            </Typography>
            <Typography variant="h5" sx={{ mt: 0.5 }}>
              GST Tax Invoice (A4)
            </Typography>
            <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 480 }}>
              Production layout matching GST tax invoice practice: party blocks, HSN/MRP columns,
              tax-by-rate footer, UPI QR, and amount in words. Used for all completed GST and Tax
              invoices.
            </Typography>
            <Button
              component={RouterLink}
              to="/sales/history"
              variant="outlined"
              sx={{ mt: 2 }}
            >
              Open a completed invoice
            </Button>
          </Box>
          <Box
            sx={{
              minWidth: { md: 220 },
              p: 2,
              borderRadius: 1,
              bgcolor: 'background.default',
              border: 1,
              borderColor: 'divider',
            }}
          >
            <Typography variant="subtitle2" gutterBottom>
              On the PDF
            </Typography>
            <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2 }}>
              {LAYOUT_LEGEND.map((line) => (
                <Typography key={line} component="li" variant="body2" color="text.secondary">
                  {line}
                </Typography>
              ))}
            </Stack>
          </Box>
        </Stack>
      </Paper>

      <Paper sx={{ p: 3 }}>
        <Typography variant="h6">Terms & conditions</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Printed on every invoice PDF. Leave blank to use the system default.
        </Typography>
        <TextField
          label="Invoice terms"
          value={terms}
          onChange={(e) => setTerms(e.target.value)}
          multiline
          minRows={5}
          fullWidth
          placeholder={
            '1. Goods once sold will not be taken back or exchanged.\n2. All disputes are subject to local jurisdiction.'
          }
        />
        <Divider sx={{ my: 2 }} />
        <Button
          variant="contained"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          Save terms
        </Button>
      </Paper>
    </Stack>
  );
}
