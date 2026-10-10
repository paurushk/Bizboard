import { useCallback, useEffect, useRef, useState } from 'react';

/** One success message and one error for a page. A new action clears both, and a
 * success message dismisses itself, so a stale banner never outlives what it described. */
export function useNotices(autoDismissMs = 6000) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setMessage(null);
    setError(null);
  }, []);

  const success = useCallback(
    (text: string) => {
      if (timer.current) clearTimeout(timer.current);
      setError(null);
      setMessage(text);
      timer.current = autoDismissMs > 0 ? setTimeout(() => setMessage(null), autoDismissMs) : null;
    },
    [autoDismissMs],
  );

  const fail = useCallback((text: string) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setMessage(null);
    setError(text);
  }, []);

  useEffect(() => stopTimer, []);

  return { message, error, success, fail, clear };
}
