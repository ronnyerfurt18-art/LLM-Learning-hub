import { useEffect, useRef, useState } from 'react';
import { api, errorText } from './api';
import { Badge, Button, Empty, ErrorBox, Field, Icon, Loading, Modal, PageTitle, Progress, useLoad } from './components';
import {
  AppSettings, BigPictureInfo, DocumentKind, ImportDocument, ImportOverview, ImportPreview, ImportPublishResult, ImportStatus,
  LearningPagesPackage, LearningPagesSummary, Module, UploadResult,
} from './types';
import { unitLabel, unitLabelPlural } from './unitLabel';
import { ModuleEditor } from './Overview';
import { RemoveResult, removeText } from './Documents';
import './module-import.css';

const EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx', '.txt', '.md', '.markdown', '.mp4'];
const MAX_MB = 300;
const POLL_MS = 2000;

type Labels = { one: string; many: string };
type UploadRow = {
  id: number;
  file: File;
  state: 'waiting' | 'running' | 'done' | 'error';
  message: string;
  unit?: number | null;
  requested?: number | null;
};

const enc = encodeURIComponent;

function list(numbers: number[]) {
  return numbers.join(', ');
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : 1));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

async function uploadFile(moduleId: string, file: File, unit: string): Promise<UploadResult> {
  const query = `module_id=${enc(moduleId)}&filename=${enc(file.name)}${unit ? `&unit=${enc(unit)}` : ''}`;
  const response = await fetch(`/api/documents/upload?${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  });
  if (!response.ok) {
    let message = `Der Upload ist fehlgeschlagen (${response.status}).`;
    try {
      const detail = (await response.json()).detail;
      message = typeof detail === 'string' ? detail : JSON.stringify(detail) || message;
    } catch {
      // The server did not send JSON; the generic message stays.
    }
    throw new Error(message);
  }
  return response.json();
}

export function ModuleImportPage({ modules, moduleId, settings, onSelect, onChange }: {
  modules: Module[];
  moduleId: string;
  settings: AppSettings | null;
  onSelect: (moduleId: string) => void;
  onChange: () => void;
}) {
  const module = modules.find(item => item.id === moduleId);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [created, setCreated] = useState('');
  const newModule = <Button className="secondary" onClick={() => { setCreated(''); setCreating(true); }}><Icon name="plus" size={16} /> Neues Modul anlegen</Button>;
  return <>
    <PageTitle
      eyebrow="UNTERLAGEN AUFBEREITEN"
      title="Aufbereiten"
      description="Lade Lehrbriefe hoch, lass das KI-Modell daraus Lernseiten und Fragen entwerfen und prüfe alles, bevor du es veröffentlichst." />
    {settings === null ? <Loading /> : !settings.features.includes('module_import')
      ? <Empty icon="upload" title="Diese Funktion ist ausgeschaltet">Das Aufbereiten von Unterlagen ist in diesem Hub nicht aktiv.</Empty>
      : <>
        <section className="card import-step" aria-labelledby="import-module-title">
          <h2 id="import-module-title"><span className="import-number">1</span> Modul wählen</h2>
          {modules.length === 0
            ? <p className="muted">Es gibt noch keine Module. Lege hier ein neues Modul an, dann kannst du direkt Unterlagen hochladen.</p>
            : <Field label="Modul" hint="Für neue Unterlagen ohne bestehendes Modul legst du zuerst ein neues Modul an. Der Ordner für die Uploads entsteht automatisch.">
              <select value={moduleId} onChange={event => { setCreated(''); onSelect(event.target.value); }}>
                <option value="">Bitte ein Modul wählen</option>
                {modules.map(item => <option key={item.id} value={item.id}>{item.number ? `${item.number} ` : ''}{item.name}</option>)}
              </select>
            </Field>}
          <div className="button-row">{newModule}{module && <Button className="secondary" onClick={() => setEditing(true)}>Modulangaben bearbeiten</Button>}</div>
          <p className="muted">Name und Kennung kannst du selbst eintragen oder später ändern. Eine Modulnummer ist nicht erforderlich. Nicht erkannte Dokumentzuordnungen lassen sich unter „Dokumente“ ergänzen.</p>
          {created && <p className="import-live muted" role="status" aria-live="polite">{created}</p>}
        </section>
        {editing && module && <ModuleEditor module={module} close={() => setEditing(false)} save={() => {
          setEditing(false);
          setCreated('Modulangaben gespeichert. Bestehende Lernseiten bleiben zugeordnet.');
          onChange();
        }} />}
        {creating && <ModuleEditor module={null} close={() => setCreating(false)} save={saved => {
          setCreating(false);
          onChange();
          if (saved) {
            setCreated(`Modul „${saved.name}“ ist angelegt und ausgewählt. Lade jetzt in Schritt 2 die Unterlagen hoch.`);
            onSelect(saved.id);
          }
        }} />}
        {module
          ? <Workspace key={module.id} module={module} settings={settings} onChange={onChange} />
          : modules.length > 0 && <Empty icon="file" title="Noch kein Modul gewählt">Wähle oben ein Modul, dann siehst du seine Unterlagen und Einheiten.</Empty>}
      </>}
  </>;
}

function Workspace({ module, settings, onChange }: { module: Module; settings: AppSettings; onChange: () => void }) {
  const labels: Labels = { one: unitLabel(module), many: unitLabelPlural(module) };
  const overview = useLoad(() => api<ImportOverview>(`/module-import/overview?module_id=${enc(module.id)}`), [module.id, module.name, module.number]);
  const reloadRef = useRef(overview.reload);
  reloadRef.current = overview.reload;
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [bigPictureBusy, setBigPictureBusy] = useState(false);
  const tutor = settings.tutor;
  const tutorBlock = tutor && tutor.readiness && tutor.readiness !== 'ready' ? (tutor.message || 'Das KI-Modell ist gerade nicht bereit.') : '';
  const refresh = () => {
    reloadRef.current();
    onChange();
  };
  return <>
    <UploadSection module={module} labels={labels} overview={overview.data} onUploaded={() => reloadRef.current()} />
    <UnitsSection labels={labels} overview={overview} selected={selected} onSelect={setSelected} />
    {overview.data && <ProcessSection
      module={module} labels={labels} overview={overview.data} selected={selected} tutorBlock={tutorBlock} pictureBusy={bigPictureBusy}
      onBusy={setBusy} onRefresh={refresh} />}
    {settings.features.includes('big_picture') && overview.data &&
      <BigPictureSection module={module} labels={labels} overview={overview.data} tutorBlock={tutorBlock} importBusy={busy}
        onBusy={setBigPictureBusy} onRefresh={refresh} />}
  </>;
}

function UploadSection({ module, labels, overview, onUploaded }: {
  module: Module; labels: Labels; overview: ImportOverview | null; onUploaded: () => void;
}) {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [unit, setUnit] = useState('');
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const counter = useRef(0);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  const highest = Math.max(module.unit_count || 0, ...(overview?.units.map(item => item.unit) || [0]));
  const patch = (id: number, values: Partial<UploadRow>) => {
    if (alive.current) setRows(items => items.map(item => (item.id === id ? { ...item, ...values } : item)));
  };
  const choose = (files: FileList | null) => {
    const added = Array.from(files || []).map(file => ({ id: ++counter.current, file, state: 'waiting' as const, message: '' }));
    setRows(items => [...items.filter(item => item.state !== 'done'), ...added]);
    setStatus('');
  };
  const upload = async () => {
    setUploading(true);
    let done = 0;
    let failed = 0;
    for (const row of rows.filter(item => item.state === 'waiting' || item.state === 'error')) {
      patch(row.id, { state: 'running', message: '' });
      try {
        const result = await uploadFile(module.id, row.file, unit);
        patch(row.id, { state: 'done', unit: result.unit, requested: result.requested_unit });
        done += 1;
      } catch (error) {
        patch(row.id, { state: 'error', message: errorText(error) });
        failed += 1;
      }
    }
    if (!alive.current) return;
    setUploading(false);
    if (input.current) input.current.value = '';
    setStatus(`${done} ${done === 1 ? 'Datei' : 'Dateien'} hochgeladen${failed ? `, ${failed} mit Fehler` : ''}.`);
    onUploaded();
  };
  const pending = rows.filter(item => item.state === 'waiting' || item.state === 'error').length;
  return <section className="card import-step" aria-labelledby="import-upload-title">
    <h2 id="import-upload-title"><span className="import-number">2</span> Unterlagen hochladen</h2>
    <div className="import-upload-controls">
      <Field label="Dateien" hint={`Erlaubt: ${EXTENSIONS.join(', ')}. Höchstens ${MAX_MB} MB je Datei.`}>
        <input ref={input} type="file" multiple disabled={uploading} onChange={event => choose(event.target.files)} />
      </Field>
      <Field label={labels.one} hint={`Bei „automatisch erkennen“ liest der Hub die ${labels.one} aus dem Dateinamen.`}>
        <select value={unit} disabled={uploading} onChange={event => setUnit(event.target.value)}>
          <option value="">Automatisch erkennen</option>
          {Array.from({ length: highest + 1 }, (_, index) => index + 1).map(number =>
            <option key={number} value={number}>{labels.one} {number}</option>)}
        </select>
      </Field>
    </div>
    {rows.length > 0 && <ul className="import-files" aria-label="Ausgewählte Dateien">
      {rows.map(row => <li key={row.id} className={`import-file ${row.state}`}>
        <span className="import-file-name">{row.file.name}</span>
        <span className="import-file-state">{uploadText(row, labels)}</span>
      </li>)}
    </ul>}
    <div className="button-row">
      <Button onClick={upload} disabled={uploading || pending === 0}><Icon name="upload" size={16} /> {uploading ? 'Lädt hoch …' : 'Hochladen'}</Button>
      {rows.length > 0 && !uploading && <Button className="secondary" onClick={() => { setRows([]); setStatus(''); if (input.current) input.current.value = ''; }}>Liste leeren</Button>}
    </div>
    <p className="import-live muted" role="status" aria-live="polite">{status}</p>
  </section>;
}

function uploadText(row: UploadRow, labels: Labels) {
  if (row.state === 'waiting') return 'Wartet';
  if (row.state === 'running') return 'Lädt hoch …';
  if (row.state === 'error') return `Fehler: ${row.message}`;
  if (row.unit == null) return `Fertig. Keine ${labels.one} erkannt, bitte unter „Dokumente“ zuordnen.`;
  if (row.requested != null && row.requested !== row.unit) return `Fertig. Als ${labels.one} ${row.unit} erkannt (gewählt war ${row.requested}).`;
  return `Fertig. ${labels.one} ${row.unit}.`;
}

function DocumentList({ documents, kinds, onKindChanged }: {
  documents: ImportDocument[]; kinds?: DocumentKind[]; onKindChanged?: () => void;
}) {
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [removing, setRemoving] = useState<ImportDocument | null>(null);
  const [notice, setNotice] = useState('');
  if (!documents.length) return <p className="muted import-none">Noch keine Unterlagen.</p>;
  const remove = async () => {
    if (!removing) return;
    setSaving(removing.id);
    setError('');
    try {
      const result = await api<RemoveResult>(`/documents/${removing.id}`, undefined, 'DELETE');
      setNotice(removeText(result));
      setRemoving(null);
      onKindChanged?.();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setSaving(null);
    }
  };
  const change = async (document: ImportDocument, kind: string) => {
    setSaving(document.id);
    setError('');
    try {
      await api(`/documents/${document.id}/kind`, { kind: kind === '__auto__' ? null : kind }, 'PATCH');
      onKindChanged?.();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setSaving(null);
    }
  };
  return <>
    {error && <ErrorBox error={error} />}
    <ul className="import-documents">
      {documents.map(document => <li key={document.path}>
        <span className="import-document-name">{document.name}</span>
        {document.pages > 0 && <span className="muted"> · {document.pages} S.</span>}
        {kinds && kinds.length > 0 && <label className="import-kind">
          <span className="muted">Art:</span>
          <select value={document.manual_kind || document.kind} disabled={saving === document.id}
            aria-label={`Art der Unterlage ${document.name}`} onChange={event => change(document, event.target.value)}>
            {!kinds.some(item => item.kind === document.kind) && <option value={document.kind}>{document.kind}</option>}
            {kinds.map(item => <option key={item.kind} value={item.kind}>{item.label}{item.prepared ? '' : ' (wird nicht aufbereitet)'}</option>)}
            {document.manual_kind && <option value="__auto__">Automatisch erkennen lassen</option>}
          </select>
          {document.manual_kind ? <Badge>Von Hand gewählt</Badge> : <span className="muted">automatisch erkannt</span>}
        </label>}
        {document.usable ? <span className="import-ok"> Wird aufbereitet</span>
          : document.reason && <span className="import-reason">Nicht verwertbar: {document.reason}</span>}
        {onKindChanged && <button type="button" className="text-button import-remove" disabled={saving === document.id}
          onClick={() => { setNotice(''); setRemoving(document); }}>Entfernen</button>}
      </li>)}
    </ul>
    {notice && <p className="import-live muted" role="status" aria-live="polite">{notice}</p>}
    {removing && <Modal title="Datei entfernen?" onClose={() => setRemoving(null)}>
      <p>„{removing.name}“ wird aus dem Studienordner in den Papierkorb des Hubs verschoben (<code>data/papierkorb/…</code>) und aus der Liste genommen. Nichts wird endgültig gelöscht: Datei zurückschieben und unter „Dokumente“ den Ordner durchsuchen holt sie wieder herein.</p>
      <p className="muted">Bereits übernommene Fragen und veröffentlichte Lernseiten bleiben erhalten.</p>
      {error && <ErrorBox error={error} />}
      <div className="button-row">
        <Button onClick={remove} disabled={saving === removing.id}>{saving === removing.id ? 'Wird verschoben …' : 'In den Papierkorb'}</Button>
        <Button className="secondary" onClick={() => setRemoving(null)}>Abbrechen</Button>
      </div>
    </Modal>}
  </>;
}

function UnitsSection({ labels, overview, selected, onSelect }: {
  labels: Labels;
  overview: { data: ImportOverview | null; error: string; loading: boolean; reload: () => void };
  selected: number[];
  onSelect: (units: number[]) => void;
}) {
  const { data, error, loading, reload } = overview;
  const kinds = useLoad(() => api<DocumentKind[]>('/module-import/kinds'), []);
  const choosable = data ? data.units.filter(item => item.published_lessons === 0 && item.documents.length > 0).map(item => item.unit) : [];
  const toggle = (unit: number) => onSelect(selected.includes(unit) ? selected.filter(item => item !== unit) : [...selected, unit].sort((a, b) => a - b));
  return <section className="card import-step" aria-labelledby="import-units-title">
    <div className="section-head">
      <h2 id="import-units-title"><span className="import-number">3</span> {labels.many}</h2>
      {data && choosable.length > 1 && <Button className="secondary small" onClick={() => onSelect(selected.length === choosable.length ? [] : choosable)}>
        {selected.length === choosable.length ? 'Auswahl aufheben' : 'Alle auswählen'}
      </Button>}
    </div>
    {error && <ErrorBox error={error} retry={reload} />}
    {loading && !data && <Loading />}
    {data && <>
      {data.units.length === 0 && <p className="muted">Zu diesem Modul gibt es noch keine Unterlagen mit {labels.one}. Lade oben Dateien hoch.</p>}
      <ul className="import-units">
        {data.units.map(item => {
          const published = item.published_lessons > 0;
          const empty = item.documents.length === 0;
          const id = `import-unit-${item.unit}`;
          return <li key={item.unit} className={`import-unit${selected.includes(item.unit) ? ' is-selected' : ''}`}>
            <input id={id} type="checkbox" checked={selected.includes(item.unit)} disabled={published || empty}
              aria-describedby={`${id}-state`} onChange={() => toggle(item.unit)} />
            <div className="import-unit-body">
              <label htmlFor={id} className="import-unit-title">{labels.one} {item.unit}</label>
              <span id={`${id}-state`} className="import-unit-state">
                {published
                  ? <Badge tone="green">Veröffentlicht</Badge>
                  : item.draft_lessons > 0 ? <Badge tone="yellow">Entwurf</Badge> : empty ? <Badge>Keine Unterlagen</Badge> : <Badge tone="teal">Unterlagen vorhanden</Badge>}
                {published && <span className="muted"> {item.published_lessons} {item.published_lessons === 1 ? 'Lernseite' : 'Lernseiten'}, nicht mehr auswählbar</span>}
                {!published && item.draft_lessons > 0 && <span className="muted"> {item.draft_lessons} {item.draft_lessons === 1 ? 'Lernseite' : 'Lernseiten'} im Entwurf</span>}
              </span>
              <DocumentList documents={item.documents} kinds={kinds.data || []} onKindChanged={reload} />
            </div>
          </li>;
        })}
      </ul>
      {data.unassigned_documents.length > 0 && <div className="alert warning import-unassigned">
        <strong>Ohne {labels.one}</strong>
        <span>Diese Dateien werden nicht aufbereitet. Ordne sie unter <a href="#documents">Dokumente</a> einer {labels.one} zu.</span>
        <DocumentList documents={data.unassigned_documents} kinds={kinds.data || []} onKindChanged={reload} />
      </div>}
    </>}
  </section>;
}

function ProcessSection({ module, labels, overview, selected, tutorBlock, pictureBusy, onBusy, onRefresh }: {
  module: Module; labels: Labels; overview: ImportOverview; selected: number[]; tutorBlock: string; pictureBusy: boolean;
  onBusy: (busy: boolean) => void; onRefresh: () => void;
}) {
  const [preview, setPreview] = useState<{ key: string; data: ImportPreview } | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [watch, setWatch] = useState(0);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState('');
  const [starting, setStarting] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState<ImportPublishResult | null>(null);
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;
  const key = selected.join(',');
  const mine = status && status.module_id === module.id ? status : null;
  const running = status?.state === 'running';
  const runningHere = running && !!mine;
  useEffect(() => onBusy(running), [running]);

  // Ask for the state once on arrival (a running job shows up again after a reload), then every 2 seconds while it runs.
  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let wasRunning = false;
    const tick = async () => {
      try {
        const next = await api<ImportStatus>('/module-import');
        if (!active) return;
        setStatus(next);
        if (next.state === 'running') {
          wasRunning = true;
          timer = window.setTimeout(tick, POLL_MS);
        } else if (wasRunning) {
          refreshRef.current();
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

  const unitOf = new Map<string, number>();
  overview.units.forEach(item => item.documents.forEach(document => unitOf.set(document.path, item.unit)));
  const shown = preview && preview.key === key ? preview.data : null;
  const sources = shown ? shown.sources.filter(source => selected.includes(source.unit)) : [];
  const skipped = shown ? shown.skipped.filter(item => !unitOf.has(item.path) || selected.includes(unitOf.get(item.path)!)) : [];
  const windows = sources.reduce((sum, source) => sum + source.windows, 0);
  const perWindow = shown && shown.windows ? shown.estimated_minutes / shown.windows : 5;
  const minutes = Math.round(windows * perWindow);

  const showPreview = async () => {
    setPreviewing(true);
    setError('');
    setBlocked('');
    setPublished(null);
    try {
      setPreview({ key, data: await api<ImportPreview>(`/module-import/preview?module_id=${enc(module.id)}`) });
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setPreviewing(false);
    }
  };
  const start = async () => {
    setStarting(true);
    setError('');
    setPublished(null);
    try {
      setStatus(await api<ImportStatus>('/module-import', { module_id: module.id, units: selected }));
      setWatch(value => value + 1);
    } catch (problem) {
      const text = errorText(problem);
      if (/Ollama|Modell/.test(text)) setBlocked(text);
      else setError(text);
    } finally {
      setStarting(false);
    }
  };
  const cancel = async () => {
    try {
      setStatus(await api<ImportStatus>('/module-import/cancel', {}));
      setWatch(value => value + 1);
    } catch (problem) {
      setError(errorText(problem));
    }
  };
  const publish = async () => {
    setPublishing(true);
    setError('');
    try {
      setPublished(await api<ImportPublishResult>('/module-import/publish', { module_id: module.id }));
      onRefresh();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setPublishing(false);
    }
  };

  const otherRunning = running && !mine;
  const lock = tutorBlock || blocked;
  const canStart = !!shown && windows > 0 && !running && !pictureBusy && !starting && !lock;
  const unpublishedDrafts = overview.units.filter(item => item.draft_lessons > 0 && item.published_lessons === 0).map(item => item.unit);
  const finished = mine && ['done', 'cancelled', 'error'].includes(mine.state) ? mine : null;
  const total = mine?.total || 0;
  const done = mine?.done || 0;
  return <section className="card import-step" aria-labelledby="import-process-title">
    <h2 id="import-process-title"><span className="import-number">4</span> Aufbereiten</h2>
    {lock && <div className="alert warning" role="alert"><strong>Das KI-Modell ist nicht bereit.</strong><span>{lock}</span></div>}
    {otherRunning && <div className="alert info" role="status">Für das Modul „{status?.module_name || status?.module_id}“ läuft gerade eine Aufbereitung. Warte, bis sie fertig ist.</div>}
    {error && <ErrorBox error={error} />}
    {selected.length === 0 && !runningHere && <p className="muted">Wähle oben mindestens einen Eintrag, dann kannst du eine Vorschau ansehen.</p>}
    <div className="button-row">
      <Button className="secondary" onClick={showPreview} disabled={selected.length === 0 || previewing || running}>
        <Icon name="search" size={16} /> {previewing ? 'Vorschau wird geladen …' : 'Vorschau'}
      </Button>
      <Button onClick={start} disabled={!canStart}><Icon name="learn" size={16} /> Aufbereitung starten</Button>
      {shown && !canStart && !running && !lock && windows === 0 && <span className="muted">Aus den gewählten Einheiten lässt sich nichts lesen.</span>}
    </div>
    {shown && !runningHere && <div className="import-preview">
      <h3>Das wird gelesen</h3>
      <p><strong>{windows}</strong> {windows === 1 ? 'Abschnitt' : 'Abschnitte'} aus {sources.length} {sources.length === 1 ? 'Datei' : 'Dateien'}, geschätzt etwa <strong>{minutes} Minuten</strong>.</p>
      <ul className="import-documents">
        {sources.map(source => <li key={source.path}>
          <span className="import-document-name">{source.path.split('/').pop()}</span>
          <span className="muted"> · {labels.one} {source.unit} · {source.pages} S. · {source.windows} {source.windows === 1 ? 'Abschnitt' : 'Abschnitte'}</span>
        </li>)}
      </ul>
      {skipped.length > 0 && <>
        <h3>Das wird ausgelassen</h3>
        <ul className="import-documents">
          {skipped.map(item => <li key={item.path}>
            <span className="import-document-name">{item.path.split('/').pop()}</span>
            <span className="import-reason">{item.reason}</span>
          </li>)}
        </ul>
      </>}
    </div>}
    {runningHere && <div className="import-run" aria-live="polite">
      <Progress value={total ? (done / total) * 100 : 0} label="Fortschritt der Aufbereitung" />
      <p><strong>{done} von {total}</strong> Abschnitten erledigt{mine?.current ? `. Aktuell: ${mine.current}` : '.'}</p>
      <Button className="secondary small" onClick={cancel}>Abbrechen</Button>
    </div>}
    {mine && mine.messages.length > 0 && <div className="import-messages-wrap">
      <h3>Meldungen</h3>
      <ol className="import-messages" aria-live="polite" tabIndex={0} aria-label="Meldungen der Aufbereitung">
        {mine.messages.map((message, index) => <li key={index}>{message}</li>)}
      </ol>
    </div>}
    {finished && <ImportResult status={{ ...finished, outputs: finished.outputs ? { ...finished.outputs, draft_errors: overview.draft_errors ?? finished.outputs.draft_errors } : finished.outputs }} />}
    {!runningHere && unpublishedDrafts.length > 0 && <div className="import-publish">
      <h3>Lernseiten veröffentlichen</h3>
      {!!overview.draft_errors?.length && <div className="alert warning"><strong>Bitte den Entwurf zuerst korrigieren.</strong><ul>{overview.draft_errors.map((message, index) => <li key={index}>{message}</li>)}</ul></div>}
      <p>Der Entwurf enthält Lernseiten für {unpublishedDrafts.length === 1 ? labels.one : labels.many} {list(unpublishedDrafts)}. Erst nach dem Veröffentlichen erscheinen sie im Bereich Lernpages.</p>
      <div className="button-row">
        <Button onClick={publish} disabled={publishing || running || !!overview.draft_errors?.length}><Icon name="check" size={16} /> {publishing ? 'Wird veröffentlicht …' : 'Lernseiten veröffentlichen'}</Button>
        <a className="button secondary" href={`#documents`}>Fragen unter Dokumente prüfen</a>
      </div>
    </div>}
    {published && <div className="alert success" role="status">
      <strong>Lernseiten veröffentlicht.</strong>
      <span>{published.lessons} {published.lessons === 1 ? 'Lernseite' : 'Lernseiten'}{published.added_units.length ? ` für ${published.added_units.length === 1 ? labels.one : labels.many} ${list(published.added_units)} neu aufgenommen` : ''}.
        {published.skipped_units.length > 0 && ` Übersprungen, weil schon veröffentlicht: ${labels.many} ${list(published.skipped_units)}.`}</span>
      <a href={`#pages?module=${enc(module.id)}`}>Lernseiten ansehen</a>
    </div>}
  </section>;
}

function ImportResult({ status }: { status: ImportStatus }) {
  const counts = status.counts;
  const outputs = status.outputs;
  const needsCorrection = !!outputs?.draft_errors?.length;
  const headline = status.state === 'done' ? (needsCorrection ? 'Entwurf – Korrektur erforderlich' : 'Entwurf erstellt') : status.state === 'cancelled' ? 'Abgebrochen' : 'Fehlgeschlagen';
  const tone = status.state === 'done' ? (needsCorrection ? 'warning' : 'success') : status.state === 'cancelled' ? 'info' : 'error';
  return <div className={`alert ${tone} import-result`} role="status">
    <strong>{headline}</strong>
    {outputs && <dl className="import-counts">
      <div><dt>Lernseiten</dt><dd>{outputs.lessons}</dd></div>
      <div><dt>Fragen</dt><dd>{outputs.questions}</dd></div>
      {counts && <>
        <div><dt>Verworfene Fragen</dt><dd>{counts.rejected_questions}</dd></div>
        <div><dt>Abschnitte ohne Beleg</dt><dd>{counts.unproven_sections}</dd></div>
        <div><dt>Abschnitte ohne Ergebnis</dt><dd>{counts.failed_windows}</dd></div>
      </>}
    </dl>}
    {outputs?.draft_errors && outputs.draft_errors.length > 0 && <div>
      <strong>Fehler im Entwurf</strong>
      <ul className="import-errors">{outputs.draft_errors.map((text, index) => <li key={index}>{text}</li>)}</ul>
    </div>}
    {outputs && outputs.questions > 0 && <a href="#documents">Fragen unter Dokumente prüfen</a>}
  </div>;
}

function BigPictureSection({ module, labels, overview, tutorBlock, importBusy, onBusy, onRefresh }: {
  module: Module; labels: Labels; overview: ImportOverview; tutorBlock: string; importBusy: boolean;
  onBusy: (busy: boolean) => void; onRefresh: () => void;
}) {
  const info = useLoad(() => api<BigPictureInfo>(`/big-picture?module_id=${enc(module.id)}`), [module.id]);
  const pages = useLoad(
    async () => {
      // Ask the list first: the single package answers 404 while nothing is published.
      const known = await api<LearningPagesSummary[]>('/learning-pages');
      return known.some(item => item.module_id === module.id) ? api<LearningPagesPackage>(`/learning-pages/${enc(module.id)}`) : null;
    },
    [module.id, overview.units.map(item => item.published_lessons).join(',')]);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState('');
  const data = info.data;
  const running = data?.state === 'running';
  const reloadRef = useRef(info.reload);
  reloadRef.current = info.reload;
  useEffect(() => onBusy(running), [running]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(() => reloadRef.current(), POLL_MS);
    return () => window.clearTimeout(timer);
  }, [running, data]);

  const hasPages = overview.has_learning_pages && overview.units.some(item => item.published_lessons > 0);
  const exists = !!data?.published.exists;
  const stale = data?.published.stale_units || [];
  const draft = data?.draft || null;
  const publishedPicture = pages.data?.overview.big_picture;
  const draftIsPublished = !!draft && !!publishedPicture && stableStringify(draft) === stableStringify(publishedPicture);
  const titles = new Map((pages.data?.lessons || []).map(lesson => [lesson.id, lesson.title]));
  const nodeTitles = new Map((draft?.nodes || []).map(node => [node.id, node.title]));
  const lock = tutorBlock;

  const start = async () => {
    setStarting(true);
    setError('');
    setResult('');
    try {
      await api('/big-picture', { module_id: module.id });
      info.reload();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setStarting(false);
    }
  };
  const publish = async () => {
    setConfirm(false);
    setPublishing(true);
    setError('');
    try {
      const body = exists ? { module_id: module.id, replace: true } : { module_id: module.id };
      const done = await api<{ replaced: boolean; nodes: number }>('/big-picture/publish', body);
      setResult(`${done.replaced ? 'Big Picture ersetzt' : 'Big Picture veröffentlicht'}: ${done.nodes} Bausteine.`);
      info.reload();
      pages.reload();
      onRefresh();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setPublishing(false);
    }
  };

  return <section className="card import-step" aria-labelledby="import-picture-title">
    <h2 id="import-picture-title"><span className="import-number">5</span> Big Picture</h2>
    {info.error && <ErrorBox error={info.error} retry={info.reload} />}
    {info.loading && !data && <Loading />}
    {data && <>
      <p className="import-picture-state">
        {exists
          ? <><Badge tone={stale.length ? 'yellow' : 'green'}>{stale.length ? 'Veraltet' : 'Vorhanden'}</Badge>{' '}
            {data.published.units.length > 0 && `Stand: ${data.published.units.length === 1 ? labels.one : labels.many} ${list(data.published.units)}. `}
            {data.published.generated_by ? `Herkunft: ${data.published.generated_by}.` : 'Herkunft nicht angegeben.'}
            {stale.length > 0 && ` Neu dazugekommen: ${labels.many} ${list(stale)}.`}</>
          : <><Badge>Keines</Badge> Für dieses Modul gibt es noch kein Big Picture.</>}
      </p>
      {!hasPages && <p className="muted">Zuerst müssen Lernseiten veröffentlicht sein. Das Big Picture entsteht aus ihnen.</p>}
      {lock && <div className="alert warning" role="alert"><strong>Das KI-Modell ist nicht bereit.</strong><span>{lock}</span></div>}
      {error && <ErrorBox error={error} />}
      <div className="button-row">
        <Button onClick={start} disabled={!hasPages || running || starting || importBusy || !!lock}>
          <Icon name={exists ? 'refresh' : 'plus'} size={16} /> {exists ? 'Big Picture erneuern' : 'Big Picture erstellen'}
        </Button>
        {importBusy && <span className="muted">Wartet, bis die Aufbereitung fertig ist.</span>}
      </div>
      <p className="import-live muted" role="status" aria-live="polite">
        {running ? data.message || 'Das KI-Modell erstellt das Big Picture. Das kann einige Minuten dauern.' : data.state === 'error' ? '' : data.message}
      </p>
      {data.state === 'error' && <ErrorBox error={data.message} />}
      {draft && !running && <div className="import-draft">
        <h3>Entwurf</h3>
        <p className="import-draft-title"><strong>{draft.title}</strong></p>
        <p className="import-question"><span>Leitfrage</span>{draft.central_question}</p>
        <p>{draft.intro}</p>
        <h4>Bausteine</h4>
        <ol className="import-nodes">
          {draft.nodes.map(node => <li key={node.id}>
            <strong>{node.title}</strong>
            <span className="muted"> {node.role}</span>
            <p>{node.summary}</p>
            {!!node.lesson_ids?.length && <p className="muted import-lessons">Lernseiten: {node.lesson_ids.map(id => titles.get(id) || id).join(', ')}</p>}
          </li>)}
        </ol>
        {draft.connections.length > 0 && <>
          <h4>Zusammenhänge</h4>
          <ul className="import-connections">
            {draft.connections.map((connection, index) => <li key={index}>
              {nodeTitles.get(connection.from) || connection.from} → {nodeTitles.get(connection.to) || connection.to}: {connection.label}
            </li>)}
          </ul>
        </>}
        <p className="muted">Entwurf: {draft.generated_by || 'unbekannt'}. Fachlich nicht geprüft.</p>
        {draftIsPublished
          ? <p className="muted">Dieser Entwurf ist bereits veröffentlicht.</p>
          : <div className="button-row">
            <Button onClick={() => (exists ? setConfirm(true) : publish())} disabled={publishing}>
              <Icon name="check" size={16} /> {publishing ? 'Wird veröffentlicht …' : 'Veröffentlichen'}
            </Button>
          </div>}
      </div>}
      {result && <div className="alert success" role="status"><strong>{result}</strong><a href={`#pages?module=${enc(module.id)}`}>Lernseiten ansehen</a></div>}
    </>}
    {confirm && <Modal title="Big Picture ersetzen?" onClose={() => setConfirm(false)}>
      <p>Für dieses Modul gibt es schon ein Big Picture. Wenn du fortfährst, wird es durch den Entwurf ersetzt. Die bisherige Datei wird vorher gesichert.</p>
      <div className="button-row">
        <Button onClick={publish}>Ersetzen</Button>
        <Button className="secondary" onClick={() => setConfirm(false)}>Abbrechen</Button>
      </div>
    </Modal>}
  </section>;
}
