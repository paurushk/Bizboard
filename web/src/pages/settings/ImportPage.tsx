import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Stepper from '@mui/material/Stepper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { commitImport, uploadImport } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { ImportJob, ImportKind } from '@/types/domain';
import { canImport } from '@/utils/permissions';
import { statusLabelKey } from '@/utils/status';

const steps = [t('import.stepUpload'), t('import.stepPreview'), t('import.stepCommit')];

export function ImportPage() {
  const { user } = useAuth();
  const [kind, setKind] = useState<ImportKind>('PRODUCTS');
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose a file');
      return uploadImport(file, kind);
    },
    onSuccess: (data) => {
      setJob(data);
      setActiveStep(1);
      setError(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const commitMutation = useMutation({
    mutationFn: () => {
      if (!job) throw new Error('No import job');
      return commitImport(job.id);
    },
    onSuccess: (data) => {
      setJob(data);
      setActiveStep(2);
      setError(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!canImport(user)) return <Navigate to="/" replace />;

  const previewRows = Array.isArray(job?.preview) ? job!.preview : [];

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('import.title')}</Typography>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Stepper activeStep={activeStep} alternativeLabel>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          <TextField
            select
            label={t('import.entityType')}
            value={kind}
            onChange={(e) => setKind(e.target.value as ImportKind)}
            sx={{ maxWidth: 320 }}
          >
            <MenuItem value="PRODUCTS">Products</MenuItem>
            <MenuItem value="CUSTOMERS">Customers</MenuItem>
            <MenuItem value="SUPPLIERS">Suppliers</MenuItem>
            <MenuItem value="OPENING_STOCK">Opening stock</MenuItem>
          </TextField>

          <Button variant="outlined" component="label" sx={{ alignSelf: 'flex-start' }}>
            {t('import.chooseFile')}
            <input
              hidden
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          {file ? <Typography variant="body2">Selected: {file.name}</Typography> : null}

          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Button
              variant="contained"
              disabled={!file || uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              {t('common.upload')}
            </Button>
            <Button
              variant="contained"
              color="secondary"
              disabled={!job || job.validRows === 0 || commitMutation.isPending || activeStep < 1}
              onClick={() => commitMutation.mutate()}
            >
              {t('common.commit')}
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {job ? (
        <Paper sx={{ p: 2 }}>
          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
            <StatusChip tone="info" labelKey={statusLabelKey(job.status)} />
            <Typography>
              {t('import.validRows')}: {job.validRows} / {job.totalRows}
            </Typography>
            <Typography color="error">
              {t('import.errorRows')}: {job.errorRows}
            </Typography>
          </Stack>

          {previewRows.length > 0 ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Row</TableCell>
                  <TableCell>Data</TableCell>
                  <TableCell>Errors</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {previewRows.map((row, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{(row.rowNumber as number) ?? idx + 1}</TableCell>
                    <TableCell>
                      {row.data
                        ? Object.entries(row.data as Record<string, string>)
                            .map(([k, v]) => `${k}=${v || '∅'}`)
                            .join(', ')
                        : JSON.stringify(row)}
                    </TableCell>
                    <TableCell>
                      {Array.isArray(row.errors) ? row.errors.join('; ') || '—' : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}

          {job.status === 'COMMITTED' ? (
            <Alert severity="success" sx={{ mt: 2 }}>
              Import committed.
            </Alert>
          ) : null}
        </Paper>
      ) : null}
    </Stack>
  );
}
