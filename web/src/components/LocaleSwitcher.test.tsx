import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LocaleSwitcher } from '@/components/LocaleSwitcher';

const i18n = vi.hoisted(() => {
  const state = { current: 'en', listeners: new Set<() => void>() };
  return {
    state,
    getLocale: () => state.current,
    setLocale: (next: string) => {
      if (next === state.current) return;
      state.current = next;
      state.listeners.forEach((fn) => fn());
    },
    subscribeLocale: (fn: () => void) => {
      state.listeners.add(fn);
      return () => state.listeners.delete(fn);
    },
    t: (key: string) => key,
  };
});

vi.mock('@/i18n', () => ({
  getLocale: i18n.getLocale,
  setLocale: i18n.setLocale,
  subscribeLocale: i18n.subscribeLocale,
  t: i18n.t,
}));

const isSelected = (button: HTMLElement) => button.className.includes('MuiButton-contained');

describe('LocaleSwitcher', () => {
  beforeEach(() => {
    i18n.state.current = 'en';
    i18n.state.listeners.clear();
  });

  it('marks the current language and switches to the other one', async () => {
    render(<LocaleSwitcher />);
    const [english, hindi] = screen.getAllByRole('button');
    expect(isSelected(english)).toBe(true);
    expect(isSelected(hindi)).toBe(false);

    await userEvent.click(hindi);
    expect(i18n.state.current).toBe('hi');
    expect(isSelected(screen.getAllByRole('button')[1])).toBe(true);
  });

  it('follows a language change made elsewhere', () => {
    render(<LocaleSwitcher />);
    act(() => i18n.setLocale('hi'));
    expect(isSelected(screen.getAllByRole('button')[1])).toBe(true);
    expect(isSelected(screen.getAllByRole('button')[0])).toBe(false);
  });

  it('puts a leftover language from an older build back to English, and shows it', () => {
    i18n.state.current = 'ta';
    render(<LocaleSwitcher />);
    expect(i18n.state.current).toBe('en');
    expect(isSelected(screen.getAllByRole('button')[0])).toBe(true);
  });

  it('does not re-announce a language that is already selected', async () => {
    render(<LocaleSwitcher />);
    const listener = vi.fn();
    i18n.state.listeners.add(listener);
    await userEvent.click(screen.getAllByRole('button')[0]);
    expect(listener).not.toHaveBeenCalled();
  });
});
