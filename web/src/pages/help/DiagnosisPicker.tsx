import { useEffect, useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { HELP_EVENTS, trackHelpEvent } from './analytics';
import { getHelpIntent } from './intents';
import { IntentBody } from './IntentBody';
import type { HelpContext, HelpDiagnosisLeaf, HelpIntent } from './types';

export function findDiagnosisPath(intent: HelpIntent, leafId: string): HelpDiagnosisLeaf[] {
  const walk = (nodes: HelpDiagnosisLeaf[], trail: HelpDiagnosisLeaf[]): HelpDiagnosisLeaf[] | null => {
    for (const node of nodes) {
      const next = [...trail, node];
      if (node.id === leafId || node.intentId === leafId) return next;
      if (node.children?.length) {
        const found = walk(node.children, next);
        if (found) return found;
      }
    }
    return null;
  };
  return walk(intent.diagnosis ?? [], []) ?? [];
}

export function DiagnosisPicker({
  intent,
  context,
  initialLeafId,
  visited,
}: {
  intent: HelpIntent;
  context?: HelpContext;
  initialLeafId?: string;
  /** F3-053: intentIds already rendered on this recursion path — guards a
   * cross-intent diagnosis cycle (A -> B -> A) authored into intents.ts,
   * which the direct-self-reference check alone doesn't catch. */
  visited?: Set<string>;
}) {
  const seen = visited ?? new Set<string>([intent.intentId]);
  const startPath = useMemo(
    () => (initialLeafId ? findDiagnosisPath(intent, initialLeafId) : []),
    [intent, initialLeafId],
  );
  const [path, setPath] = useState<HelpDiagnosisLeaf[]>(startPath);

  useEffect(() => {
    setPath(startPath);
  }, [startPath]);
  const level = path.length === 0 ? intent.diagnosis ?? [] : path[path.length - 1]?.children ?? [];
  const leaf = path.length ? path[path.length - 1] : null;
  const atLeaf = Boolean(leaf && (!leaf.children || leaf.children.length === 0));

  if (!intent.diagnosis?.length) {
    return <IntentBody intent={intent} context={context} />;
  }

  if (atLeaf && leaf) {
    const target = leaf.intentId ? getHelpIntent(leaf.intentId) : undefined;
    const nestedTree =
      target &&
      !seen.has(target.intentId) &&
      target.type === 6 &&
      (target.diagnosis?.length ?? 0) > 0;
    return (
      <Stack spacing={1.5}>
        <Button size="small" onClick={() => setPath(path.slice(0, -1))}>
          {t('common.back')}
        </Button>
        {nestedTree && target ? (
          <DiagnosisPicker
            intent={target}
            context={context}
            visited={new Set(seen).add(target.intentId)}
          />
        ) : target ? (
          <IntentBody intent={target} context={context} />
        ) : (
          <IntentBody
            intent={intent}
            context={context}
            answer={leaf.answer}
            action={leaf.action}
            resolution={leaf.resolution}
            nextStep={leaf.nextStep}
            hideNextStep={!leaf.nextStep}
          />
        )}
      </Stack>
    );
  }

  const options = path.length === 0 ? intent.diagnosis : level;
  return (
    <Stack spacing={1}>
      {path.length > 0 ? (
        <Button size="small" onClick={() => setPath(path.slice(0, -1))}>
          {t('common.back')}
        </Button>
      ) : (
        <Typography variant="body2">{t('help.whatAreYouSeeing')}</Typography>
      )}
      {options.map((opt) => (
        <Button
          key={opt.id}
          variant="outlined"
          sx={{ justifyContent: 'flex-start', textAlign: 'left', py: 1 }}
          onClick={() => {
            trackHelpEvent(HELP_EVENTS.DIAGNOSIS_BRANCH, { id: intent.intentId, leaf: opt.id });
            setPath([...path, opt]);
          }}
        >
          {opt.symptom}
        </Button>
      ))}
    </Stack>
  );
}
