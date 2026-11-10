export async function api<T = any>(path: string, data?: unknown, method?: string): Promise<T> {
  const response = await fetch(`/api${path}`, {method: method || (data === undefined ? 'GET' : 'POST'), headers: data === undefined ? {} : {'Content-Type':'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  if (!response.ok) {
    let message = `Die Anfrage konnte nicht abgeschlossen werden (${response.status}).`;
    try {const detail = (await response.json()).detail; message = typeof detail === 'string' ? detail : JSON.stringify(detail) || message;} catch {}
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const list = <T,>(value: any, key?: string): T[] => Array.isArray(value) ? value : value?.[key || 'items'] || [];
export function query(values: Record<string, unknown>) {const params = new URLSearchParams(); Object.entries(values).forEach(([key,value]) => {if (value !== '' && value !== undefined && value !== null) params.set(key,String(value));}); return params.toString() ? `?${params}` : '';}
export function formatDate(value?: string | null) {if (!value) return 'Noch nicht geplant'; const date = new Date(value); return isNaN(date.getTime()) ? value : date.toLocaleDateString('de-DE',{day:'numeric',month:'short',year:'numeric'});}
export const percent = (value: number | undefined) => `${Math.round(value || 0)} %`;
export const errorText = (error: unknown) => error instanceof Error ? error.message : 'Etwas ist schiefgelaufen. Bitte versuche es erneut.';
