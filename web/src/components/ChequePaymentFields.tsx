import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { getErrorMessage } from '@/api/client';
import { uploadFile } from '@/api/resources';
import { t } from '@/i18n';

export type ChequePaymentValues = {
  chequeNumber: string;
  chequeBankName: string;
  chequeDate: string;
  chequeImage?: number | null;
};

type Props = {
  value: ChequePaymentValues;
  onChange: (next: ChequePaymentValues) => void;
  disabled?: boolean;
};

export function ChequePaymentFields({ value, onChange, disabled }: Props) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileName, setFileName] = useState('');
  const set = (patch: Partial<ChequePaymentValues>) => onChange({ ...value, ...patch });

  return (
    <Stack spacing={1}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
        <TextField
          size="small"
          required
          label={t('billing.chequeNumber')}
          value={value.chequeNumber}
          onChange={(e) => set({ chequeNumber: e.target.value })}
          disabled={disabled}
          sx={{ minWidth: 140 }}
        />
        <TextField
          size="small"
          required
          label={t('billing.chequeBank')}
          value={value.chequeBankName}
          onChange={(e) => set({ chequeBankName: e.target.value })}
          disabled={disabled}
          sx={{ minWidth: 160 }}
        />
        <TextField
          size="small"
          type="date"
          label={t('billing.chequeDate')}
          InputLabelProps={{ shrink: true }}
          value={value.chequeDate}
          onChange={(e) => set({ chequeDate: e.target.value })}
          disabled={disabled}
          sx={{ minWidth: 160 }}
        />
        <Button
          component="label"
          size="small"
          variant="outlined"
          disabled={disabled || uploading}
          sx={{ alignSelf: 'center' }}
        >
          {value.chequeImage ? t('billing.chequeImageAttached') : t('billing.chequeImage')}
          <input
            type="file"
            hidden
            accept="image/*,.pdf"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = '';
              if (!file) return;
              setUploading(true);
              setUploadError(null);
              void uploadFile(file, 'ATTACHMENT')
                .then((uploaded) => {
                  set({ chequeImage: uploaded.id });
                  setFileName(file.name);
                })
                .catch((err) => setUploadError(getErrorMessage(err)))
                .finally(() => setUploading(false));
            }}
          />
        </Button>
      </Stack>
      {fileName ? (
        <Typography variant="caption" color="text.secondary">
          {fileName}
        </Typography>
      ) : null}
      {uploadError ? (
        <Typography variant="caption" color="error">
          {uploadError}
        </Typography>
      ) : null}
    </Stack>
  );
}
