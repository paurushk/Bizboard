import { MutationCache, QueryClient } from '@tanstack/react-query';
import { invalidateMoney } from '@/lib/moneyInvalidate';

/**
 * The app's query client. Any successful write may move money (a receipt, a void, a cheque
 * status, a promise), so the Money hub and the screens that foot to it refetch instead of
 * showing yesterday's number.
 */
export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    mutationCache: new MutationCache({ onSuccess: () => invalidateMoney(client) }),
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  });
  return client;
}
