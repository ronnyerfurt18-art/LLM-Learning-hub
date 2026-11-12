import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorText } from './api';
import { Badge, Button, Icon } from './components';
import { DevelopmentEdit, DevelopmentJob, DevelopmentOverview, DevelopmentRequest } from './types';
import './devchat.css';

const POLL_MS = 1500;
const KEY = 'mlh-dev-chat';
const SHOWN = 500;
const enc = encodeURIComponent;

function remembered() {
  try {
    return localStorage.getItem(KEY) || '';
  } catch {
    return '';
  }
}

function remember(id: string) {
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {
    // Without storage the chat simply starts empty after a reload.
  }
}

function cut(text: string) {
  return text.length > SHOWN ? `${text.slice(0, SHOWN)} …` : text;
}

function EditView({ edit }: { edit: DevelopmentEdit }) {
  return <div className={`dev-chat-edit${edit.ok ? '' : ' is-bad'}`}>
    <div><code>{edit.path}</code> {!edit.ok && <Badge tone="red">nicht übernehmbar</Badge>}</div>
    {edit.reason && <p>{edit.reason}</p>}
    {!edit.ok && edit.problem && <p className="dev-chat-problem">{edit.problem}</p>}
    <pre className="dev-chat-old" aria-label="Bisher">{cut(edit.search)}</pre>
    <pre className="dev-chat-new" aria-label="Neu">{cut(edit.replace)}</pre>
  </div>;
}

/** Opened from the development button in the top bar; shown at the top right, below the bar. */
export function DevChat({ open, onClose, onOpenPage, onWorking }: {
  open: boolean; onClose: () => void; onOpenPage: () => void; onWorking?: (working: boolean) => void;
}) {
  const [id, setId] = useState(remembered);
  const [request, setRequest] = useState<DevelopmentRequest | null>(null);
  const [job, setJob] = useState<DevelopmentJob>({ state: 'idle', message: '' });
  const [modelMessage, setModelMessage] = useState('');
  const [text, setText] = useState('');
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [tick, setTick] = useState(0);
  const idRef = useRef(id);
  idRef.current = id;
  const endRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const overview = await api<DevelopmentOverview>('/development');
      setJob(overview.job);
      setModelMessage(overview.model_message);
      setRequest(idRef.current ? await api<DevelopmentRequest>(`/development/requests/${enc(idRef.current)}`) : null);
      return overview.job.state === 'running';
    } catch (problem) {
      setError(errorText(problem));
      return false;
    }
  }, []);

  // Look once when the chat opens or something was done, then every 1.5 seconds while the hub works.
  useEffect(() => {
    if (!open) return;
    let active = true;
    let timer: number | undefined;
    const loop = async () => {
      const running = await load();
      if (active && running) timer = window.setTimeout(loop, POLL_MS);
    };
    loop();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [open, id, tick, load]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [request, job.message, error]);

  const go = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    setCopied('');
    try {
      await work();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setBusy(false);
      setTick(value => value + 1);
    }
  };
  const path = (tail = '') => `/development/requests/${enc(id)}${tail}`;
  const ask = () => go(async () => {
    const started = await api<{ id: string }>('/development/ask', { text });
    setText('');
    remember(started.id);
    setId(started.id);
  });
  const approve = () => go(async () => {
    await api(path('/proposal/apply'), {});
    await api(path('/verify'), {});
  });
  const reply = () => go(async () => {
    await api(path(), { note: [request?.note, answer.trim()].filter(Boolean).join('\n') }, 'PATCH');
    setAnswer('');
    await api(path('/proposal'), {});
  });
  const fresh = () => {
    remember('');
    setId('');
    setRequest(null);
    setError('');
    setText('');
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(request?.prompt || '');
      setCopied('Prompt kopiert. Füge ihn in Cowork oder Codex ein.');
    } catch {
      setCopied('Kopieren ging nicht. Öffne die Anforderung unter „Alle Anforderungen“ und kopiere den Prompt dort.');
    }
  };

  const mine = !!id && job.request_id === id;
  const working = job.state === 'running';
  const workingHere = working && mine;
  const proposal = request?.proposal || null;
  const applied = proposal?.state === 'applied';
  const done = applied && request?.outcome.tone === 'green' && !workingHere;
  const lock = modelMessage && !working ? modelMessage : '';
  const jobError = job.state === 'error' && mine ? job.message : '';

  useEffect(() => {
    onWorking?.(workingHere);
  }, [workingHere, onWorking]);

  return <>
    {open && <section className="dev-chat" role="dialog" aria-label="Entwicklung" aria-modal="false" onKeyDown={event => { if (event.key === 'Escape') onClose(); }}>
      <header className="dev-chat-head">
        <strong>Entwicklung</strong>
        <span className="dev-chat-tools">
          <button type="button" className="link-button" onClick={fresh} disabled={workingHere}>Neue Aufgabe</button>
          <button type="button" className="link-button" onClick={onOpenPage}>Alle Anforderungen</button>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Entwicklung schließen"><Icon name="close" size={16} /></button>
        </span>
      </header>
      <div className="dev-chat-body" aria-live="polite">
        {!request && <div className="dev-chat-bubble hub">
          <p>Sag mir, was am Hub anders werden soll. Ich arbeite es aus, schlage die Änderung vor und melde dir am Ende, ob sie erledigt ist oder nicht.</p>
          <p className="muted">Beschreibe es in Worten, zum Beispiel: „Das Menü im Hellmodus soll etwas heller grün sein.“ Code musst du nicht einfügen.</p>
        </div>}
        {request && <div className="dev-chat-bubble me">{request.text}</div>}
        {request?.order && <div className="dev-chat-bubble hub">
          <p><strong>Auftrag:</strong> {request.order.title}</p>
          {request.order.route === 'local'
            ? <p>Das kann ich lokal lösen.</p>
            : <><p>Das lässt sich nicht lokal lösen. Dafür liegt ein Prompt für eine externe KI bereit.</p>
              <ul>{request.order.route_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
              <div className="button-row">
                <Button className="secondary small" onClick={copy}><Icon name="file" size={14} /> Prompt kopieren</Button>
              </div>
              {copied && <p className="muted" role="status">{copied}</p>}</>}
        </div>}
        {proposal?.state === 'open' && proposal.edits.length > 0 && <div className="dev-chat-bubble hub">
          <p><strong>Vorschlag von {proposal.generated_by}</strong></p>
          {proposal.edits.map((edit, index) => <EditView key={`${edit.path}-${index}`} edit={edit} />)}
          {proposal.warnings.map(warning => <p key={warning} className="dev-chat-problem">{warning}</p>)}
          <p className="muted">Der Hub schreibt erst nach deiner Freigabe, legt vorher eine Sicherung an und prüft danach, ob alles baut.</p>
          <div className="button-row">
            <Button onClick={approve} disabled={busy || working || !proposal.edits.some(edit => edit.ok)}>Übernehmen und prüfen</Button>
            <Button className="secondary" onClick={() => go(() => api(path('/proposal/discard'), {}))} disabled={busy || working}>Verwerfen</Button>
          </div>
        </div>}
        {proposal?.state === 'open' && proposal.edits.length === 0 && <div className="dev-chat-bubble hub">
          <p><strong>Rückfrage:</strong> {proposal.question}</p>
          <textarea rows={2} value={answer} onChange={event => setAnswer(event.target.value)} aria-label="Deine Antwort" />
          <div className="button-row">
            <Button onClick={reply} disabled={busy || working || answer.trim().length === 0}>Antworten</Button>
          </div>
        </div>}
        {workingHere && <div className="dev-chat-bubble hub working" role="status"><span className="dev-spinner" aria-hidden="true" /> {job.message}</div>}
        {(request?.error || request?.change_error || jobError) && !workingHere && !applied && <div className="dev-chat-bubble hub bad" role="alert">
          <strong>Das hat nicht geklappt.</strong> {jobError || request?.change_error || request?.error}
        </div>}
        {applied && request && !workingHere && <div className={`dev-chat-verdict ${done ? 'ok' : 'open'}`} role="status">
          <strong>{done ? '✓ Erledigt' : '✗ Noch nicht erledigt'}</strong>
          <span>{request.outcome.label}</span>
          <ul>{request.outcome.checks.map(check => <li key={check.text}>
            <span className={check.ok ? 'dev-ok' : 'dev-open'}>{check.ok ? '✓' : '✗'}</span> {check.text}
            {!check.ok && check.hint && <small>{check.hint}</small>}
          </li>)}</ul>
          <div className="button-row">
            <Button className="secondary small" onClick={() => setTick(value => value + 1)} disabled={busy}><Icon name="refresh" size={14} /> Stand neu prüfen</Button>
            {proposal?.verify && !done && <Button className="secondary small" onClick={() => go(() => api(path('/verify'), {}))} disabled={busy || working}>Prüfung wiederholen</Button>}
            <Button className="secondary small" onClick={() => go(() => api(path('/proposal/revert'), {}))} disabled={busy || working}>Zurücknehmen</Button>
          </div>
        </div>}
        {proposal?.state === 'reverted' && !workingHere && <div className="dev-chat-verdict open" role="status">
          <strong>Zurückgenommen</strong><span>{request?.outcome.label}</span>
          <ul>{request?.outcome.checks.map(check => <li key={check.text}>✗ {check.text}{check.hint && <small>{check.hint}</small>}</li>)}</ul>
        </div>}
        {error && <div className="dev-chat-bubble hub bad" role="alert">{error}</div>}
        <div ref={endRef} />
      </div>
      <footer className="dev-chat-foot">
        {lock && <p className="dev-chat-problem">{lock}</p>}
        {!request
          ? <>
            <textarea rows={3} value={text} onChange={event => setText(event.target.value)} maxLength={4000} aria-label="Was soll anders werden?"
              placeholder="Was soll am Hub anders werden?" />
            <div className="button-row">
              <Button onClick={ask} disabled={busy || working || !!lock || text.trim().length < 10}><Icon name="arrow" size={14} /> Aufgabe abschicken</Button>
              {text.trim().length > 0 && text.trim().length < 10 && <span className="muted">Mindestens 10 Zeichen.</span>}
              {working && !mine && <span className="muted">Der Hub arbeitet gerade an einer anderen Aufgabe.</span>}
            </div>
          </>
          : <p className="muted">Für eine weitere Aufgabe oben „Neue Aufgabe“ wählen.</p>}
      </footer>
    </section>}
  </>;
}
