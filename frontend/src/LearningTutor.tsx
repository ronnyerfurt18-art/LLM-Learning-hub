import { type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { errorText, query } from './api';
import { Badge, Button, Icon, Loading } from './components';
import { SourceDocumentLink, SourceLinks } from './SourceLinks';
import { LearningPagesPackage, SourceImage, SourceRef } from './types';
import './learning-tutor.css';
import { LearningMemory } from './LearningMemory';
import { ModelSolution } from './ModelSolution';
import { AnswerText, citedIds, sourcePosition } from './AnswerText';
import { useTutorVoice, VoiceIcon } from './TutorVoice';
import { AnswerReview } from './AnswerReview';
import { SourceImages } from './Learning';

type TutorSource = SourceRef & { id: string };
type Excerpt = { pdf_page: number; text: string };
type ExcerptSpan = { pdf_page: number; start: number; end: number };
/** Curated figure of the selected section; shown under answers citing its sources. */
type TutorFigure = SourceImage & { source_ids: string[] };
type TutorStatus = {
  configured: boolean;
  readiness: 'disabled' | 'configured' | 'starting' | 'ready' | 'error';
  provider: 'none' | 'openai' | 'ollama' | 'bonsai';
  model: string | null;
  data_flow: 'none' | 'local' | 'cloud';
  message: string;
  capabilities: { text: boolean; voice: boolean };
  thinking?: boolean;
};
type TutorContext = {
  module_id: string;
  lesson_id?: string;
  section_id?: string;
  concept_id?: string;
  title: string;
  context_text: string;
  sources: TutorSource[];
  suggestions: string[];
  notice: string;
  instructions?: string;
  context_preamble?: string;
  excerpts?: Record<string, ExcerptSpan[]>;
  figures?: TutorFigure[];
};
export type TutorScope = { module_id: string; lesson_id?: string; section_id?: string; concept_id?: string };
type HistoryItem = { role: 'user' | 'assistant'; content: string };
type Message = HistoryItem & { id: number; sources?: TutorSource[]; excerpts?: Record<string, Excerpt[]>; figures?: TutorFigure[]; notice?: string; responseSeconds?: number; firstTokenSeconds?: number; thinking?: string };
type ChatRequest = TutorScope & { goal_id?: string; message: string; history: HistoryItem[]; think?: boolean };
type ChatResponse = { answer: string; sources: TutorSource[]; provider: string; model: string; notice: string; excerpts?: Record<string, Excerpt[]>; figures?: TutorFigure[] };
type StreamEvent = { type: 'delta'; text: string } | { type: 'thinking'; text: string } | ({ type: 'done' } & ChatResponse) | { type: 'error'; status?: number; detail?: unknown };

const learningStarts = [
  { label: 'Ohne Vorwissen starten', message: 'Ich habe noch kein Vorwissen. Führe mich in das ausgewählte Thema ein: Erkläre zuerst einen grundlegenden Zusammenhang in einfachen Worten, mit einem kurzen Beispiel. Stelle mir danach eine leichte Verständnisfrage und warte auf meine Antwort.' },
  { label: 'An einem Beispiel lernen', message: 'Erarbeite das ausgewählte Thema mit mir an einem konkreten Beispiel. Beginne mit der Ausgangssituation, erkläre den ersten Schritt und lass mich anschließend selbst weiterdenken.' },
  { label: 'Verständnis prüfen', message: 'Prüfe mein Verständnis des ausgewählten Themas. Stelle mir jeweils eine Frage, warte auf meine Antwort und erkläre anschließend anhand der Lerninhalte, was stimmt und was ich noch verbessern kann. Gib mir bei Schwierigkeiten zunächst einen Hinweis.' },
];
const maxMessageLength = 4000;

class TutorRequestError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function tutorRequest<T>(path: string, signal: AbortSignal, body?: unknown): Promise<T> {
  const response = await fetch(`/api/tutor/${path}`, {
    method: body === undefined ? 'GET' : 'POST', signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `Die Anfrage konnte nicht abgeschlossen werden (${response.status}).`;
    try {
      const detail = (await response.json()).detail;
      if (typeof detail === 'string') message = detail;
    } catch { /* The readable fallback also covers non-JSON server errors. */ }
    throw new TutorRequestError(message, response.status);
  }
  return response.json();
}

function parseEvent(line: string): StreamEvent | null {
  if (!line.trim()) return null;
  try { return JSON.parse(line) as StreamEvent; }
  catch { throw new TutorRequestError('Die Antwort des Lernbegleiters war unvollständig. Bitte erneut senden.', 502); }
}

/** Receive the answer piece by piece (NDJSON events from /api/tutor/chat/stream). */
async function streamChat(body: ChatRequest, signal: AbortSignal, onDelta: (text: string) => void, onThinking: (text: string) => void): Promise<ChatResponse> {
  const response = await fetch('/api/tutor/chat/stream', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `Die Anfrage konnte nicht abgeschlossen werden (${response.status}).`;
    try {
      const detail = (await response.json()).detail;
      if (typeof detail === 'string') message = detail;
    } catch { /* The readable fallback also covers non-JSON server errors. */ }
    throw new TutorRequestError(message, response.status);
  }
  if (!response.body) throw new TutorRequestError('Dieser Browser kann die Antwort nicht schrittweise empfangen.', 0);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finished: ChatResponse | null = null;
  try {
    for (;;) {
      const chunk = await reader.read();
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split('\n');
      buffer = chunk.done ? '' : lines.pop() ?? '';
      for (const line of lines) {
        const event = parseEvent(line);
        if (!event) continue;
        if (event.type === 'delta') onDelta(event.text);
        else if (event.type === 'thinking') onThinking(event.text);
        else if (event.type === 'done') finished = { answer: event.answer, sources: event.sources, provider: event.provider, model: event.model, notice: event.notice, excerpts: event.excerpts, figures: event.figures };
        else throw new TutorRequestError(typeof event.detail === 'string' ? event.detail : 'Der Lernbegleiter konnte nicht antworten.', event.status || 502);
      }
      if (chunk.done) break;
    }
  } catch (error) {
    void reader.cancel().catch(() => undefined);
    throw error;
  }
  if (!finished) throw new TutorRequestError('Die Antwort des Lernbegleiters wurde unterbrochen. Bitte erneut senden.', 502);
  return finished;
}

/** One answer with clickable references and the matching original excerpts below it. */
function AssistantAnswer({ message, seconds }: { message: Message; seconds: (value: number) => string }) {
  const sources = message.sources || [];
  const cited = citedIds(message.content)
    .map(id => sources.find(source => source.id === id))
    .filter((source): source is TutorSource => !!source);
  const [open, setOpen] = useState<string[]>([]);
  const baseId = `tutor-reading-${message.id}`;
  const cite = (id: string) => {
    setOpen(previous => previous.includes(id) ? previous : [...previous, id]);
    requestAnimationFrame(() => document.getElementById(`${baseId}-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
  };
  const figures = figuresFor(message, cited);
  return <>
    <AnswerText text={message.content} sources={sources} onCite={cite} highlightTask />
    {figures.length > 0 && <section className="tutor-figures" aria-label="Abbildungen aus den Unterlagen"><SourceImages images={figures} /></section>}
    {message.thinking && <details className="tutor-thinking"><summary>Überlegungen des Modells anzeigen (ungeprüft)</summary><p className="preserve-lines">{message.thinking}</p></details>}
    {message.responseSeconds !== undefined && <p className="tutor-notice tutor-meta">{message.thinking ? 'Mit Nachdenken · ' : ''}{message.firstTokenSeconds !== undefined ? `Antwortbeginn nach ${seconds(message.firstTokenSeconds)} · ` : ''}Antwortzeit: {seconds(message.responseSeconds)}</p>}
    {cited.length ? <section className="tutor-reading" aria-label="Zum Nachlesen">
      <div className="tutor-reading-heading"><strong className="tutor-reading-title">Zum Nachlesen</strong><span>{cited.length} {cited.length === 1 ? 'Quelle' : 'Quellen'}</span></div>
      {cited.map(source => {
        const parts = message.excerpts?.[source.id] || [];
        return <details key={source.id} id={`${baseId}-${source.id}`} open={open.includes(source.id)} onToggle={event => {
          const isOpen = event.currentTarget.open;
          setOpen(previous => isOpen ? (previous.includes(source.id) ? previous : [...previous, source.id]) : previous.filter(id => id !== source.id));
        }}>
          <summary className="tutor-reading-summary">
            <span className="tutor-cite">{source.id}</span>
            <span className="tutor-reading-description">
              <strong>{source.title}</strong>
              <span>{source.chapter && ` · ${source.chapter}`} · {sourcePosition(source)}</span>
            </span>
            <span className="tutor-reading-chevron" aria-hidden="true">›</span>
          </summary>
          <div className="tutor-reading-content">
          <div className="tutor-reading-actions">{source.kind === 'video'
            ? <SourceDocumentLink path={source.path} timestamp={source.timestamp_seconds} end={source.timestamp_end_seconds}>Im Video ansehen</SourceDocumentLink>
            : <SourceDocumentLink path={source.path} page={parts[0]?.pdf_page ?? source.pdf_page} pageEnd={source.pdf_page_end}>Im Original öffnen · PDF-Seite {parts[0]?.pdf_page ?? source.pdf_page}</SourceDocumentLink>}</div>
          {parts.length ? parts.map(part => <blockquote key={part.pdf_page} className="tutor-excerpt" tabIndex={0} aria-label={`Originalauszug, PDF-Seite ${part.pdf_page}`}><small>Originalauszug · PDF-Seite {part.pdf_page}</small><div className="tutor-excerpt-text">{part.text}</div></blockquote>)
            : <p className="tutor-notice">Für diese Quelle ist kein Originalauszug beigefügt. Bitte im Original nachlesen.</p>}
          </div>
        </details>;
      })}
    </section> : <p className="tutor-notice">Diese Antwort enthält keine Quellenverweise. Prüfe die Aussagen anhand der Quellen zur Antwort.</p>}
    {(message.notice || (!cited.length && !!sources.length)) && <details className="tutor-answer-sources"><summary>Hinweise zur Antwort</summary>
      {!cited.length && !!sources.length && <SourceLinks sources={sourcesForDisplay(sources)} title="Quellen im Lernkontext" />}
      {message.notice && <p className="tutor-notice">{message.notice}</p>}
    </details>}
  </>;
}

/** Figures whose sources the answer cites, or that it names by number (e.g. „Abb. 2“). */
function figuresFor(message: Message, cited: TutorSource[]): TutorFigure[] {
  const ids = new Set(cited.map(source => source.id));
  return (message.figures || []).filter(figure =>
    figure.source_ids.some(id => ids.has(id)) || mentionsFigure(message.content, figure.caption));
}

function mentionsFigure(text: string, caption: string) {
  const number = /Abb(?:ildung|\.)?\s*(\d+)/i.exec(caption)?.[1];
  return !!number && new RegExp(`Abb(?:ildung|\\.)?\\s*${number}(?!\\d)`, 'i').test(text);
}

function requestHistory(messages: Message[]): HistoryItem[] {
  const history: HistoryItem[] = [];
  let characters = 0;
  // Keep complete, successful question-answer pairs within the server's limits.
  for (let index = messages.length - 2; index >= 0 && history.length < 12; index -= 2) {
    const pair = messages.slice(index, index + 2);
    if (pair.some(message => message.content.length > (message.role === 'assistant' ? 16000 : maxMessageLength))) break;
    const length = pair.reduce((total, message) => total + message.content.length, 0);
    if (characters + length > 18000) break;
    history.unshift(...pair.map(({ role, content }) => ({ role, content })));
    characters += length;
  }
  return history;
}

function sourcesForDisplay(sources: TutorSource[]): SourceRef[] {
  return sources.map(source => ({ ...source, title: `[${source.id}] ${source.title}` }));
}

function sourceDescription(source: TutorSource) {
  const position = source.kind === 'video'
    ? `Video ab Sekunde ${source.timestamp_seconds}${source.timestamp_end_seconds !== undefined ? ` bis ${source.timestamp_end_seconds}` : ''}`
    : `PDF-Seite ${source.pdf_page}${source.pdf_page_end && source.pdf_page_end !== source.pdf_page ? `–${source.pdf_page_end}` : ''}`;
  return `[${source.id}] ${source.title}${source.chapter ? ` · ${source.chapter}` : ''}\n${position}\n${source.path}`;
}

function providerText(context: TutorContext, history: HistoryItem[], message: string) {
  return [
    context.instructions ? `ANWEISUNGEN FÜR DEN LERNBEGLEITER\n${context.instructions}` : '',
    `LERNKONTEXT\n${context.context_preamble || ''}${context.context_text}`,
    history.length ? `BISHERIGES GESPRÄCH\n${history.map(item => `${item.role === 'user' ? 'Du' : 'Lernbegleiter'}:\n${item.content}`).join('\n\n')}` : '',
    `DEIN LERNAUFTRAG\n${message}`,
  ].filter(Boolean).join('\n\n');
}

function preparedText(context: TutorContext, history: HistoryItem[], message: string) {
  return [
    `THEMA\n${context.title}`,
    providerText(context, history, message),
    context.sources.length ? `QUELLEN ZUM NACHLESEN\n${context.sources.map(sourceDescription).join('\n\n')}` : '',
  ].filter(Boolean).join('\n\n');
}

export function TutorWorkspace({ scope, moduleTitle }: { scope: TutorScope; moduleTitle: string }) {
  const [status, setStatus] = useState<TutorStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState('');
  const [context, setContext] = useState<TutorContext | null>(null);
  const [contextLoading, setContextLoading] = useState(true);
  const [contextError, setContextError] = useState('');
  const [version, setVersion] = useState(0);
  const [statusVersion, setStatusVersion] = useState(0);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeTurn, setActiveTurn] = useState<ChatRequest | null>(null);
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState('');
  const [streamText, setStreamText] = useState('');
  const [thinkText, setThinkText] = useState('');
  const [think, setThink] = useState(false);
  const thinkingRef = useRef('');
  const streamArticle = useRef<HTMLElement | null>(null);
  const streamStarted = !!streamText;
  useEffect(() => {
    // Show the beginning of a new answer once; afterwards the reader scrolls freely.
    if (streamStarted) streamArticle.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [streamStarted]);
  const [copyNotice, setCopyNotice] = useState('');
  const chatController = useRef<AbortController | null>(null);
  const requestRunning = useRef(false);
  const alive = useRef(true);
  const nextMessageId = useRef(1);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const id = useId().replace(/:/g, '');
  const [goalId, setGoalId] = useState('');
  const scopeQuery = query({ ...scope, ...(goalId ? { goal_id: goalId } : {}) });
  const voice = useTutorVoice(scopeQuery, text => {
    const combined = [draft.trimEnd(), text].filter(Boolean).join(draft.includes('\n') ? '\n' : ' ');
    if (combined.length > maxMessageLength) throw new Error('Die Frage würde länger als 4.000 Zeichen. Bitte den vorhandenen Text kürzen und erneut aufnehmen.');
    setDraft(combined); setCopyNotice('');
    requestAnimationFrame(() => messageInput.current?.focus());
  });
  const timingKey = `mlh-tutor-timing-v1:${scopeQuery}`;
  const [timings, setTimings] = useState<number[]>(() => {
    try { const saved = JSON.parse(localStorage.getItem(timingKey) || '[]'); return Array.isArray(saved) ? saved.filter((n): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0).slice(-100) : []; } catch { return []; }
  });
  const [timingSaved, setTimingSaved] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef(0);
  const firstTokenAt = useRef<number | null>(null);
  useEffect(() => {
    if (!sending) return;
    const timer = window.setInterval(() => setElapsed((performance.now() - startedAt.current) / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [sending]);
  const seconds = (value: number) => `${value.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;


  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setStatusLoading(true); setStatusError('');
    tutorRequest<TutorStatus>('status', controller.signal).then(value => {
      if (active) setStatus(value);
    }).catch(error => {
      if (active) { setStatus(null); setStatusError(errorText(error)); }
    }).finally(() => { if (active) setStatusLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [statusVersion]);

  useEffect(() => {
    if (!status || !['ollama', 'bonsai'].includes(status.provider)) return;
    const timer = window.setTimeout(() => setStatusVersion(value => value + 1), status.readiness === 'starting' ? 2000 : 10000);
    return () => window.clearTimeout(timer);
  }, [status, statusVersion]);

  const [switchingModel, setSwitchingModel] = useState(false);
  const switchModel = async (provider: string) => {
    setSwitchingModel(true); setStatusError('');
    try { setStatus(await tutorRequest<TutorStatus>('model', new AbortController().signal, { provider })); }
    catch (error) { setStatusError(errorText(error)); }
    finally { setSwitchingModel(false); }
  };
  const retryModel = async () => {
    const controller = new AbortController();
    setStatusError('');
    try { setStatus(await tutorRequest<TutorStatus>('retry', controller.signal, {})); }
    catch (error) { setStatusError(errorText(error)); }
  };

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setContextLoading(true); setContextError(''); setContext(null);
    tutorRequest<TutorContext>(`context${scopeQuery}`, controller.signal).then(value => {
      if (active) setContext(value);
    }).catch(error => {
      if (active) setContextError(errorText(error));
    }).finally(() => { if (active) setContextLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [scopeQuery, version]);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; chatController.current?.abort(); };
  }, []);

  const history = requestHistory(messages);
  const nextMessage = activeTurn?.message || draft.trim();
  const previewHistory = activeTurn?.history || history;
  const exportText = context ? preparedText(context, previewHistory, nextMessage) : '';
  const preview = context ? providerText(context, previewHistory, nextMessage) : '';
  const canSend = !switchingModel && !!status?.configured && (!['ollama', 'bonsai'].includes(status.provider) || status.readiness === 'ready') && status.capabilities.text && !!context && !contextLoading;

  const send = async (retry?: ChatRequest) => {
    if (requestRunning.current || voice.busy || !canSend || (!retry && activeTurn)) return;
    const message = draft.trim();
    if (!retry && (!message || message.length > maxMessageLength)) return;
    const request: ChatRequest = retry || { ...scope, ...(goalId ? { goal_id: goalId } : {}), message, history, ...(think && status?.thinking ? { think: true } : {}) };
    startedAt.current = performance.now(); setElapsed(0);
    requestRunning.current = true;
    setSending(true); setChatError(''); setCopyNotice(''); setActiveTurn(request); setStreamText(''); setThinkText(''); thinkingRef.current = ''; firstTokenAt.current = null;
    if (!retry) setDraft('');
    voice.stopSpeaking();
    const controller = new AbortController();
    chatController.current = controller;
    try {
      const response = await streamChat(request, controller.signal, text => {
        if (!alive.current || controller.signal.aborted) return;
        if (firstTokenAt.current === null) firstTokenAt.current = (performance.now() - startedAt.current) / 1000;
        setStreamText(previous => previous + text);
      }, text => {
        if (!alive.current || controller.signal.aborted) return;
        thinkingRef.current += text;
        setThinkText(previous => previous + text);
      });
      if (!alive.current || controller.signal.aborted) return;
      const responseSeconds = (performance.now() - startedAt.current) / 1000;
      const nextTimings = [...timings, responseSeconds].slice(-100);
      setTimings(nextTimings);
      try { localStorage.setItem(timingKey, JSON.stringify(nextTimings)); setTimingSaved(true); } catch { setTimingSaved(false); }
      setMessages(previous => [...previous,
        { id: nextMessageId.current++, role: 'user', content: request.message },
        { id: nextMessageId.current++, role: 'assistant', content: response.answer, responseSeconds, firstTokenSeconds: firstTokenAt.current ?? undefined, sources: response.sources, excerpts: response.excerpts, figures: response.figures, notice: response.notice, thinking: thinkingRef.current.trim() || undefined },
      ]);
      setStreamText(''); setThinkText('');
      setActiveTurn(null);
      if (voice.readReplies) void voice.speak(response.answer);
      requestAnimationFrame(() => { if (alive.current) messageInput.current?.focus(); });
    } catch (error) {
      if (!alive.current || controller.signal.aborted) return;
      setStreamText(''); setThinkText(''); setChatError(errorText(error));
      if (error instanceof TutorRequestError && error.status === 503) setStatusVersion(value => value + 1);
    } finally {
      if (alive.current && !controller.signal.aborted) { requestRunning.current = false; setSending(false); }
    }
  };

  const copy = async () => {
    if (!exportText) return;
    try {
      await navigator.clipboard.writeText(exportText);
      if (alive.current) setCopyNotice('Lernauftrag und vollständiger Kontext wurden kopiert.');
    } catch {
      if (alive.current) setCopyNotice('Kopieren ist in diesem Browser nicht verfügbar. Du kannst den Lernauftrag als TXT speichern oder aus der Vorschau kopieren.');
    }
  };

  const download = () => {
    if (!exportText) return;
    const url = URL.createObjectURL(new Blob([exportText], { type: 'text/plain;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `Lernauftrag-${scope.module_id.replace(/[^a-zA-Z0-9_-]/g, '-')}.txt`;
    document.body.append(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setCopyNotice('Lernauftrag und vollständiger Kontext wurden als TXT zum Speichern bereitgestellt.');
  };

  return <div className="tutor-workspace">
    <div className="tutor-status" aria-live="polite">
      {statusLoading && !status ? <p>Zugang wird geprüft …</p> : statusError ? <>
        <p className="tutor-error">Der Modellzugang konnte nicht geprüft werden. {statusError}</p>
        <button className="text-button" onClick={() => setStatusVersion(value => value + 1)}>Erneut prüfen <Icon name="refresh" size={14} /></button>
      </> : status?.configured ? <>
        {['ollama', 'bonsai'].includes(status.provider) && <label className="field"><span>Lokales Modell</span><select value={status.provider} disabled={sending || !!activeTurn || switchingModel || voice.busy} onChange={event => void switchModel(event.target.value)}><option value="ollama">Qwen · Ollama</option><option value="bonsai">Bonsai 2 27B · MLX</option></select></label>}
        <div className="tutor-status-heading"><Badge tone={status.readiness === 'ready' ? 'teal' : undefined}>{['ollama', 'bonsai'].includes(status.provider) ? status.readiness === 'ready' ? 'Tutor bereit' : status.readiness === 'starting' ? 'Modell wird geladen' : 'Tutor nicht bereit' : 'Zugang eingerichtet'}</Badge>{status.model && <span>{status.model}</span>}</div>
        {(!['ollama', 'bonsai'].includes(status.provider) || status.readiness !== 'ready') && <p>{status.data_flow === 'cloud' ? 'Beim Senden werden der ausgewählte Lernkontext und die letzten passenden Nachrichten an den eingerichteten Cloud-Modellanbieter übermittelt.' : status.message}</p>}
        {status.readiness === 'error' && <button className="text-button" onClick={() => void retryModel()}>Modell erneut prüfen <Icon name="refresh" size={14} /></button>}
      </> : <>
        <Badge>Zur Vorbereitung bereit</Badge>
        <p>Modellzugang noch nicht verbunden. Du kannst Thema und Lernauftrag vorbereiten.</p>
        <button className="text-button" onClick={() => setStatusVersion(value => value + 1)}>Zugang erneut prüfen <Icon name="refresh" size={14} /></button>
      </>}
    </div>
    <div className="tutor-chat-flow">
      {!!messages.length && <div className="tutor-conversation" role="log" aria-label="Dein Lerngespräch" aria-relevant="additions">
        {messages.map((message, index) => <article key={message.id} className={`tutor-message tutor-message-${message.role}`} aria-label={message.role === 'user' ? 'Deine Frage' : 'Antwort des Lernbegleiters'}>
          <strong className="tutor-message-author">{message.role === 'user' ? 'Du · Deine Nachricht' : 'Lernbegleiter · KI-Antwort'}</strong>
          {message.role === 'assistant' ? <AssistantAnswer message={message} seconds={seconds} /> : <p className="preserve-lines">{message.content}</p>}
          {message.role === 'assistant' && voice.speechAvailable && <button type="button" className="text-button tutor-read-answer" disabled={voice.busy || sending} onClick={() => void voice.speak(message.content)}><VoiceIcon speaker /> Antwort vorlesen</button>}
          {message.role === 'assistant' && ['ollama', 'bonsai'].includes(status?.provider || '') && messages[index - 1]?.role === 'user' && <AnswerReview question={messages[index - 1].content} answer={message.content} disabled={sending || !!activeTurn || voice.busy}
            onFollowUp={text => { setDraft(text.slice(0, maxMessageLength)); requestAnimationFrame(() => messageInput.current?.focus()); }} />}
        </article>)}
      </div>}
      {activeTurn && <div className="tutor-pending-turn">
        <article className="tutor-message tutor-message-user" aria-label="Deine Frage"><strong className="tutor-message-author">Du · Deine Nachricht</strong><p className="preserve-lines">{activeTurn.message}</p></article>
        {streamText && <article ref={streamArticle} className="tutor-message tutor-message-assistant tutor-message-streaming" aria-label="Antwort des Lernbegleiters entsteht" aria-busy="true">
          <strong className="tutor-message-author">Lernbegleiter · KI-Antwort entsteht …</strong>
          <AnswerText text={streamText} sources={[]} highlightTask />
        </article>}
        {sending && <div className="tutor-sending" role="status"><span className="spinner" /> {streamText ? 'Der Lernbegleiter schreibt' : thinkText ? `Der Lernbegleiter denkt nach (${thinkText.trim().split(/\s+/).length} Wörter)` : 'Der Lernbegleiter liest den Lernstoff'} … {seconds(elapsed)}</div>}
        {chatError && <div className="tutor-chat-error" role="alert"><strong>Es ist noch keine Antwort angekommen.</strong><p>{chatError}</p><div className="button-row">
          <Button className="secondary small" disabled={!canSend || sending} onClick={() => void send(activeTurn)}>Erneut senden <Icon name="refresh" size={14} /></Button>
          <Button className="secondary small" onClick={() => { setDraft(activeTurn.message); setActiveTurn(null); setChatError(''); requestAnimationFrame(() => messageInput.current?.focus()); }}>Frage bearbeiten</Button>
        </div></div>}
      </div>}

      <form className="tutor-composer" aria-label="Deine Nachricht verfassen" onSubmit={event => { event.preventDefault(); void send(); }}>
        <h3 className="tutor-composer-title sr-only">Dein Eingabebereich</h3>
        {!messages.length && !activeTurn && <div className="tutor-learning-starts" aria-label="Einstieg wählen">{learningStarts.map(start => <button type="button" key={start.label} disabled={voice.busy} aria-pressed={draft === start.message} onClick={() => { setDraft(start.message); setCopyNotice(''); messageInput.current?.focus(); }}>{start.label}</button>)}</div>}
        <label htmlFor={`tutor-message-${id}`}>{messages.length ? 'Deine nächste Frage' : 'Dein Lernziel oder deine Frage'}</label>
        <div className={`tutor-input-shell${voice.capture === 'recording' ? ' is-recording' : ''}`}>
          <textarea id={`tutor-message-${id}`} ref={messageInput} rows={Math.min(8, Math.max(messages.length ? 2 : 3, draft.split('\n').length + Math.floor(draft.length / 90)))} placeholder="Zum Beispiel: Ich verstehe den Unterschied noch nicht. Erkläre ihn mir an einem einfachen Beispiel." value={draft} maxLength={maxMessageLength}
            disabled={sending || !!activeTurn || voice.busy} aria-describedby={`tutor-input-hint-${id} tutor-voice-status-${id}`}
            onChange={event => { setDraft(event.target.value); setCopyNotice(''); }}
            onKeyDown={event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void send(); } }} />
          <button type="button" className="tutor-microphone" aria-label={voice.capture === 'recording' ? 'Aufnahme beenden' : 'Frage einsprechen'}
            title={voice.hint || (voice.capture === 'recording' ? 'Aufnahme beenden' : 'Frage einsprechen · lokal auf deinem Mac')}
            aria-pressed={voice.capture === 'recording'} aria-describedby={`tutor-voice-status-${id}`}
            disabled={!voice.available || sending || !!activeTurn || voice.capture === 'requesting' || voice.capture === 'transcribing'} onClick={() => void voice.toggleRecording()}>
            {voice.capture === 'requesting' || voice.capture === 'transcribing' ? <span className="spinner" /> : <VoiceIcon recording={voice.capture === 'recording'} />}
          </button>
        </div>
        <div className="tutor-voice-status" id={`tutor-voice-status-${id}`}>
          <span role="status">{voice.capture === 'recording' ? 'Aufnahme läuft' : voice.capture === 'requesting' ? 'Mikrofonzugriff im Browser erlauben …' : voice.capture === 'transcribing' ? 'Sprache wird in Text umgewandelt …' : voice.notice || voice.hint}</span>
          {voice.capture === 'recording' && <span className="tutor-recording-time" aria-label={`${voice.seconds} Sekunden aufgenommen`}>{voice.seconds} / {voice.maxSeconds} s</span>}
          {voice.busy && <button type="button" className="text-button" onClick={() => voice.cancel()}>Abbrechen</button>}
        </div>
        <div className="tutor-input-hint" id={`tutor-input-hint-${id}`}><span>Zum Senden: Strg + Enter oder ⌘ + Enter.</span><span>{draft.length} / {maxMessageLength}</span></div>
        <div className="tutor-composer-actions">{voice.speechAvailable && <label className="tutor-read-toggle"><input type="checkbox" checked={voice.readReplies} disabled={sending} onChange={event => { voice.setReadReplies(event.target.checked); if (!event.target.checked) voice.stopSpeaking(); }} /> Antworten vorlesen</label>}{status?.thinking && <label className="tutor-think-toggle" title="Das Modell überlegt vor der Antwort: gründlicher, aber deutlich langsamer (oft 1–3 Minuten).">
          <input type="checkbox" checked={think} disabled={sending} onChange={event => setThink(event.target.checked)} /> Gründlich nachdenken (langsamer)
        </label>}<Button type="submit" disabled={!canSend || !draft.trim() || sending || !!activeTurn || voice.busy}>{messages.length ? 'Senden' : 'Lernen starten'} <Icon name="arrow" size={16} /></Button>
          {!status?.configured && !statusLoading && <span>Für Antworten ist ein Modellzugang erforderlich.</span>}
        </div>
        {(voice.speechLoading || voice.audioUrl) && <div className="tutor-voice-player" aria-label="Gesprochene Antwort">
          {voice.speechLoading ? <span role="status">Die Antwort wird zum Vorlesen vorbereitet …</span> : <audio ref={voice.audioElement} src={voice.audioUrl} controls aria-label="Antwort anhören" />}
          <button type="button" className="text-button" onClick={() => voice.stopSpeaking()}>Vorlesen beenden</button>
        </div>}
      </form>
    </div>
    <div className="tutor-learning-tools">
      <LearningMemory moduleId={scope.module_id} goalId={goalId} disabled={sending || !!activeTurn || voice.busy} lastAnswer={[...messages].reverse().find(message => message.role === 'user')?.content || ''} onSelect={value => { if (value === goalId) return; setGoalId(value); setMessages([]); setDraft(''); setChatError(''); }} onQuestion={text => { setDraft(text); requestAnimationFrame(() => messageInput.current?.focus()); }} />
      {goalId && <ModelSolution key={goalId} moduleId={scope.module_id} goalId={goalId} disabled={sending || !!activeTurn || switchingModel || voice.busy} />}
    </div>
    {!!timings.length && <details className="tutor-preview"><summary>Antwortzeiten für diese Auswahl</summary>
      <p>Letzte Antwort: {seconds(timings[timings.length - 1])} · Durchschnitt: {seconds(timings.reduce((sum, value) => sum + value, 0) / timings.length)} · {timings.length} erfolgreiche Antworten.</p>
      <p>Gemessen vom Absenden bis zum vollständigen Empfang, einschließlich Ladezeit. Die letzten 100 Messungen je Themenauswahl bleiben in diesem Browser gespeichert. Fehlgeschlagene Anfragen zählen nicht zum Durchschnitt.</p>
      {!timingSaved && <p role="status">Die Messung konnte nur für diese geöffnete Ansicht gespeichert werden.</p>}
    </details>}

    {contextLoading ? <Loading /> : contextError ? <div className="tutor-context-error" role="alert">
      <strong>Der Lernkontext konnte nicht geladen werden.</strong><p>{contextError}</p>
      <Button className="secondary small" onClick={() => setVersion(value => value + 1)}>Kontext erneut laden</Button>
    </div> : context && <>
      <div className="tutor-knowledge">
        <span className="eyebrow">AUSGANGSPUNKT FÜR DEIN GESPRÄCH</span><h3>{context.title}</h3>
        <p>{moduleTitle} · Ausgewählte Lerntexte{context.sources.length ? ` · ${context.sources.length} ${context.sources.length === 1 ? 'Quellenverweis' : 'Quellenverweise'}` : ' · Keine Originalquelle verknüpft'}</p>
        <p>Im Modulchat wählt der Hub anhand deiner Frage eine passende Lernseite. Bei Nachfragen berücksichtigt er das bisherige Thema. Genannte PDF-Seiten und Abbildungen sucht er innerhalb der ausgewählten Quellen. Die tatsächlich beigefügten Auszüge stehen unter jeder Antwort.</p>
        <details><summary>Quellen und Umfang ansehen</summary>
          <SourceLinks sources={sourcesForDisplay(context.sources)} title="Verknüpfte Quellen zum Nachlesen" />
          {context.notice && <p className="tutor-notice">{context.notice}</p>}
        </details>
      </div>
    </>}

    <details className="tutor-export-details"><summary>Lernauftrag mitnehmen oder Vorschau ansehen</summary>
    <div className="tutor-export"><div className="button-row">
      <Button className="secondary small" disabled={!preview || !nextMessage || contextLoading} onClick={() => void copy()}>Lernauftrag kopieren <Icon name="file" size={15} /></Button>
      <Button className="secondary small" disabled={!preview || !nextMessage || contextLoading} onClick={download}>Als TXT speichern <Icon name="download" size={15} /></Button>
    </div><p className="tutor-export-hint">Mit vollständigem Lernkontext und Quellen. Du entscheidest, wo du den Lernauftrag verwendest.</p>
      {copyNotice && <p className="tutor-copy-notice" role="status">{copyNotice}</p>}
    </div>
    {!!context && <details className="tutor-preview"><summary>{status?.configured ? 'Vorbereiteter Lernauftrag vor der thematischen Quellenauswahl' : 'Vorschau des vorbereiteten Lernauftrags'}</summary>
      <p>Die Vorschau zeigt den Ausgangskontext. Beim Senden kann der Hub passend zur Frage andere Lerntexte und Belege auswählen. Für das lokale Modell werden lange Quellenauszüge und ältere Nachrichten bei Bedarf gekürzt; die Antwort weist darauf hin. Verwendet werden höchstens sechs letzte Frage-Antwort-Paare.</p>
      <pre tabIndex={0} aria-label="Vollständiger vorbereiteter Lernauftrag">{preview}</pre>
    </details>}
    </details>
    <p className="tutor-privacy">Dein Gespräch und dein Entwurf bleiben nur in dieser geöffneten Ansicht. Beim Themenwechsel beginnt ein neues Gespräch. Im Lernprotokoll ausdrücklich gespeicherte Antworten und Selbsteinschätzungen bleiben dauerhaft erhalten. Es werden keine Quiz-Versuche angelegt.</p>
  </div>;
}

export function TutorEntryLink({ bundle, initialLessonId = '', initialSectionId = '', conceptId = '' }: {
  bundle: LearningPagesPackage;
  initialLessonId?: string;
  initialSectionId?: string;
  conceptId?: string;
}) {
  const topic = bundle.lessons.find(item => item.id === initialLessonId)?.title || bundle.overview.big_picture?.nodes.find(item => item.id === conceptId)?.title || bundle.module_title;
  const href = `#tutor${query({ module: bundle.module_id, lesson: initialLessonId, section: initialSectionId, concept: conceptId })}`;
  return <aside className="learning-tutor tutor-entry" aria-label="Mit KI lernen">
    <div><h2>Dieses Thema gemeinsam verstehen</h2><p>{topic} ist bereits vorausgewählt. Lass es dir erklären oder prüfe dein Verständnis im Lernchat.</p></div>
    <a className="button" href={href}>Mit KI lernen <Icon name="arrow" size={17} /></a>
  </aside>;
}
