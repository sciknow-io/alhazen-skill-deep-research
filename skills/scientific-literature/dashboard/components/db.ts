// Client-side helper for the database the scientific-literature dashboard reads. The choice
// is shared with the hub via localStorage ('alh-db') and can be seeded from a ?db= URL param
// (how the hub hands a selected DB to a skill dashboard). It is appended as ?db=<name> to
// every scilit API call so the whole dashboard reads from one selectable database.

const KEY = 'alh-db';
export const DEFAULT_DB = 'alh_deep_research';

export function getDb(): string {
  if (typeof window === 'undefined') return DEFAULT_DB;
  const fromUrl = new URLSearchParams(window.location.search).get('db');
  if (fromUrl) return fromUrl;
  return window.localStorage.getItem(KEY) || DEFAULT_DB;
}

export function setDb(db: string): void {
  if (typeof window !== 'undefined') window.localStorage.setItem(KEY, db);
}

// Persist a ?db= URL param (from the hub) into localStorage so it survives in-app navigation
// that drops the query string. Call once on mount of a top-level scilit view.
export function syncDbFromUrl(): void {
  if (typeof window === 'undefined') return;
  const fromUrl = new URLSearchParams(window.location.search).get('db');
  if (fromUrl) window.localStorage.setItem(KEY, fromUrl);
}

/** Append the active (or given) db as a query param to an API path. */
export function withDb(path: string, db?: string): string {
  const d = db || getDb();
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}db=${encodeURIComponent(d)}`;
}
