// WP-8 (bundle budget): the help catalogue (~50 KB gzip) is its own chunk, fetched once the first
// time a page with a `?` renders (ContextHelp). Until then the button is simply not shown.
export type ContextHelpCatalog = typeof import('./catalog');

let catalogModule: ContextHelpCatalog | null = null;
let catalogPromise: Promise<ContextHelpCatalog> | null = null;

export function loadedContextHelpCatalog(): ContextHelpCatalog | null {
  return catalogModule;
}

export function loadContextHelpCatalog(): Promise<ContextHelpCatalog> {
  catalogPromise ??= import('./catalog').then((m) => {
    catalogModule = m;
    return m;
  });
  return catalogPromise;
}
