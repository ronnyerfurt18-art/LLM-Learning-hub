import { useEffect, useSyncExternalStore } from 'react';

/** What the visible page shows, for the "KI fragen" window. Data only; the server bounds and frames it. */
export type PageContext = { key: string; module_id?: string; title: string; text: string };

let current: PageContext | null = null;
const listeners = new Set<() => void>();

export function setPageContext(value: PageContext | null) {
  current = value;
  listeners.forEach(listener => listener());
}

export function usePageContext() {
  return useSyncExternalStore(listener => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, () => current);
}

/** A page reports its details while it is visible and withdraws them when it leaves. */
export function usePageDetail(value: PageContext | null) {
  const serialized = value ? JSON.stringify(value) : '';
  useEffect(() => {
    setPageContext(serialized ? JSON.parse(serialized) as PageContext : null);
  }, [serialized]);
  useEffect(() => () => setPageContext(null), []);
}
