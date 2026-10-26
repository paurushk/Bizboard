import { useQuery } from '@tanstack/react-query';
import { getAccountingSettings } from '@/api/resources';
import { getTodayShift } from '@/pages/pos/posCounterApi';

/**
 * BB-100: the cash till (shifts, opening float, cash drops, close) is a books feature on the
 * server; with books off every till call is refused. False while the setting loads.
 */
export function useTillAvailable(): boolean {
  const settings = useQuery({ queryKey: ['accounting-settings'], queryFn: getAccountingSettings, staleTime: 30_000 });
  return Boolean(settings.data?.accountingEnabled ?? settings.data?.accounting_enabled);
}

export function useTill(terminalId: string, enabled = true) {
  return useQuery({
    queryKey: ['pos-shift-today', terminalId],
    queryFn: () => getTodayShift(terminalId),
    enabled,
  });
}
