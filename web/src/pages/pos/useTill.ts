import { useQuery } from '@tanstack/react-query';
import { getTodayShift } from '@/pages/pos/posCounterApi';

export function useTill(terminalId: string) {
  return useQuery({
    queryKey: ['pos-shift-today', terminalId],
    queryFn: () => getTodayShift(terminalId),
  });
}
