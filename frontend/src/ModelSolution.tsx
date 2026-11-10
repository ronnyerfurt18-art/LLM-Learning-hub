import { useEffect, useRef, useState } from 'react';
import { api, errorText, formatDate, query } from './api';
import { AnswerText, citedIds, sourcePosition, type TutorSource } from './AnswerText';
import { SourceDocumentLink } from './SourceLinks';

type Excerpt = { pdf_page: number; text: string };
type WikiEntry = {
  id: string; goal_id: string; version: number; status: 'draft' | 'reviewed'; status_label: string; answer: string;
  sources: TutorSource[]; excerpts: Record<string, Excerpt[]>; provider: string; model: string; thinking: boolean;
  created_at: string; duration_seconds: number; improve_note: string;
};
type WikiVersion = { id: string; version: number; status: string; model: string; thinking: number; created_at: string };
type WikiResponse = { entry: WikiEntry | null; versions: WikiVersion[]; stale: boolean };
type StreamEvent = { type: 'delta'; text: string } | { type: 'thinking'; text: string }
  | { type: 'done'; entry: WikiEntry } | { type: 'error'; status?: number; detail?: unknown };
type Phase = '' | 'reading' | 'thinking' | 'writing';

/** NDJSON stream of /api/tutor/wiki/generate/stream; returns the stored wiki entry. */
async function streamSolution(body: Record<string, unknown>, signal: AbortSignal, onEvent: (kind: 'thinking' | 'delta', text: string) => void): Promise<WikiEntry> {
  const response = await fetch('/api/tutor/wiki/generate/stream', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `Die Anfrage konnte nicht abgeschlossen werden (${response.status}).`;
    try { const detail = (await response.json()).detail; if (typeof detail === 'string') message = detail; } catch { /* fallback */ }
    throw new Error(message);
  }
  if (!response.body) throw new Error('Dieser Browser kann die Antwort nicht schrittweise empfangen.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let entry: WikiEntry | null = null;
  try {
    for (;;) {
      const chunk = await reader.read();
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split('\n');
      buffer = chunk.done ? '' : lines.pop() ?? '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as StreamEvent;
        if (event.type === 'delta' || event.type === 'thinking') onEvent(event.type, event.text);
        else if (event.type === 'done') entry = event.entry;
        else throw new Error(typeof event.detail === 'string' ? event.detail : 'Die Musterlösung konnte nicht erstellt werden.');
      }
      if (chunk.done) break;
    }
  } catch (error) {
    void reader.cancel().catch(() => undefined);
    throw error;
  }
  if (!entry) throw new Error('Die Erstellung wurde unterbrochen. Bitte erneut versuchen.');
  return entry;
}

/** Lernwiki: Musterlösung je Lernziel – erst selbst versuchen, dann vergleichen; gespeicherte
 * Versionen erscheinen sofort ohne neue Modellanfrage. */
export function ModelSolution({ moduleId, goalId, disabled }: { moduleId: string; goalId: string; disabled: boolean }) {
  const [data, setData] = useState<WikiResponse | null>(null);
  const [error, setError] = useState('');
  const [phase, setPhase] = useState<Phase>('');
  const [partial, setPartial] = useState('');
  const [thoughtWords, setThoughtWords] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [think, setThink] = useState(false);
  const [thinkingAvailable, setThinkingAvailable] = useState(false);
  const [improve, setImprove] = useState('');
  const [openSources, setOpenSources] = useState<string[]>([]);
  const controller = useRef<AbortController | null>(null);
  const busy = phase !== '';

  useEffect(() => {
    let active = true;
    api<{ thinking?: boolean }>('/tutor/status').then(status => { if (active) setThinkingAvailable(!!status.thinking); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    setData(null); setError(''); setImprove(''); setOpenSources([]);
    api<WikiResponse>(`/tutor/wiki${query({ module_id: moduleId, goal_id: goalId })}`)
      .then(result => { if (active) setData(result); }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; controller.current?.abort(); };
  }, [moduleId, goalId]);
  useEffect(() => {
    if (!busy) return;
    const started = performance.now();
    const timer = window.setInterval(() => setElapsed((performance.now() - started) / 1000), 500);
    return () => window.clearInterval(timer);
  }, [busy]);

  const loadVersion = async (id: string) => {
    setError('');
    try { setData(await api<WikiResponse>(`/tutor/wiki${query({ module_id: moduleId, goal_id: goalId, id })}`)); }
    catch (e) { setError(errorText(e)); }
  };
  const generate = async (baseId?: string) => {
    const abort = new AbortController();
    controller.current = abort;
    setError(''); setPartial(''); setThoughtWords(0); setElapsed(0); setPhase('reading');
    try {
      const entry = await streamSolution({ module_id: moduleId, goal_id: goalId, ...(think && thinkingAvailable ? { think: true } : {}),
        ...(baseId ? { base_id: baseId, improve: improve.trim() } : {}) }, abort.signal, (kind, text) => {
        if (kind === 'thinking') { setPhase('thinking'); setThoughtWords(words => words + (text.match(/\S+/g)?.length || 0)); }
        else { setPhase('writing'); setPartial(previous => previous + text); }
      });
      setData(await api<WikiResponse>(`/tutor/wiki${query({ module_id: moduleId, goal_id: goalId, id: entry.id })}`));
      setImprove('');
    } catch (e) {
      if (!abort.signal.aborted) setError(errorText(e));
    } finally {
      setPhase(''); setPartial(''); controller.current = null;
    }
  };
  const setStatus = async (entry: WikiEntry, status: 'draft' | 'reviewed') => {
    setError('');
    try {
      const updated = await api<WikiEntry>('/tutor/wiki/status', { module_id: moduleId, goal_id: goalId, id: entry.id, status });
      setData(previous => previous && { ...previous, entry: updated, versions: previous.versions.map(v => v.id === updated.id ? { ...v, status: updated.status } : v) });
    } catch (e) { setError(errorText(e)); }
  };

  const entry = data?.entry || null;
  const cite = (id: string) => {
    setOpenSources(previous => previous.includes(id) ? previous : [...previous, id]);
    requestAnimationFrame(() => document.getElementById(`wiki-${goalId}-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
  };
  const cited = entry ? citedIds(entry.answer).map(id => entry.sources.find(source => source.id === id)).filter((source): source is TutorSource => !!source) : [];
  const phaseText = phase === 'reading' ? 'Lernstoff wird eingelesen' : phase === 'thinking' ? `Das Modell denkt nach (${thoughtWords} Wörter)` : 'Musterlösung wird geschrieben';

  return <details className="model-solution">
    <summary>Musterlösung
      {entry && <span className={`model-solution-badge ${entry.status}`}>{entry.status_label}</span>}
    </summary>
    {!data && !error && <p role="status">Lernwiki wird geprüft …</p>}
    {data && !entry && !busy && <p>Noch keine Musterlösung für dieses Lernziel. Versuch es zuerst selbst – danach vergleichen hilft am meisten.</p>}
    {entry && <p className="tutor-notice">Aus dem Lernwiki · Version {entry.version} · {entry.model}{entry.thinking ? ' mit Nachdenken' : ''} · erstellt {formatDate(entry.created_at)} in {Math.round(entry.duration_seconds)} s{entry.improve_note ? ` · Wunsch: „${entry.improve_note}“` : ''}</p>}
    {data?.stale && <p className="tutor-notice">Lernstoff oder Vorgaben haben sich seit dieser Version geändert. Bei Bedarf neu erstellen.</p>}
    {error && <p role="alert">{error}</p>}

    <div className="button-row">
      {!entry && !busy && <button type="button" className="button small" disabled={disabled || !data} onClick={() => void generate()}>Musterlösung erstellen</button>}
      {busy && <button type="button" className="button secondary small" onClick={() => controller.current?.abort()}>Abbrechen</button>}
      {thinkingAvailable && !busy && <label className="tutor-think-toggle"><input type="checkbox" checked={think} onChange={event => setThink(event.target.checked)} /> Gründlich nachdenken (langsamer)</label>}
    </div>
    {busy && <p role="status"><span className="spinner" /> {phaseText} … {elapsed.toFixed(0)} s</p>}
    {busy && partial && <div className="model-solution-body" aria-busy="true"><AnswerText text={partial} sources={entry?.sources || []} /></div>}

    {entry && !busy && <div className="model-solution-body">
      <AnswerText text={entry.answer} sources={entry.sources} onCite={cite} />
      {cited.length ? <section className="tutor-reading" aria-label="Zum Nachlesen">
        <strong className="tutor-reading-title">Zum Nachlesen</strong>
        {cited.map(source => {
          const parts = entry.excerpts[source.id] || [];
          return <details key={source.id} id={`wiki-${goalId}-${source.id}`} open={openSources.includes(source.id)} onToggle={event => {
            const isOpen = event.currentTarget.open;
            setOpenSources(previous => isOpen ? (previous.includes(source.id) ? previous : [...previous, source.id]) : previous.filter(id => id !== source.id));
          }}>
            <summary><span className="tutor-cite">{source.id}</span> {source.title}{source.chapter ? ` · ${source.chapter}` : ''} · {sourcePosition(source)}</summary>
            {source.kind !== 'video' && <SourceDocumentLink path={source.path} page={source.pdf_page}>Im Original öffnen · PDF-Seite {source.pdf_page}</SourceDocumentLink>}
            {parts.length ? parts.map(part => <blockquote key={part.pdf_page} className="tutor-excerpt"><small>Originalauszug · PDF-Seite {part.pdf_page}</small>{part.text}</blockquote>)
              : <p className="tutor-notice">Für diese Quelle ist kein Originalauszug gespeichert. Bitte im Original nachlesen.</p>}
          </details>;
        })}
      </section> : <p className="tutor-notice">Diese Musterlösung enthält keine Quellenverweise. Bitte anhand der Quellen prüfen.</p>}

      <div className="button-row">
        {entry.status === 'draft'
          ? <button type="button" className="button secondary small" onClick={() => void setStatus(entry, 'reviewed')}>Als von mir geprüft markieren</button>
          : <button type="button" className="text-button" onClick={() => void setStatus(entry, 'draft')}>Wieder als ungeprüft markieren</button>}
        {(data?.versions.length || 0) > 1 && <label>Version<select value={entry.id} onChange={event => void loadVersion(event.target.value)}>
          {data!.versions.map(v => <option key={v.id} value={v.id}>Version {v.version} · {v.status === 'reviewed' ? 'geprüft' : 'Entwurf'} · {formatDate(v.created_at)}</option>)}
        </select></label>}
      </div>
      <details className="model-solution-improve"><summary>Verbessern (neue Version)</summary>
        <label>Was soll besser werden?<textarea value={improve} maxLength={1000} rows={2} onChange={event => setImprove(event.target.value)}
          placeholder="z. B. Kriterium 2 fehlt; kürzer; Beleg zu Schritt 3 prüfen" /></label>
        <button type="button" className="button small" disabled={disabled || !improve.trim()} onClick={() => void generate(entry.id)}>Neue Version erstellen</button>
      </details>
    </div>}
    <p className="tutor-notice">KI-Entwurf: kann Fehler enthalten und ist keine offizielle Lösung. Gespeicherte Musterlösungen ändern deinen Lernstand nicht.</p>
  </details>;
}
