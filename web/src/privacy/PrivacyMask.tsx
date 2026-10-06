import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

const STORAGE_KEY = 'bb_privacy_mask';

type PrivacyMaskValue = {
  privacyMask: boolean;
  togglePrivacyMask: () => void;
};

const PrivacyMaskContext = createContext<PrivacyMaskValue | null>(null);

export function PrivacyMaskProvider({ children }: { children: ReactNode }) {
  const [privacyMask, setPrivacyMask] = useState(() => {
    try {
      return sessionStorage.getItem(STORAGE_KEY) === '1';
    } catch {
      return false; // storage blocked (private mode, blocked site data): start unmasked, never crash
    }
  });
  const togglePrivacyMask = useCallback(() => {
    setPrivacyMask((on) => {
      const next = !on;
      try {
        sessionStorage.setItem(STORAGE_KEY, next ? '1' : '0');
      } catch {
        // keep the toggle working for this tab even when it cannot be remembered
      }
      return next;
    });
  }, []);
  const value = useMemo(() => ({ privacyMask, togglePrivacyMask }), [privacyMask, togglePrivacyMask]);
  return <PrivacyMaskContext.Provider value={value}>{children}</PrivacyMaskContext.Provider>;
}

export function usePrivacyMask(): PrivacyMaskValue {
  const ctx = useContext(PrivacyMaskContext);
  if (!ctx) throw new Error('usePrivacyMask must be used within PrivacyMaskProvider');
  return ctx;
}

export function usePrivacyMaskOptional(): PrivacyMaskValue {
  return useContext(PrivacyMaskContext) ?? { privacyMask: false, togglePrivacyMask: () => undefined };
}
