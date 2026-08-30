import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ACTIVE_COMPANY_STORAGE_KEY, apiClient, getErrorMessage, unwrapData } from '@/api/client';
import { setAccessToken } from '@/auth/session';
import type { User } from '@/types/domain';

function readActiveCompanyId(): string | null {
  if (typeof localStorage === 'undefined') return null;
  const raw = localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY);
  if (!raw || !/^\d+$/.test(raw)) return null;
  return raw;
}

function persistActiveCompanyId(companyId: number) {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, String(companyId));
  }
}

function restoreActiveCompanyId(previous: string | null) {
  if (typeof localStorage === 'undefined') return;
  if (previous) {
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, previous);
  } else {
    localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY);
  }
}

export interface CompanyMembership {
  companyId: number;
  companyName: string;
  role: string;
  isActiveSelection: boolean;
}

export function useCompanySwitcher(onSwitched?: (user: User) => void) {
  const qc = useQueryClient();
  const [memberships, setMemberships] = useState<CompanyMembership[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const { data } = await apiClient.get('/auth/memberships/');
    const rows = unwrapData<
      Array<{
        companyId?: number;
        company_id?: number;
        companyName?: string;
        company_name?: string;
        role: string;
        isActiveSelection?: boolean;
        is_active_selection?: boolean;
      }>
    >(data);
    const mapped = rows.map((r) => ({
      companyId: Number(r.companyId ?? r.company_id),
      companyName: String(r.companyName ?? r.company_name ?? ''),
      role: r.role,
      isActiveSelection: Boolean(r.isActiveSelection ?? r.is_active_selection),
    }));
    setMemberships(mapped);
    setError(null);
    const active = mapped.find((m) => m.isActiveSelection);
    if (active) {
      persistActiveCompanyId(active.companyId);
    }
  }, []);

  useEffect(() => {
    void refresh().catch((err) => setError(getErrorMessage(err)));
  }, [refresh]);

  const switchCompany = useCallback(
    async (companyId: number) => {
      setLoading(true);
      // BB-000745: do not persist X-Company-Id until switch API succeeds.
      const previousId = readActiveCompanyId();
      try {
        const { data } = await apiClient.post('/auth/switch-company/', { company_id: companyId });
        const body = unwrapData<{ user: User; access?: string | null }>(data);
        if (body.access) setAccessToken(body.access);
        persistActiveCompanyId(companyId);
        qc.clear();
        await refresh();
        onSwitched?.(body.user);
        return body.user;
      } catch (err) {
        restoreActiveCompanyId(previousId);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [onSwitched, qc, refresh],
  );

  return {
    memberships,
    hasMultiple: memberships.length > 1,
    loading,
    error,
    switchCompany,
    refresh,
  };
}
