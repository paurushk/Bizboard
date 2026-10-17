import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { NoteRegisterFilters as ApiFilters } from '@/api/resources';

const DEBOUNCE_MS = 300;

export interface NoteRegisterState {
  search: string;
  status: string;
  dateFrom: string;
  dateTo: string;
}

/** Register filters kept in the URL so refresh and back keep the view (CN-02 / DN-02). */
export function useNoteRegisterFilters() {
  const [params, setParams] = useSearchParams();
  const state: NoteRegisterState = {
    search: params.get('q') ?? '',
    status: params.get('status') ?? '',
    dateFrom: params.get('from') ?? '',
    dateTo: params.get('to') ?? '',
  };
  const [debouncedSearch, setDebouncedSearch] = useState(state.search.trim());
  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedSearch(state.search.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [state.search]);

  const set = (patch: Partial<NoteRegisterState>) => {
    const next = { ...state, ...patch };
    const out = new URLSearchParams();
    if (next.search) out.set('q', next.search);
    if (next.status) out.set('status', next.status);
    if (next.dateFrom) out.set('from', next.dateFrom);
    if (next.dateTo) out.set('to', next.dateTo);
    setParams(out, { replace: true });
  };

  const rangeInvalid = Boolean(state.dateFrom && state.dateTo && state.dateFrom > state.dateTo);
  const apiFilters: ApiFilters = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      status: state.status || undefined,
      // An inverted range is a 400 from the API; do not send it.
      date_from: rangeInvalid ? undefined : state.dateFrom || undefined,
      date_to: rangeInvalid ? undefined : state.dateTo || undefined,
    }),
    [debouncedSearch, state.status, state.dateFrom, state.dateTo, rangeInvalid],
  );
  return { state, set, apiFilters, rangeInvalid };
}

