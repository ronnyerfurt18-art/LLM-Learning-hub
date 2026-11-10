import { FormEvent, ReactNode, useEffect, useId, useRef, useState } from 'react';
import { errorText, query } from './api';
import { Button, Icon } from './components';
import { SourceDocumentLink } from './SourceLinks';
import { Module, SourceRef } from './types';
import { unitLabel } from './unitLabel';
import './content-search.css';

type DocumentSource = { kind: 'document'; path: string; title: string; chapter?: string };
export type SearchResult = {
  id: string;
  kind: 'lesson' | 'concept' | 'document';
  module_id: string;
  module_title: string;
  unit_label?: string;
  unit?: number;
  title: string;
  section_title?: string;
  snippet: string;
  lesson_id?: string;
  section_id?: string;
  concept_id?: string;
  source?: SourceRef | DocumentSource;
  sources?: SourceRef[];
};
type SearchResponse = { query: string; terms: string[]; total: number; limit: number; offset: number; results: SearchResult[]; notice?: string };
type SearchState = { query: string; moduleId: string };
type SearchRequest = SearchState & { offset: number };
type Props = {
  modules: Pick<Module, 'id' | 'name' | 'number'>[];
  initialModule?: string;
  initialQuery?: string;
  onSearchStateChange?: (state: SearchState) => void;
  onOpenResult: (result: SearchResult) => void;
  onClose: () => void;
};

const pageSize = 30;
const minQueryLength = 2;
const maxQueryLength = 200;

function normalized(value: string) {
  return value.normalize('NFKD').replace(/\p{M}/gu, '').toLocaleLowerCase('de-DE').replace(/ß/g, 'ss');
}

// Search normalization can change a character's length (for example ß → ss).
// Keep its original range so highlights always contain the actual source text.
function Highlight({ text, terms }: { text: string; terms: string[] }) {
  let folded = '';
  const starts: number[] = [], ends: number[] = [];
  let originalOffset = 0;
  for (const character of text) {
    const value = normalized(character);
    for (let index = 0; index < value.length; index += 1) {
      starts.push(originalOffset); ends.push(originalOffset + character.length);
    }
    folded += value;
    originalOffset += character.length;
  }
  const ranges: { start: number; end: number }[] = [];
  for (const term of new Set(terms.map(normalized).filter(Boolean))) {
    let offset = 0;
    while (offset <= folded.length - term.length) {
      const found = folded.indexOf(term, offset);
      if (found < 0) break;
      ranges.push({ start: starts[found], end: ends[found + term.length - 1] });
      offset = found + term.length;
    }
  }
  if (!ranges.length) return <>{text}</>;
  ranges.sort((left, right) => left.start - right.start || right.end - left.end);
  const merged: typeof ranges = [];
  for (const range of ranges) {
    const previous = merged.at(-1);
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end);
    else merged.push({ ...range });
  }
  const pieces: ReactNode[] = [];
  let position = 0;
  merged.forEach((range, index) => {
    if (range.start > position) pieces.push(text.slice(position, range.start));
    pieces.push(<mark key={index}>{text.slice(range.start, range.end)}</mark>);
    position = range.end;
  });
  if (position < text.length) pieces.push(text.slice(position));
  return <>{pieces}</>;
}

function sourceLabel(source: SourceRef | DocumentSource) {
  if (source.kind === 'document') return source.chapter || 'Datei';
  if (source.kind === 'video') {
    const seconds = Math.floor(source.timestamp_seconds);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const time = `${hours ? `${hours}:` : ''}${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    return `Video · ${time}`;
  }
  return `PDF-Seite ${source.pdf_page}${source.pdf_page_end && source.pdf_page_end !== source.pdf_page ? `–${source.pdf_page_end}` : ''}`;
}

function SearchSource({ source, original = false }: { source: SourceRef | DocumentSource; original?: boolean }) {
  const label = sourceLabel(source);
  return <SourceDocumentLink
    path={source.path}
    page={source.kind !== 'video' && source.kind !== 'document' ? source.pdf_page : undefined}
    timestamp={source.kind === 'video' ? source.timestamp_seconds : undefined}
    end={source.kind === 'video' ? source.timestamp_end_seconds : undefined}
  >{original ? `Datei öffnen · ${label}` : label}</SourceDocumentLink>;
}

export function ContentSearch({ modules, initialModule = '', initialQuery = '', onSearchStateChange, onOpenResult, onClose }: Props) {
  const [draft, setDraft] = useState(initialQuery);
  const [moduleId, setModuleId] = useState(modules.some(module => module.id === initialModule) ? initialModule : '');
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const requestNumber = useRef(0);
  const lastRequest = useRef<SearchRequest | null>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const stateChange = useRef(onSearchStateChange);
  stateChange.current = onSearchStateChange;
  const id = useId();

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    searchInput.current?.focus();
    return () => {
      requestNumber.current += 1;
      controller.current?.abort();
      element?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => { stateChange.current?.({ query: draft, moduleId }); }, [draft, moduleId]);

  async function search(request: SearchRequest) {
    const value = request.query.trim();
    controller.current?.abort();
    const version = ++requestNumber.current;
    if (value.length < minQueryLength) {
      setResponse(null); setLoading(false); setHasSearched(false);
      setError(`Gib mindestens ${minQueryLength} Zeichen ein.`);
      searchInput.current?.focus();
      return;
    }
    const current = new AbortController();
    controller.current = current;
    lastRequest.current = { ...request, query: value };
    setLoading(true); setError(''); setHasSearched(true);
    if (!request.offset) setResponse(null);
    try {
      const result = await fetch(`/api/search${query({ q: value, module_id: request.moduleId, limit: pageSize, offset: request.offset })}`, { signal: current.signal });
      if (!result.ok) {
        let message = `Die Suche konnte nicht abgeschlossen werden (${result.status}).`;
        try {
          const detail = (await result.json()).detail;
          if (typeof detail === 'string') message = detail;
        } catch { /* Keep a readable message for non-JSON errors. */ }
        throw new Error(message);
      }
      const next = await result.json() as SearchResponse;
      if (version !== requestNumber.current || current.signal.aborted) return;
      setResponse(previous => request.offset && previous
        ? { ...next, results: [...previous.results, ...next.results], offset: 0 }
        : next);
    } catch (failure) {
      if (version === requestNumber.current && !current.signal.aborted) setError(errorText(failure));
    } finally {
      if (version === requestNumber.current) setLoading(false);
    }
  }

  useEffect(() => {
    if (initialQuery.trim().length >= minQueryLength) void search({ query: initialQuery, moduleId, offset: 0 });
    // Restore the last query once when this dialog is reopened.
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    void search({ query: draft, moduleId, offset: 0 });
  }

  function changeModule(value: string) {
    setModuleId(value);
    controller.current?.abort(); requestNumber.current += 1;
    setResponse(null); setError(''); setLoading(false);
    if (hasSearched && draft.trim().length >= minQueryLength) void search({ query: draft, moduleId: value, offset: 0 });
    else setHasSearched(false);
  }

  function clear() {
    controller.current?.abort(); requestNumber.current += 1;
    setDraft(''); setResponse(null); setError(''); setHasSearched(false); setLoading(false);
    searchInput.current?.focus();
  }

  const count = response?.results.length || 0;
  const more = !!response && count < response.total;

  return <dialog ref={dialog} className="content-search-dialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
    onCancel={event => { event.preventDefault(); close.current(); }}
    onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); } }}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close.current();
    }}>
    <div className="content-search-shell">
      <header className="content-search-header">
        <div><div className="eyebrow">In deinen Studienunterlagen</div><h2 id={`${id}-title`}><Icon name="search" size={23}/>Inhalte durchsuchen</h2></div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Suche schließen"><Icon name="close"/></button>
      </header>
      <p id={`${id}-description`} className="content-search-description">Finde Begriffe in Lernseiten und Unterlagen. Öffne die passende Stelle, um deine Aufgaben mit Quellen zu bearbeiten.</p>
      <form className="content-search-form" onSubmit={submit} role="search" aria-label="Studieninhalte durchsuchen">
        <label className="content-search-query" htmlFor={`${id}-query`}><span>Suchbegriffe</span><div className="content-search-input-wrap"><Icon name="search" size={19}/><input ref={searchInput} id={`${id}-query`} type="search" aria-label="Suchbegriffe" value={draft} onChange={event => setDraft(event.target.value)} placeholder="z. B. soziales Kapital" maxLength={maxQueryLength} autoComplete="off" spellCheck={false} aria-describedby={`${id}-hint`}/>{draft && <button type="button" className="icon-button" onClick={clear} aria-label="Suchbegriffe löschen"><Icon name="close" size={17}/></button>}</div></label>
        <label className="content-search-module" htmlFor={`${id}-module`}><span>Studienmodul</span><select id={`${id}-module`} value={moduleId} onChange={event => changeModule(event.target.value)}><option value="">Alle Module</option>{modules.map(module => <option key={module.id} value={module.id}>{module.name}{module.number ? ` · ${module.number}` : ''}</option>)}</select></label>
        <Button type="submit" disabled={draft.trim().length < minQueryLength}><Icon name="search" size={17}/>Suchen</Button>
        <small id={`${id}-hint`} className="content-search-hint">Mehrere Wörter grenzen die Suche ein. Groß- und Kleinschreibung spielen keine Rolle.</small>
      </form>
      <div className="content-search-results" aria-busy={loading}>
        {!hasSearched && !error && <div className="content-search-empty"><span><Icon name="book" size={28}/></span><h3>Die passende Stelle finden</h3><p>Suche nach einem Fachbegriff oder nach wichtigen Wörtern aus deiner Aufgabe. Die Treffer zeigen dir den Zusammenhang und führen direkt zum Abschnitt oder zur Datei.</p></div>}
        {loading && !response && <div className="content-search-loading" role="status"><span className="spinner"/> Deine Inhalte werden durchsucht …</div>}
        {response && <>
          <div className="content-search-result-summary" role="status"><strong>{response.total === 1 ? '1 Fundstelle' : `${response.total} Fundstellen`}</strong><span>für „{response.query}“{response.total > count ? ` · ${count} angezeigt` : ''}</span></div>
          {!response.total && <div className="content-search-empty"><span><Icon name="search" size={28}/></span><h3>Keine passende Stelle gefunden</h3><p>Versuche einen kürzeren Begriff, andere Wörter oder die Suche in allen Modulen.</p>{moduleId && <Button className="secondary" onClick={() => changeModule('')}>In allen Modulen suchen</Button>}</div>}
          <div className="content-search-list">{response.results.map(result => {
            const isOriginal = result.kind === 'document';
            const primarySource = result.source || result.sources?.[0];
            const heading = result.section_title || result.title;
            return <article className="content-search-result" key={result.id}>
              <div className="content-search-result-meta"><span className={`content-search-kind ${isOriginal ? 'original' : ''}`}>{isOriginal ? 'Unterlage' : result.kind === 'concept' ? 'Big Picture' : 'Lernseite'}</span><span>{result.module_title}{result.unit ? ` · ${unitLabel(result)} ${result.unit}` : ''}</span></div>
              {result.section_title && result.title !== result.section_title && <div className="content-search-chapter"><Highlight text={result.title} terms={response.terms}/></div>}
              <h3>{isOriginal && primarySource ? <a href={`/api/source${query({ path: primarySource.path })}${primarySource.kind !== 'video' && primarySource.kind !== 'document' ? `#page=${primarySource.pdf_page}` : ''}`} target="_blank" rel="noreferrer"><Highlight text={heading} terms={response.terms}/><Icon name="arrow" size={17}/></a> : <button type="button" onClick={() => onOpenResult(result)}><Highlight text={heading} terms={response.terms}/><Icon name="arrow" size={17}/></button>}</h3>
              <p className="content-search-snippet"><Highlight text={result.snippet} terms={response.terms}/></p>
              <div className="content-search-result-links">{!isOriginal && <button type="button" className="text-button" onClick={() => onOpenResult(result)}>{result.kind === 'concept' ? 'Im Big Picture öffnen' : 'Zum Lernabschnitt'}<Icon name="arrow" size={15}/></button>}{primarySource && <SearchSource source={primarySource} original={isOriginal}/>}</div>
            </article>;
          })}</div>
          {more && <div className="content-search-more"><Button className="secondary" disabled={loading} onClick={() => { if (lastRequest.current) void search({ ...lastRequest.current, offset: count }); }}>{loading ? 'Weitere Treffer werden geladen …' : 'Weitere Treffer anzeigen'}</Button><small>{count} von {response.total} Fundstellen</small></div>}
          {response.notice && <p className="content-search-notice">{response.notice}</p>}
        </>}
        {error && <div className="content-search-error" role="alert"><strong>Die Suche hat nicht geklappt.</strong><p>{error}</p>{hasSearched && lastRequest.current && <Button className="secondary small" onClick={() => { if (lastRequest.current) void search(lastRequest.current); }}>Erneut versuchen</Button>}</div>}
      </div>
    </div>
  </dialog>;
}
