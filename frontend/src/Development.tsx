import { useEffect, useRef, useState } from 'react';
import { api, errorText, formatDate } from './api';
import { Badge, Button, Empty, ErrorBox, Field, Icon, Loading, PageTitle } from './components';
import {
  AppSettings, DevelopmentJob, DevelopmentOrder, DevelopmentOverview, DevelopmentRequest, DevelopmentStatus, DevelopmentSummary,
} from './types';
import './development.css';

const POLL_MS = 2000;
const TEXT_MIN = 10;
const TEXT_MAX = 4000;
const NOTE_MAX = 2000;
const STATUS: Record<DevelopmentStatus, { label: string; tone: 'neutral' | 'green' | 'yellow' | 'red' | 'teal' }> = {
  new: { label: 'Neu', tone: 'neutral' },
  drafted: { label: 'Auftrag liegt vor', tone: 'teal' },
  handed_over: { label: 'Übergeben', tone: 'yellow' },
  done: { label: 'Umgesetzt', tone: 'green' },
  dropped: { label: 'Verworfen', tone: 'red' },
};
const CLOSED: DevelopmentStatus[] = ['done', 'dropped'];
const enc = encodeURIComponent;

function routeLabel(route: 'local' | 'external') {
  return route === 'local' ? 'Lokal machbar' : 'Extern übergeben';
}

export function DevelopmentPage({ settings }: { settings: AppSettings | null }) {
  return <>
    <PageTitle
      eyebrow="HUB WEITERENTWICKELN"
      title="Entwicklung"
      description="Halte fest, was am Hub anders werden soll. Das KI-Modell arbeitet daraus einen Auftrag aus, der Hub stuft ihn ein und schreibt den Prompt für eine externe KI." />
    {settings === null ? <Loading /> : !settings.features.includes('development')
      ? <Empty icon="code" title="Diese Funktion ist ausgeschaltet">Der Bereich Entwicklung ist in diesem Hub nicht aktiv.</Empty>
      : <Workspace />}
  </>;
}

function Workspace() {
  const [overview, setOverview] = useState<DevelopmentOverview | null>(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<DevelopmentRequest | null>(null);
  const [detailError, setDetailError] = useState('');
  const [showClosed, setShowClosed] = useState(false);
  const [watch, setWatch] = useState(0);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const loadDetail = async (id: string) => {
    if (!id) {
      setDetail(null);
      return;
    }
    try {
      const next = await api<DevelopmentRequest>(`/development/requests/${enc(id)}`);
      if (selectedRef.current === id) {
        setDetail(next);
        setDetailError('');
      }
    } catch (problem) {
      if (selectedRef.current === id) setDetailError(errorText(problem));
    }
  };

  // Ask once on arrival (a running job shows up again after a reload), then every 2 seconds while the model works.
  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let wasRunning = false;
    const tick = async () => {
      try {
        const next = await api<DevelopmentOverview>('/development');
        if (!active) return;
        setOverview(next);
        setError('');
        if (next.job.state === 'running') {
          wasRunning = true;
          timer = window.setTimeout(tick, POLL_MS);
        } else if (wasRunning) {
          loadDetail(selectedRef.current);
        }
      } catch (problem) {
        if (!active) return;
        setError(errorText(problem));
        if (wasRunning) timer = window.setTimeout(tick, POLL_MS);
      }
    };
    tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [watch]);

  useEffect(() => {
    setDetail(null);
    setDetailError('');
    loadDetail(selected);
  }, [selected]);

  const refresh = () => setWatch(value => value + 1);
  const created = (request: DevelopmentRequest) => {
    setSelected(request.id);
    refresh();
  };
  const changed = (request: DevelopmentRequest) => {
    setDetail(request);
    refresh();
  };

  if (error && !overview) return <ErrorBox error={error} retry={refresh} />;
  if (!overview) return <Loading />;
  const closedCount = overview.requests.filter(item => CLOSED.includes(item.status)).length;
  const shown = overview.requests.filter(item => showClosed || !CLOSED.includes(item.status) || item.id === selected);
  return <>
    {error && <ErrorBox error={error} retry={refresh} />}
    <NewRequest onCreated={created} />
    <section className="card dev-step" aria-labelledby="dev-list-title">
      <div className="section-head">
        <h2 id="dev-list-title"><span className="dev-number">2</span> Anforderungen</h2>
        {closedCount > 0 && <label className="dev-toggle">
          <input type="checkbox" checked={showClosed} onChange={event => setShowClosed(event.target.checked)} />
          <span>Umgesetzte und verworfene zeigen ({closedCount})</span>
        </label>}
      </div>
      {overview.requests.length === 0
        ? <p className="muted">Noch keine Anforderungen. Schreib oben auf, was am Hub anders werden soll.</p>
        : shown.length === 0
          ? <p className="muted">Alle Anforderungen sind umgesetzt oder verworfen.</p>
          : <RequestList requests={shown} selected={selected} job={overview.job} onSelect={setSelected} />}
    </section>
    {selected && <section className="card dev-step" aria-labelledby="dev-detail-title">
      {detailError && <ErrorBox error={detailError} retry={() => loadDetail(selected)} />}
      {!detail && !detailError && <Loading />}
      {detail && <Detail key={detail.id} request={detail} overview={overview} onChanged={changed} onStarted={refresh} />}
    </section>}
  </>;
}

function NewRequest({ onCreated }: { onCreated: (request: DevelopmentRequest) => void }) {
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const length = text.trim().length;
  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const request = await api<DevelopmentRequest>('/development/requests', title.trim() ? { title: title.trim(), text } : { text });
      setTitle('');
      setText('');
      onCreated(request);
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setSaving(false);
    }
  };
  return <section className="card dev-step" aria-labelledby="dev-new-title">
    <h2 id="dev-new-title"><span className="dev-number">1</span> Neue Anforderung</h2>
    <Field label="Was soll anders werden?" hint={`Beschreibe, was du erreichen willst und woran du merkst, dass es klappt. ${length} von ${TEXT_MAX} Zeichen.`}>
      <textarea rows={5} maxLength={TEXT_MAX} value={text} onChange={event => setText(event.target.value)}
        placeholder="Zum Beispiel: Im Lernchat soll unter jeder Antwort stehen, wie lange das KI-Modell dafür gebraucht hat." />
    </Field>
    <Field label="Titel (optional)" hint="Ohne Titel übernimmt der Hub später den Titel des Auftrags.">
      <input type="text" maxLength={120} value={title} onChange={event => setTitle(event.target.value)} />
    </Field>
    {error && <ErrorBox error={error} />}
    <div className="button-row">
      <Button onClick={save} disabled={saving || length < TEXT_MIN}><Icon name="plus" size={16} /> {saving ? 'Speichert …' : 'Anforderung speichern'}</Button>
      {length > 0 && length < TEXT_MIN && <span className="muted">Mindestens {TEXT_MIN} Zeichen.</span>}
    </div>
  </section>;
}

function RequestList({ requests, selected, job, onSelect }: {
  requests: DevelopmentSummary[]; selected: string; job: DevelopmentJob; onSelect: (id: string) => void;
}) {
  return <ul className="dev-list">
    {requests.map(item => {
      const running = job.state === 'running' && job.request_id === item.id;
      return <li key={item.id}>
        <button type="button" className={`dev-row${selected === item.id ? ' is-selected' : ''}`} aria-pressed={selected === item.id}
          onClick={() => onSelect(selected === item.id ? '' : item.id)}>
          <span className="dev-row-id">{item.id}</span>
          <span className="dev-row-title">{item.title}</span>
          <span className="dev-row-meta">
            {running && <Badge tone="yellow">KI-Modell arbeitet …</Badge>}
            <Badge tone={STATUS[item.status].tone}>{STATUS[item.status].label}</Badge>
            {item.route && <Badge>{routeLabel(item.route)}</Badge>}
            <span className="muted">{formatDate(item.created_at)}</span>
          </span>
        </button>
      </li>;
    })}
  </ul>;
}

function Detail({ request, overview, onChanged, onStarted }: {
  request: DevelopmentRequest; overview: DevelopmentOverview; onChanged: (request: DevelopmentRequest) => void; onStarted: () => void;
}) {
  const [note, setNote] = useState(request.note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState('');
  const [copied, setCopied] = useState('');
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const job = overview.job;
  const running = job.state === 'running';
  const runningHere = running && job.request_id === request.id;
  const order = request.order;

  const patch = async (value: Record<string, string>) => {
    setBusy(true);
    setError('');
    try {
      onChanged(await api<DevelopmentRequest>(`/development/requests/${enc(request.id)}`, value, 'PATCH'));
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setBusy(false);
    }
  };
  const draft = async () => {
    setBusy(true);
    setError('');
    setBlocked('');
    try {
      await api<DevelopmentJob>(`/development/requests/${enc(request.id)}/order`, {});
      onStarted();
    } catch (problem) {
      const text = errorText(problem);
      if (/Ollama|KI-Modell/.test(text)) setBlocked(text);
      else setError(text);
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(request.prompt);
      setCopied('Prompt kopiert. Füge ihn in Cowork oder Codex ein.');
    } catch {
      // Without clipboard access the text is selected, so Cmd+C works.
      promptRef.current?.focus();
      promptRef.current?.select();
      setCopied('Der Prompt ist markiert. Kopiere ihn mit Cmd+C.');
    }
  };

  const lock = blocked || overview.model_message;
  return <>
    <div className="section-head dev-detail-head">
      <h2 id="dev-detail-title"><span className="dev-number">3</span> {request.id}: {request.title}</h2>
      <label className="dev-status">
        <span>Status</span>
        <select value={request.status} disabled={busy} onChange={event => patch({ status: event.target.value })}>
          {(Object.keys(STATUS) as DevelopmentStatus[]).map(key => <option key={key} value={key}>{STATUS[key].label}</option>)}
        </select>
      </label>
    </div>
    {error && <ErrorBox error={error} />}

    <h3>Anforderung im Wortlaut</h3>
    <p className="dev-text">{request.text}</p>
    <Field label="Ergänzung" hint="Nachträge und Antworten auf offene Fragen. Die Ergänzung geht an das KI-Modell und in den Prompt.">
      <textarea rows={3} maxLength={NOTE_MAX} value={note} onChange={event => setNote(event.target.value)} />
    </Field>
    {note.trim() !== request.note && <div className="button-row dev-note-save">
      <Button className="secondary small" onClick={() => patch({ note })} disabled={busy}>Ergänzung speichern</Button>
      {order && <span className="muted">Der Auftrag berücksichtigt die Ergänzung erst, wenn du ihn neu ausarbeiten lässt.</span>}
    </div>}

    <h3>Auftrag</h3>
    {lock && <div className="alert warning" role="alert"><strong>Das KI-Modell steht nicht bereit.</strong><span>{lock}</span></div>}
    {runningHere && <p className="dev-live" role="status" aria-live="polite">{job.message}</p>}
    {running && !runningHere && <div className="alert info" role="status">Für {job.request_id} wird gerade ein Auftrag ausgearbeitet. Warte, bis er fertig ist.</div>}
    {!runningHere && request.error && <div className="alert error" role="alert">
      <strong>Der letzte Versuch ist fehlgeschlagen.</strong><span>{request.error}</span>
    </div>}
    {!order && !runningHere && <p className="muted">Noch kein Auftrag. Das KI-Modell sieht dafür die Anforderung, die Dateinamen des Programms und einen Auszug aus dem Architekturlog, aber keinen Quelltext und keine Lernunterlagen.</p>}
    {order && <Order order={order} busy={busy || running} onRoute={route => patch({ route })} />}
    <div className="button-row">
      <Button className={order ? 'secondary' : ''} onClick={draft} disabled={busy || running || !overview.model_available}>
        <Icon name={order ? 'refresh' : 'learn'} size={16} /> {order ? 'Auftrag neu ausarbeiten' : 'Auftrag ausarbeiten'}
      </Button>
      {order && <span className="muted">Ein neuer Auftrag ersetzt den bisherigen.</span>}
    </div>

    <h3>Prompt für eine externe KI</h3>
    <p className="muted">Der Hub schreibt den Prompt selbst aus Anforderung, Auftrag und Projektregeln ({overview.rules_source}). Er enthält keine Lernunterlagen und verlässt den Hub erst, wenn du ihn kopierst.</p>
    <textarea ref={promptRef} className="dev-prompt" readOnly rows={14} value={request.prompt} aria-label="Prompt für eine externe KI" />
    <div className="button-row">
      <Button onClick={copy}><Icon name="file" size={16} /> Prompt kopieren</Button>
      {request.status !== 'handed_over' && !CLOSED.includes(request.status) &&
        <Button className="secondary" onClick={() => patch({ status: 'handed_over' })} disabled={busy}>Als übergeben markieren</Button>}
    </div>
    <p className="dev-live muted" role="status" aria-live="polite">{copied}</p>
  </>;
}

function Order({ order, busy, onRoute }: { order: DevelopmentOrder; busy: boolean; onRoute: (route: 'local' | 'external') => void }) {
  const other = order.route === 'local' ? 'external' : 'local';
  return <div className="dev-order">
    <div className={`dev-route ${order.route}`}>
      <div className="dev-route-head">
        <strong>{routeLabel(order.route)}</strong>
        <span className="muted">{order.route_by === 'user' ? 'von dir festgelegt' : 'Einstufung des Hubs'}</span>
        <Button className="secondary small" onClick={() => onRoute(other)} disabled={busy}>
          {other === 'local' ? 'Als lokal machbar einstufen' : 'Als extern einstufen'}
        </Button>
      </div>
      {order.route_by === 'hub' && <ul>{order.route_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      {order.route === 'local' && <p>Die Umsetzung durch das lokale KI-Modell ist noch nicht eingebaut. Setze die Änderung selbst um oder gib sie mit dem Prompt unten weiter.</p>}
    </div>
    <h4>Ziel</h4>
    <p>{order.goal}</p>
    <h4>Voraussichtlich betroffene Dateien</h4>
    {order.files.length === 0
      ? <p className="muted">Keine Datei ließ sich im Projekt belegen.</p>
      : <ul className="dev-files">
        {order.files.map(file => <li key={file.path}>
          <code>{file.path}</code>{file.new && <Badge tone="teal">neu</Badge>}
          {file.change && <span>{file.change}</span>}
        </li>)}
      </ul>}
    {order.dropped_files.length > 0 && <p className="dev-dropped">
      Vom KI-Modell genannt, im Projekt aber nicht vorhanden und deshalb weggelassen: {order.dropped_files.join(', ')}
    </p>}
    {order.tests.length > 0 && <>
      <h4>Zugehörige Tests</h4>
      <ul className="dev-files">{order.tests.map(path => <li key={path}><code>{path}</code></li>)}</ul>
    </>}
    <h4>Schritte</h4>
    <ol>{order.steps.map(step => <li key={step}>{step}</li>)}</ol>
    <h4>Abnahmekriterien</h4>
    <ul>{order.acceptance.map(item => <li key={item}>{item}</li>)}</ul>
    {order.risks.length > 0 && <>
      <h4>Risiken</h4>
      <ul>{order.risks.map(item => <li key={item}>{item}</li>)}</ul>
    </>}
    {order.questions.length > 0 && <>
      <h4>Offene Fragen</h4>
      <ul>{order.questions.map(item => <li key={item}>{item}</li>)}</ul>
    </>}
    <p className="dev-origin muted">
      Entwurf: {order.generated_by}, {formatDate(order.created_at)}. Umfang laut KI-Modell: {order.size === 'gross' ? 'groß' : order.size}{order.reason ? ` (${order.reason})` : ''}.
      Das KI-Modell kannte nur die Dateinamen; prüfe den Auftrag, bevor du ihn weitergibst.
    </p>
  </div>;
}
