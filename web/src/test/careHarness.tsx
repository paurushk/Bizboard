/** Shared helpers for the customer care, jobs and contracts page tests. */
import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import axe from 'axe-core';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

/** jsdom has no media queries. This answers min-width / max-width the way MUI asks them. */
export function setViewport(width: number) {
  window.matchMedia = ((query: string) => {
    const min = /min-width:\s*([\d.]+)px/.exec(query);
    const max = /max-width:\s*([\d.]+)px/.exec(query);
    const matches = (min ? width >= Number(min[1]) : true) && (max ? width <= Number(max[1]) : true);
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  }) as typeof window.matchMedia;
}

export function renderRoutes(routes: { path: string; element: ReactElement }[], initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          {routes.map((route) => <Route key={route.path} path={route.path} element={route.element} />)}
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Serious accessibility problems in what is on screen. Colour contrast needs a real browser, so it is skipped here. */
export async function a11yViolations(container: Element): Promise<string[]> {
  const result = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  });
  return result.violations.map((violation) => `${violation.id}: ${violation.nodes.map((n) => n.html).join(' | ').slice(0, 300)}`);
}
