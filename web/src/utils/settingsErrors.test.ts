import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { AxiosError } from 'axios';
import { describe, expect, it } from 'vitest';
import { en } from '@/i18n/en';
import { hi } from '@/i18n/hi';
import { SETTINGS_ERROR_CODES, settingsErrorAdvice, settingsErrorText } from '@/utils/settingsErrors';

type Entry = { cause?: string; fix?: string };
const catalogue = (cat: unknown) => (cat as { settingsErrors: Record<string, Entry | string> }).settingsErrors;

function axiosError(status: number | undefined, code?: string, message = 'Server said no.') {
  const err = new AxiosError('x');
  if (status !== undefined) {
    err.response = { status, data: { error: { code, message } }, headers: {}, statusText: '', config: {} as never };
  }
  return err;
}

describe('settings error catalogue (SET-14)', () => {
  const backend = readFileSync(resolve(__dirname, '../../../backend/core/settings_codes.py'), 'utf8');
  const backendCodes = [...backend.matchAll(/^\s+"([A-Za-z_]+)",$/gm)].map((m) => m[1]);

  it('lists exactly the codes the backend raises', () => {
    expect([...SETTINGS_ERROR_CODES].sort()).toEqual([...backendCodes].sort());
  });

  it('has a cause and a fix, in English and Hindi, for every code and every status', () => {
    const statusKeys = ['rejected', 'signedOut', 'forbidden', 'notFound', 'conflict', 'tooLarge', 'slowDown', 'server', 'offline'];
    for (const lang of [en, hi]) {
      const cat = catalogue(lang);
      for (const key of [...SETTINGS_ERROR_CODES.map((c) => `code_${c}`), ...statusKeys.map((s) => `status_${s}`)]) {
        const e = cat[key] as Entry;
        expect(e?.cause, key).toBeTruthy();
        expect(e?.fix, key).toBeTruthy();
      }
    }
  });

  it('keeps the Hindi text different from the English text', () => {
    const e = catalogue(en);
    const h = catalogue(hi);
    for (const key of Object.keys(e)) {
      if (typeof e[key] === 'string') continue;
      expect((h[key] as Entry).cause).not.toBe((e[key] as Entry).cause);
    }
  });

  it('explains a coded error by its code', () => {
    const advice = settingsErrorAdvice(axiosError(400, 'LICENCE_LOCKED'));
    expect(advice?.fix).toMatch(/Deactivate it/);
  });

  it('explains any other error by its status', () => {
    expect(settingsErrorAdvice(axiosError(409, 'something_else'))?.cause).toMatch(/changed|state/);
    expect(settingsErrorAdvice(axiosError(403))?.cause).toMatch(/role/);
    expect(settingsErrorAdvice(axiosError(500))?.fix).toMatch(/support/);
    expect(settingsErrorAdvice(axiosError(400, 'validation_error'))?.fix).toMatch(/Check the fields/);
  });

  it('replaces the raw "credentials were not provided" answer with a plain sentence when signed out', () => {
    const text = settingsErrorText(axiosError(401, undefined, 'Authentication credentials were not provided.'));
    expect(text).not.toMatch(/credentials/);
    expect(text).toMatch(/session has ended/);
  });

  it('gives no advice for something that is not an error, and appends the fix to the message', () => {
    expect(settingsErrorAdvice(null)).toBeNull();
    expect(settingsErrorText(axiosError(404))).toMatch(/Go back to the list/);
  });
});
