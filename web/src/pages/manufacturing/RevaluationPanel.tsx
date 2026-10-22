import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  discardRevaluation,
  listRevaluations,
  postRevaluation,
  previewRevaluation,
  reverseRevaluation,
  type Revaluation,
} from '@/api/mfg';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { t } from '@/i18n';
import { ErrorLine, Grid, Pill, ProductPick, Stat, day, money, qty, todayIso, useMfgRights, useRun } from './mfgShared';

/**
 * Re-price the finished stock on hand to the standard cost in force. Preview shows every lot that would change
 * and by how much; nothing moves until it is posted. A posted run is reversed as a whole while the stock has not moved.
 */
export function RevaluationPanel() {
  const qc = useQueryClient();
  const { canPlan, canWork } = useMfgRights();
  const { run, busy, error, code, clear } = useRun();
  const runs = useQuery({ queryKey: ['mfg-revaluations'], queryFn: listRevaluations });
  const [product, setProduct] = useState<number | ''>('');
  const [asOf, setAsOf] = useState(todayIso());
  const [shown, setShown] = useState<number | null>(null);
  const [reverseId, setReverseId] = useState<number | null>(null);
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-revaluations'] });
  const current: Revaluation | undefined = (runs.data ?? []).find((r) => r.id === shown) ?? (runs.data ?? []).find((r) => r.status === 'DRAFT');

  return (
    <Stack spacing={2} sx={{ pt: 2 }}>
      <Typography variant="h6" component="h2">{t('mfg.reval.title')}</Typography>
      <Typography variant="body2" color="text.secondary">{t('mfg.reval.help')}</Typography>
      <ErrorLine error={error ? `${error}${code ? ` (${code})` : ''}` : null} onClose={clear} />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
        <ProductPick label={t('mfg.reval.oneItem')} value={product} onChange={setProduct} />
        <TextField size="small" type="date" label={t('mfg.reval.asOf')} value={asOf} onChange={(e) => setAsOf(e.target.value)} InputLabelProps={{ shrink: true }} />
        <Button
          variant="outlined"
          disabled={!canPlan || busy}
          onClick={async () => {
            const made = await run(() => previewRevaluation({ asOf, product: product === '' ? undefined : product }));
            if (made) {
              setShown(made.id);
              reload();
            }
          }}
        >
          {t('mfg.reval.preview')}
        </Button>
      </Stack>

      {current ? (
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            <Typography variant="subtitle1">
              {current.number || t('mfg.reval.preview')} · {day(current.asOf)}
            </Typography>
            <Pill value={current.status} />
            <Stat label={t('mfg.reval.before')} value={money(current.totalBefore)} />
            <Stat label={t('mfg.reval.after')} value={money(current.totalAfter)} />
            <Stat label={t('mfg.reval.change')} value={money(current.totalChange)} tone={Number(current.totalChange) < 0 ? 'warn' : undefined} />
          </Stack>
          {current.lines.length === 0 ? <Alert severity="info">{t('mfg.reval.nothing')}</Alert> : null}
          <Grid
            rows={current.lines}
            rowKey={(l) => l.id}
            cols={[
              { key: 'p', label: t('mfg.common.item'), render: (l) => l.productName },
              { key: 'w', label: t('mfg.common.warehouse'), render: (l) => l.warehouseName },
              { key: 'b', label: t('mfg.common.batchNo'), render: (l) => l.batchNo ?? '—' },
              { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (l) => qty(l.qty) },
              { key: 'o', label: t('mfg.reval.oldCost'), align: 'right', render: (l) => money(l.oldUnitCost) },
              { key: 'n', label: t('mfg.reval.newCost'), align: 'right', render: (l) => money(l.newUnitCost) },
              { key: 'c', label: t('mfg.reval.change'), align: 'right', render: (l) => money(l.change) },
            ]}
          />
          {current.status === 'DRAFT' ? (
            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                disabled={!canPlan || busy || current.lines.length === 0}
                onClick={async () => {
                  if (await run(() => postRevaluation(current.id))) {
                    setShown(current.id);
                    reload();
                  }
                }}
              >
                {t('mfg.reval.post')}
              </Button>
              <Button
                color="warning"
                disabled={!canWork || busy}
                onClick={async () => {
                  if (await run(() => discardRevaluation(current.id))) {
                    setShown(null);
                    reload();
                  }
                }}
              >
                {t('mfg.common.discard')}
              </Button>
            </Stack>
          ) : null}
        </Stack>
      ) : null}

      <Typography variant="subtitle2">{t('mfg.reval.history')}</Typography>
      <Grid
        query={runs}
        rows={(runs.data ?? []).filter((r) => r.status !== 'DRAFT')}
        rowKey={(r) => r.id}
        empty={t('mfg.common.nothingYet')}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'd', label: t('mfg.reval.asOf'), render: (r) => day(r.asOf) },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          { key: 'c', label: t('mfg.reval.change'), align: 'right', render: (r) => money(r.totalChange) },
          {
            key: 'a',
            label: '',
            render: (r) => (
              <Stack direction="row" spacing={1}>
                <Button size="small" onClick={() => setShown(r.id)}>{t('mfg.reval.view')}</Button>
                {r.status === 'POSTED' ? <Button size="small" color="warning" disabled={!canPlan || busy} onClick={() => setReverseId(r.id)}>{t('mfg.common.reverse')}</Button> : null}
              </Stack>
            ),
          },
        ]}
      />
      <ConfirmDialog
        open={reverseId !== null}
        title={t('mfg.common.reverseTitle')}
        body={t('mfg.reval.reverseBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setReverseId(null)}
        onConfirm={(reason) => {
          const id = reverseId!;
          setReverseId(null);
          void run(() => reverseRevaluation(id, reason)).then(reload);
        }}
      />
    </Stack>
  );
}
