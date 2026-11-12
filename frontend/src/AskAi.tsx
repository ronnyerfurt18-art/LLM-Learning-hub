import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import { Button, Icon } from './components';
import { AnswerText, type TutorSource } from './AnswerText';
import { pageUrl, sourceUrl } from './SourceLinks';
import { usePageContext } from './pageContext';
import './ask-ai.css';

type Turn = { role: 'user' | 'assistant'; content: string; sources?: TutorSource[]; notice?: string };
type Entry = Turn | { role: 'divider'; content: string };
type Done = { type: 'done'; answer: string; sources: TutorSource[]; notice: string };
type StreamEvent = { type: 'delta'; text: string } | { type: 'thinking'; text: string } | Done | { type: 'error'; status?: number; detail?: unknown };

const MAX_MESSAGE = 4000;
const MAX_HISTORY = 12;
const MAX_HISTORY_CHARS = 18000;
const TRAINING_STARTS = ['Was fehlt in meiner Antwort?', 'Erklär mir das einfacher.', 'Gib mir ein Beispiel dazu.'];

function history(entries: Entry[]) {
  const start = entries.map(entry => entry.role).lastIndexOf('divider') + 1;
  const turns = entries.slice(start).filter((entry): entry is Turn => entry.role !== 'divider')
    .map(({ role, content }) => ({ role, content: content.slice(0, role === 'user' ? MAX_MESSAGE : 16000) }));
  let kept = turns.slice(-MAX_HISTORY);
  while (kept.length && kept.reduce((sum, turn) => sum + turn.content.length, 0) > MAX_HISTORY_CHARS) kept = kept.slice(2);
  while (kept.length && kept[0].role !== 'user') kept = kept.slice(1);
  return kept;
}

async function detail(response: Response) {
  let value: unknown;
  try { value = (await response.json()).detail; } catch { /* fall back below */ }
  // An older server process does not know the route yet: StaticFiles answers instead of the hub.
  if (response.status === 405 || (response.status === 404 && (value === undefined || value === 'Not Found'))) {
    return 'Der Hub läuft noch mit dem alten Stand. Bitte im Startfenster Ctrl+C drücken und Start.command erneut öffnen.';
  }
  return typeof value === 'string' ? value : `Die Anfrage konnte nicht abgeschlossen werden (${response.status}).`;
}

function openSource(source: TutorSource) {
  const url = source.kind === 'video' ? sourceUrl(source.path, undefined, source.timestamp_seconds)
    : source.pdf_page ? pageUrl(source.path, source.pdf_page) : sourceUrl(source.path);
  window.open(url, '_blank', 'noopener');
}

/** Small chat window on every page: asks the local model about what the page shows. */
export function AskAi({ open, hidden, onOpen, onClose, pageTitle, moduleId }: {
  open: boolean; hidden: boolean; onOpen: () => void; onClose: () => void; pageTitle: string; moduleId: string;
}) {
  const page = usePageContext();
  const context = page || { key: `page:${pageTitle}:${moduleId}`, module_id: moduleId || undefined, title: pageTitle || 'Master Learning Hub', text: '' };
  const [entries, setEntries] = useState<Entry[]>([]);
  const [text, setText] = useState('');
  const [live, setLive] = useState('');
  const [busy, setBusy] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const anchor = useRef('');
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // A new page or question starts a new topic; the earlier turns stay visible but are not sent along.
  useEffect(() => {
    if (anchor.current && anchor.current !== context.key) {
      setEntries(items => items.length && items[items.length - 1].role !== 'divider' ? [...items, { role: 'divider', content: context.title }] : items);
    }
    anchor.current = context.key;
  }, [context.key, context.title]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    fetch('/api/tutor/status').then(response => response.ok ? response.json() : null).then(value => {
      setStatus(value && !value.configured ? value.message || 'Der Lernbegleiter ist nicht eingerichtet.' : '');
    }).catch(() => setStatus(''));
  }, [open]);

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }); }, [entries, live, error, open]);

  useEffect(() => {
    if (!busy) return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const send = async (message = text.trim()) => {
    if (!message || busy) return;
    const past = history(entries);
    setEntries(items => [...items, { role: 'user', content: message }]);
    setText('');
    setLive('');
    setError('');
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    let answer = '';
    try {
      const response = await fetch('/api/tutor/quick/stream', {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history: past, module_id: context.module_id || undefined,
          page: { title: context.title.slice(0, 160), text: context.text.slice(0, 6000) } }),
      });
      if (!response.ok) throw new Error(await detail(response));
      if (!response.body) throw new Error('Dieser Browser kann die Antwort nicht schrittweise empfangen.');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let done: Done | null = null;
      for (;;) {
        const chunk = await reader.read();
        buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true });
        const lines = buffer.split('\n');
        buffer = chunk.done ? '' : lines.pop() ?? '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as StreamEvent;
          if (event.type === 'delta') { answer += event.text; setLive(answer); }
          else if (event.type === 'done') done = event;
          else if (event.type === 'error') throw new Error(typeof event.detail === 'string' ? event.detail : 'Die KI konnte nicht antworten.');
        }
        if (chunk.done) break;
      }
      if (!done) throw new Error('Die Antwort wurde unterbrochen. Bitte erneut senden.');
      const finished = done;
      setEntries(items => [...items, { role: 'assistant', content: finished.answer, sources: finished.sources, notice: finished.notice }]);
    } catch (problem) {
      if (controller.signal.aborted) {
        if (answer.trim()) setEntries(items => [...items, { role: 'assistant', content: `${answer.trim()}\n\n(abgebrochen)` }]);
      } else {
        setError(problem instanceof Error ? problem.message : 'Etwas ist schiefgelaufen. Bitte versuche es erneut.');
      }
    } finally {
      setLive('');
      setBusy(false);
      abort.current = null;
    }
  };

  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
  };
  const fresh = () => { abort.current?.abort(); setEntries([]); setError(''); setText(''); inputRef.current?.focus(); };
  const topic = history(entries).length === 0;

  if (hidden) return null;
  if (!open) return <button type="button" className="ai-fab" onClick={onOpen} aria-haspopup="dialog" title="KI zu dieser Seite fragen">
    <Icon name="chat" size={14} /><span>KI fragen</span>{busy && <span className="ai-fab-dot" aria-label="antwortet" />}
  </button>;

  return <section className="ai-chat" role="dialog" aria-label="KI fragen" aria-modal="false" onKeyDown={event => { if (event.key === 'Escape') onClose(); }}>
    <header className="ai-chat-head">
      <div><strong>KI fragen</strong><small title={context.title}>Bezug: {context.title}</small></div>
      <span className="ai-chat-tools">
        <button type="button" className="link-button" onClick={fresh} disabled={!entries.length && !busy}>Neu</button>
        <button type="button" className="icon-button" onClick={onClose} aria-label="KI-Fenster schließen"><Icon name="close" size={15} /></button>
      </span>
    </header>
    <div className="ai-chat-body" aria-live="polite">
      {!entries.length && !busy && <p className="ai-chat-hint">{page
        ? 'Ich sehe die aktuelle Aufgabe, deine Antwort und – nach dem Aufdecken – die Musterantwort. Frag einfach.'
        : 'Frag kurz nach, was dir auf dieser Seite unklar ist. Für längere Lernsitzungen ist „Mit KI lernen“ da.'}</p>}
      {entries.map((entry, index) => entry.role === 'divider'
        ? <div className="ai-chat-divider" key={index}><span>Neuer Bezug: {entry.content}</span></div>
        : entry.role === 'user'
          ? <div className="ai-bubble me" key={index}>{entry.content}</div>
          : <div className="ai-bubble ai" key={index}>
            <AnswerText text={entry.content} sources={entry.sources || []} onCite={id => { const source = entry.sources?.find(item => item.id === id); if (source) openSource(source); }} />
          </div>)}
      {busy && (live
        ? <div className="ai-bubble ai ai-live">{live}</div>
        : <div className="ai-bubble ai working" role="status"><span className="ai-spinner" aria-hidden="true" /> Liest mit … {seconds} s</div>)}
      {error && <div className="ai-bubble ai bad" role="alert">{error}</div>}
      <div ref={endRef} />
    </div>
    <footer className="ai-chat-foot">
      {status && <p className="ai-chat-problem">{status}</p>}
      {page && topic && !busy && <div className="ai-chat-starts">{TRAINING_STARTS.map(start => <button type="button" key={start} onClick={() => void send(start)} disabled={!!status}>{start}</button>)}</div>}
      <div className="ai-chat-input">
        <textarea ref={inputRef} rows={2} value={text} maxLength={MAX_MESSAGE} onChange={event => setText(event.target.value)} onKeyDown={keyDown}
          placeholder="Deine Frage … (Enter sendet)" aria-label="Deine Frage an die KI" />
        {busy
          ? <Button className="secondary small" onClick={() => abort.current?.abort()}>Stopp</Button>
          : <Button className="small" onClick={() => void send()} disabled={!text.trim() || !!status}><Icon name="arrow" size={14} /></Button>}
      </div>
    </footer>
  </section>;
}
