import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { openAuthenticatedFile, voidImport } from '@/api/resources';
import { t } from '@/i18n';

type Props = {
  /** Where the upload screen lives, so Undo can return to it. */
  uploadPath: string;
  /** Bill number printed on the source bill (shown as the source reference). */
  reference?: string;
  /** API path that serves the uploaded bill for anyone who may open the invoice. */
  sourceBillPath?: string | null;
  /** True when the invoice has an uploaded bill attached. */
  hasSourceBill?: boolean;
  /** Lines kept below the customer's price list because that is what the bill printed. */
  belowListLines?: number;
  /** Present only straight after the commit; enables Undo. */
  importJobId?: number | null;
  /** Products the import created that have no cost or stock yet. */
  productsCreated?: number;
  isDraft: boolean;
};

/**
 * What an editor opened from a bill upload should tell the reviewer: which bill
 * it came from (and a way to see it), that auto-created items still need
 * cost/stock, and a way to undo the whole import while it is still a draft.
 */
export function ImportedBillNotice({
  uploadPath,
  reference,
  sourceBillPath,
  hasSourceBill,
  belowListLines = 0,
  importJobId,
  productsCreated = 0,
  isDraft,
}: Props) {
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const undo = useMutation({
    mutationFn: () => voidImport(importJobId!),
    onSuccess: () => {
      setConfirm(false);
      void navigate(`${uploadPath}?job=${importJobId}`);
    },
    onError: (err) => {
      setConfirm(false);
      setError(getErrorMessage(err));
    },
  });
  if (!reference && !hasSourceBill && !importJobId && productsCreated <= 0 && belowListLines <= 0) return null;
  return (
    <Stack spacing={1}>
      {reference || hasSourceBill ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          {reference ? (
            <Typography variant="body2">
              {t('billUpload.sourceBillRef')} {reference}
            </Typography>
          ) : null}
          {hasSourceBill && sourceBillPath ? (
            <Button size="small" onClick={() => void openAuthenticatedFile(sourceBillPath)}>
              {t('billUpload.originalBill')}
            </Button>
          ) : null}
          {importJobId && isDraft ? (
            <Button size="small" color="inherit" onClick={() => setConfirm(true)}>
              {t('billUpload.undoImport')}
            </Button>
          ) : null}
        </Stack>
      ) : null}
      {productsCreated > 0 ? (
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" component={RouterLink} to="/inventory/products?needsReview=1">
              {t('billUpload.reviewProducts')}
            </Button>
          }
        >
          {t('billUpload.importedProductsReview', { count: productsCreated })}
        </Alert>
      ) : null}
      {belowListLines > 0 ? (
        <Alert severity="info">{t('billUpload.belowListLines', { count: belowListLines })}</Alert>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Dialog open={confirm} onClose={() => setConfirm(false)}>
        <DialogTitle>{t('billUpload.undoImportTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('billUpload.undoImportBody')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(false)}>{t('common.cancel')}</Button>
          <Button color="error" disabled={undo.isPending} onClick={() => undo.mutate()}>
            {t('billUpload.undoImport')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
