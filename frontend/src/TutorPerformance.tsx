export type TutorPerformanceData = {
  provider: string; model: string;
  first_token_seconds?: number | null; ttft_seconds?: number | null;
  total_seconds?: number | null; context_seconds?: number | null;
  load_seconds?: number | null; prefill_seconds?: number | null;
  cache_ratio?: number | null; decode_tokens_per_second?: number | null;
  prompt_tokens?: number | null; cached_tokens?: number | null;
  new_prompt_tokens?: number | null; output_tokens?: number | null;
  memory?: { model_bytes?: number | null; peak_bytes?: number | null; pressure_level?: number | null; swap_used_bytes?: number | null };
};

const measured = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const format = (value: number | null | undefined, unit = '', digits = 1) => measured(value)
  ? `${value.toLocaleString('de-DE', { maximumFractionDigits: digits })}${unit}` : 'nicht verfügbar';
const memory = (value?: number | null) => format(measured(value) ? value / 1024 ** 3 : null, ' GiB');

/** Provider measurements never stand in for browser arrival or paint timing. */
export function TutorPerformance({ data, arrival }: { data?: TutorPerformanceData | null; arrival?: number }) {
  if (!data) return null;
  const pressure = data.memory?.pressure_level;
  const rows = [
    ['Modell', `${data.model} (${data.provider})`],
    ['Erster Antworttext im Browser', format(arrival, ' s')],
    ['Erster Antworttext im Hub (TTFT)', format(data.ttft_seconds, ' s')],
    ['Prefill', format(data.prefill_seconds, ' s')],
    ['Prompt-Cache', format(measured(data.cache_ratio) && data.cache_ratio <= 1 ? data.cache_ratio * 100 : null, ' %')],
    ['Antwortgeschwindigkeit', format(data.decode_tokens_per_second, ' Tokens/s')],
  ];
  const detail = [
    ['Erstes Token im Hub (inkl. Nachdenken)', format(data.first_token_seconds, ' s')],
    ['Modell laden', format(data.load_seconds, ' s')],
    ['Kontextaufbau', format(data.context_seconds, ' s')],
    ['Gesamt im Hub ab Modellprüfung', format(data.total_seconds, ' s')],
    ['Eingabe-Tokens', format(data.prompt_tokens, '', 0)],
    ['Wiederverwendete Tokens', format(data.cached_tokens, '', 0)],
    ['Neu verarbeitete Tokens', format(data.new_prompt_tokens, '', 0)],
    ['Ausgabe-Tokens (inkl. Nachdenken)', format(data.output_tokens, '', 0)],
    ['Modellbelegung laut Laufzeit', memory(data.memory?.model_bytes)],
    ['Laufzeit-Speicherspitze', memory(data.memory?.peak_bytes)],
    ['System-Swap nach Antwort', memory(data.memory?.swap_used_bytes)],
    ['System-Speicherdruck nach Antwort', pressure === 1 ? 'normal' : pressure === 2 ? 'erhöht' : pressure === 4 ? 'kritisch' : 'nicht verfügbar'],
  ];
  const table = (items: string[][]) => <dl className="tutor-performance-values">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
  return <details className="tutor-answer-sources tutor-performance">
    <summary>Performance dieser Antwort</summary>
    {table(rows)}
    <details><summary>Technische Messdetails</summary>{table(detail)}
      <p className="tutor-notice">Browserzeit: Eingang des ersten Antworttexts, vor der Bildschirmdarstellung. Hubzeit: ab Modellprüfung, ohne Kontextaufbau. Fehlende Messwerte werden nicht geschätzt. Speicherwerte beschreiben den Zustand nach der Antwort.</p>
    </details>
  </details>;
}
