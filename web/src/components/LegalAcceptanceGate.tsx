import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { acceptLegal, getLegalStatus } from '@/api/auth';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';

/**
 * WP-H5 (DPDP): when the Terms, Privacy Policy or (for an owner) the DPA change version, the
 * person has to accept the new version before carrying on. The server records who accepted which
 * version and when (accounts.LegalAcceptance). The dialog cannot be dismissed.
 */
export function LegalAcceptanceGate() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const status = useQuery({ queryKey: ['legal-status'], queryFn: getLegalStatus, staleTime: 5 * 60 * 1000 });
  const accept = useMutation({
    mutationFn: (docs: string[]) => acceptLegal(docs),
    onSuccess: (data) => queryClient.setQueryData(['legal-status'], data),
    onError: (err) => setError(getErrorMessage(err)),
  });
  const pending = status.data?.pending ?? [];
  if (!pending.length) return null;
  return (
    <Dialog open aria-labelledby="legal-gate-title" disableEscapeKeyDown>
      <DialogTitle id="legal-gate-title">{t('auth.legalTitle')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" gutterBottom>{t('auth.legalBody')}</Typography>
        <ul>
          {pending.map((doc) => (
            <li key={`${doc.document}-${doc.companyId ?? ''}`}>
              <Typography variant="body2">
                {t(`auth.legalDoc_${doc.document}`)} ({doc.version})
              </Typography>
            </li>
          ))}
        </ul>
        {error ? <Alert severity="error">{error}</Alert> : null}
      </DialogContent>
      <DialogActions>
        <Button
          variant="contained"
          disabled={accept.isPending}
          onClick={() => accept.mutate(pending.map((doc) => doc.document))}
        >
          {t('auth.legalAccept')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
