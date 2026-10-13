import { useCallback, useState } from 'react';

const STORAGE_KEY = 'billUpload.showSource';

/** Whether the original-bill viewer is shown; remembered per browser, wide screens default to on. */
export function useSourceVisibility(): [boolean, (next: boolean) => void] {
  const [show, setShow] = useState(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved != null) return saved === '1';
    } catch {
      /* storage can be unavailable (private mode, blocked site data) */
    }
    return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1200px)').matches
      : false;
  });
  const update = useCallback((next: boolean) => {
    setShow(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, []);
  return [show, update];
}
