import { useRef, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient, getErrorMessage, unwrapData } from '@/api/client';
import type { AttachmentRow } from '@/api/care';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { t } from '@/i18n';

type FileMeta = { id: number; url: string; originalName: string; contentType: string; size: number };

function useFileMeta(id: number) {
  return useQuery({
    queryKey: ['care-file', id],
    queryFn: async () => unwrapData<FileMeta>((await apiClient.get(`/files/${id}/`)).data),
    staleTime: 5 * 60_000,
  });
}

function FileRow({ row, canEdit, onRemove }: { row: AttachmentRow; canEdit: boolean; onRemove: () => void }) {
  const meta = useFileMeta(row.file);
  const file = meta.data;
  const isImage = Boolean(file?.contentType?.startsWith('image/'));
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      {isImage && file ? (
        <Box component="img" src={file.url} alt="" sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 0.5 }} />
      ) : null}
      {file ? (
        <Link href={file.url} target="_blank" rel="noopener noreferrer" underline="hover" sx={{ wordBreak: 'break-all' }}>
          {file.originalName || t('care.files.file', { id: row.file })}
        </Link>
      ) : (
        <Typography variant="body2">{t('care.files.file', { id: row.file })}</Typography>
      )}
      {canEdit ? (
        <Button size="small" color="error" onClick={onRemove} aria-label={t('care.files.removeNamed', { name: file?.originalName ?? `#${row.file}` })}>
          {t('care.files.remove')}
        </Button>
      ) : null}
    </Stack>
  );
}

/** Files on a record. When the record is finished the buttons are replaced by a plain note (FND-14). */
export function AttachmentPanel({
  queryKey,
  list,
  upload,
  remove,
  canEdit,
  lockedReason,
}: {
  queryKey: unknown[];
  list: () => Promise<AttachmentRow[]>;
  upload: (file: File) => Promise<unknown>;
  remove: (attachmentId: number) => Promise<unknown>;
  canEdit: boolean;
  lockedReason?: string;
}) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<AttachmentRow | null>(null);
  const [error, setError] = useState('');
  const rows = useQuery({ queryKey, queryFn: list });
  const refresh = () => qc.invalidateQueries({ queryKey });
  const add = useMutation({
    mutationFn: (file: File) => upload(file),
    onSuccess: () => { setError(''); void refresh(); },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const del = useMutation({
    mutationFn: (attachmentId: number) => remove(attachmentId),
    onSuccess: () => { setError(''); void refresh(); },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const editable = canEdit && !lockedReason;
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2" component="h3">{t('care.files.title')}</Typography>
      {lockedReason ? <Typography variant="caption" color="text.secondary">{lockedReason}</Typography> : null}
      {rows.isError ? <Typography variant="body2" color="error">{getErrorMessage(rows.error)}</Typography> : null}
      {!rows.isLoading && (rows.data ?? []).length === 0 ? (
        <Typography variant="body2" color="text.secondary">{t('care.files.none')}</Typography>
      ) : null}
      {(rows.data ?? []).map((row) => (
        <FileRow key={row.id} row={row} canEdit={editable} onRemove={() => setPending(row)} />
      ))}
      {editable ? (
        <>
          <Typography variant="caption" color="text.secondary">{t('growth.attachmentHint')}</Typography>
          <Button size="small" variant="outlined" sx={{ alignSelf: 'flex-start' }} disabled={add.isPending} onClick={() => input.current?.click()}>
            {t('care.files.upload')}
          </Button>
          <input
            ref={input}
            hidden
            type="file"
            aria-label={t('care.files.upload')}
            accept="image/jpeg,image/png,image/webp,application/pdf"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) add.mutate(file);
              event.target.value = '';
            }}
          />
        </>
      ) : null}
      {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
      <ConfirmDialog
        open={pending != null}
        title={t('care.files.removeTitle')}
        body={t('care.files.removeBody')}
        confirmLabel={t('care.files.remove')}
        confirmColor="error"
        onClose={() => setPending(null)}
        onConfirm={() => {
          if (pending) del.mutate(pending.id);
          setPending(null);
        }}
      />
    </Stack>
  );
}
