import { describe, expect, it } from 'vitest';
import { needsBotToken, onBotTokenChange, setBotToken, takeBotToken } from '@/auth/botCheck';

describe('WP-AB2 bot-check token', () => {
  it('rides only on the four pre-login calls', () => {
    expect(needsBotToken('/auth/register/')).toBe(true);
    expect(needsBotToken('/api/v1/auth/otp/request/')).toBe(true);
    expect(needsBotToken('https://api.example.com/api/v1/auth/password/reset/?x=1')).toBe(true);
    expect(needsBotToken('/auth/login/')).toBe(false);
    expect(needsBotToken('/sales/invoices/')).toBe(false);
    expect(needsBotToken(undefined)).toBe(false);
  });

  it('is single-use, and clearing it tells the widget to reset', () => {
    const seen: Array<string | null> = [];
    const off = onBotTokenChange((v) => seen.push(v));
    setBotToken('tok-1');
    expect(takeBotToken()).toBe('tok-1');
    expect(takeBotToken()).toBeNull();
    off();
    expect(seen).toEqual(['tok-1', null]);
  });
});
