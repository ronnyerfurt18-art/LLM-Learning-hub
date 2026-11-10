import { FormEvent, useMemo, useState } from 'react';
import { api, errorText, query } from './api';
import { Badge, Button, Empty, ErrorBox, Field, Icon, Loading, Modal, PageTitle, useLoad } from './components';
import { SourceDocumentLink } from './SourceLinks';
import { Module } from './types';
import './planning.css';

export type PlanningEvent = {
  id: string;
  module_id: string | null;
  title: string;
  kind: 'deadline' | 'exam' | 'teaching' | 'phase' | 'study';
  start: string;
  end?: string | null;
  all_day: boolean;
  timezone: string;
  description: string;
  location?: string | null;
  source?: { path: string; title: string; kind?: string; pdf_page?: number | null; chapter?: string | null } | null;
  date_note?: string | null;
  status: 'planned' | 'done';
  category?: 'submission' | 'registration' | 'reenrollment' | 'other';
};

type PlanningData = { events: PlanningEvent[]; timezone: string; today: string; notes: string[] };
export const deadlineCategories = { submission: 'Abgabe', registration: 'Modul- oder Prüfungsanmeldung', reenrollment: 'Rückmeldung', other: 'Sonstige Frist' };
const ZONE = 'Europe/Berlin';
const kindNames: Record<PlanningEvent['kind'], string> = { deadline: 'Abgabe / Frist', exam: 'Prüfung', teaching: 'Lehrveranstaltung', phase: 'Bearbeitungsfenster', study: 'Lernblock' };
const dayFormatter = new Intl.DateTimeFormat('de-DE', { timeZone: ZONE, day: 'numeric', month: 'long', year: 'numeric', weekday: 'short' });
const timeFormatter = new Intl.DateTimeFormat('de-DE', { timeZone: ZONE, hour: '2-digit', minute: '2-digit' });
const isoDateFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit' });
const berlinParts = new Intl.DateTimeFormat('en-GB', { timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

function dateParts(value: Date) {
  return Object.fromEntries(berlinParts.formatToParts(value).map(part => [part.type, part.value]));
}

// The form always means Berlin wall-clock time, even on a computer set to another time zone.
export function berlinDateTime(date: string, time: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const clock = /^(\d{2}):(\d{2})$/.exec(time);
  if (!match || !clock) throw new Error('Bitte gib ein gültiges Datum und eine Uhrzeit ein.');
  const [, year, month, day] = match;
  const [, hour, minute] = clock;
  const target = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  const candidates = [1, 2].map(offset => new Date(target - offset * 3600000)).filter(value => {
    const parts = dateParts(value);
    return parts.year === year && parts.month === month && parts.day === day && parts.hour === hour && parts.minute === minute;
  });
  if (!candidates.length) throw new Error('Diese Uhrzeit existiert an diesem Datum in Berlin nicht. Bitte wähle eine andere Uhrzeit (Zeitumstellung).');
  if (candidates.length > 1) throw new Error('Diese Uhrzeit kommt bei der Zeitumstellung zweimal vor. Bitte wähle eine Uhrzeit vor 02:00 oder ab 03:00 Uhr.');
  return candidates[0].toISOString();
}

export function displayDate(event: PlanningEvent) {
  // Noon Berlin avoids interpreting a date-only value in the browser's own zone.
  return dayFormatter.format(new Date(event.all_day ? `${event.start.slice(0, 10)}T12:00:00+01:00` : event.start));
}

function eventDay(event: PlanningEvent) {
  if (event.all_day) return event.start.slice(0, 10);
  const parts = dateParts(new Date(event.start));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function displayTime(event: PlanningEvent) {
  if (event.all_day) return 'Ganztägig · keine Uhrzeit angegeben';
  const start = timeFormatter.format(new Date(event.start));
  if (event.kind === 'deadline') return `Frist: ${start} Uhr`;
  if (event.kind === 'phase' && !event.end) return `Beginn: ${start} Uhr`;
  if (!event.end) return `${start} Uhr · Ende nicht angegeben`;
  const endDate = new Date(event.end);
  const endParts = dateParts(endDate);
  const sameDay = `${endParts.year}-${endParts.month}-${endParts.day}` === eventDay(event);
  return `${start}–${sameDay ? '' : `${dayFormatter.format(endDate)}, `}${timeFormatter.format(endDate)} Uhr`;
}

function calendarUrl(moduleId = '', eventId = '') {
  return `/api/planning/calendar.ics${query({ module_id: moduleId, event_id: eventId })}`;
}

function ordered(events: PlanningEvent[]) {
  return [...events].sort((a, b) => Date.parse(a.start) - Date.parse(b.start) || a.title.localeCompare(b.title, 'de'));
}

function moduleName(modules: Module[], id: string | null) {
  if (!id) return 'Studienweit';
  return modules.find(module => module.id === id)?.name || id;
}

export function EventCard({ event, modules, today, busy, onStatus, overdue, onEdit }: {
  event: PlanningEvent;
  modules: Module[];
  today: string;
  busy: boolean;
  onStatus: (event: PlanningEvent) => void;
  overdue?: boolean;
  onEdit?: (event: PlanningEvent) => void;
}) {
  const past = eventDay(event) < today;
  const source = event.source;
  return <li className={`planning-event ${event.status === 'done' ? 'is-done' : ''}`}>
    <div className="planning-event-date"><Icon name="clock" size={18} /><div><time dateTime={event.start}>{displayDate(event)}</time><span>{displayTime(event)}</span></div></div>
    <div className="planning-event-main">
      <div className="planning-event-tags"><Badge tone={event.kind === 'exam' || event.kind === 'deadline' ? 'yellow' : 'teal'}>{event.category ? deadlineCategories[event.category] : kindNames[event.kind]}</Badge>
        <span>{moduleName(modules, event.module_id)}</span>{(overdue ?? past) && <span className="planning-past">Vergangen</span>}{event.category && <span>Selbst eingetragen</span>}{event.status === 'done' && <Badge tone="green">Erledigt</Badge>}</div>
      <h3>{event.title}</h3>
      {event.description && <p className="preserve-lines">{event.description}</p>}
      {event.location && <p className="planning-location"><strong>Ort:</strong> {event.location}</p>}
      {event.date_note && <p className="planning-date-note"><Icon name="file" size={15} /><span>{event.date_note}</span></p>}
      {source && <div className="planning-source"><span><strong>Quelle:</strong> {source.title}{source.chapter && ` · ${source.chapter}`}{source.pdf_page && ` · PDF-Seite ${source.pdf_page}`}</span>
        <SourceDocumentLink path={source.path} page={/\.pdf$/i.test(source.path) ? source.pdf_page : undefined}>Quelle öffnen</SourceDocumentLink></div>}
      <div className="planning-event-actions"><button className={`button small ${event.status === 'done' ? 'secondary' : ''}`} disabled={busy} aria-pressed={event.status === 'done'} onClick={() => onStatus(event)}>
        <Icon name={event.status === 'done' ? 'repeat' : 'check'} size={15} />{event.status === 'done' ? 'Wieder offen' : 'Als erledigt markieren'}</button>
        {onEdit && <Button className="secondary small" disabled={busy} onClick={() => onEdit(event)}>Bearbeiten</Button>}
        <a className="planning-calendar-link" href={calendarUrl('', event.id)} download><Icon name="download" size={15} />Apple Kalender</a></div>
    </div>
  </li>;
}

export function StudyBlockForm({ modules, initialModule, initialTitle = '', today, onClose, onCreated }: {
  modules: Module[];
  initialModule: string;
  initialTitle?: string;
  today: string;
  onClose: () => void;
  onCreated: (moduleId: string) => void;
}) {
  const [title, setTitle] = useState(initialTitle.slice(0, 240));
  const [moduleId, setModuleId] = useState(initialModule || modules[0]?.id || '');
  const [date, setDate] = useState(today);
  const [start, setStart] = useState('18:00');
  const [end, setEnd] = useState('19:00');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setError('');
    try {
      const selectedDate = String(fields.get('date') || '');
      const startIso = berlinDateTime(selectedDate, String(fields.get('start') || ''));
      const endIso = berlinDateTime(selectedDate, String(fields.get('end') || ''));
      if (endIso <= startIso) throw new Error('Das Ende muss nach dem Beginn liegen. Ein Lernblock liegt innerhalb eines Tages.');
      setSaving(true);
      await api('/planning/events', { module_id: moduleId, title: title.trim(), kind: 'study', start: startIso, end: endIso, all_day: false, timezone: ZONE, description: description.trim() });
      onCreated(moduleId);
    } catch (cause) { setError(errorText(cause)); }
    finally { setSaving(false); }
  }
  return <Modal title="Deinen Lernblock planen" onClose={onClose}><form onSubmit={submit} className="planning-form">
    <p className="muted">Wähle ein konkretes Thema und reserviere dir Zeit zum Verstehen, Nachlesen oder Üben.</p>
    {error && <ErrorBox error={error} />}
    <Field label="Was möchtest du lernen?"><input value={title} onChange={event => setTitle(event.target.value)} placeholder="Zum Beispiel: Kapitel 2 wiederholen und Übungsfragen lösen" maxLength={240} required /></Field>
    <div className="form-grid"><Field label="Studienmodul"><select value={moduleId} onChange={event => setModuleId(event.target.value)} required><option value="" disabled>Modul auswählen</option>{modules.map(module => <option key={module.id} value={module.id}>{module.name}</option>)}</select></Field>
      <Field label="Datum"><input type="date" name="date" value={date} onInput={event => setDate(event.currentTarget.value)} onChange={event => setDate(event.target.value)} required /></Field></div>
    <div className="form-grid"><Field label="Beginn · Berliner Zeit"><input type="time" name="start" value={start} onInput={event => setStart(event.currentTarget.value)} onChange={event => setStart(event.target.value)} required /></Field>
      <Field label="Ende · Berliner Zeit"><input type="time" name="end" value={end} onInput={event => setEnd(event.currentTarget.value)} onChange={event => setEnd(event.target.value)} required /></Field></div>
    <Field label="Dein Vorhaben (optional)"><textarea rows={3} value={description} onChange={event => setDescription(event.target.value)} placeholder="Welches Kapitel? Was möchtest du danach erklären können?" maxLength={4000} /></Field>
    <p className="planning-timezone"><Icon name="clock" size={15} />Alle Uhrzeiten gelten für Europe/Berlin, einschließlich Sommer- und Winterzeit.</p>
    <div className="modal-actions"><Button className="secondary" onClick={onClose} disabled={saving}>Abbrechen</Button><Button type="submit" disabled={saving || !moduleId || !title.trim()}>{saving ? 'Wird gespeichert …' : 'Lernblock speichern'}<Icon name="plus" size={16} /></Button></div>
  </form></Modal>;
}

export function PlanningPage({ modules, initialModule, onOpenModule }: { modules: Module[]; initialModule: string; onOpenModule: (moduleId: string) => void }) {
  const [status, setStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [savingId, setSavingId] = useState('');
  const [actionError, setActionError] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const { data, error, loading, reload, setData } = useLoad(() => api<PlanningData>(`/planning${query({ module_id: initialModule })}`), [initialModule]);
  const events = useMemo(() => ordered(data?.events || []), [data]);
  const visible = status ? events.filter(event => event.status === status) : events;
  const fixed = visible.filter(event => event.kind !== 'study');
  const study = visible.filter(event => event.kind === 'study');
  const today = data?.today || isoDateFormatter.format(new Date());
  const upcoming = events.filter(event => event.status !== 'done' && eventDay(event) >= today);
  const next = upcoming[0];
  async function changeStatus(event: PlanningEvent) {
    setSavingId(event.id); setActionError(''); setAnnouncement('');
    try {
      const value = await api<PlanningEvent>(`/planning/events/${encodeURIComponent(event.id)}`, { status: event.status === 'done' ? 'planned' : 'done' }, 'PATCH');
      setData(current => current ? { ...current, events: current.events.map(item => item.id === value.id ? value : item) } : current);
      setAnnouncement(`${event.title}: ${value.status === 'done' ? 'als erledigt markiert' : 'wieder offen'}.`);
    } catch (cause) { setActionError(errorText(cause)); }
    finally { setSavingId(''); }
  }
  return <div className="planning-page">
    <PageTitle eyebrow="ZEIT FÜR DEIN STUDIUM" title="Deine Lernplanung" description="Behalte feste Termine im Blick und gib deinen nächsten Lernschritten einen Platz im Kalender." action={<Button onClick={() => setShowForm(true)} disabled={!modules.length}><Icon name="plus" size={17} />Lernblock planen</Button>} />
    <div className="filter-bar planning-filters"><Field label="Studienmodul"><select value={initialModule} onChange={event => onOpenModule(event.target.value)}><option value="">Alle Module</option>{modules.map(module => <option key={module.id} value={module.id}>{module.name}</option>)}</select></Field>
      <Field label="Arbeitsstand"><select value={status} onChange={event => setStatus(event.target.value)}><option value="">Alle Termine</option><option value="planned">Offen</option><option value="done">Erledigt</option></select></Field>
      <a className="button secondary" href={calendarUrl(initialModule)} download><Icon name="download" size={16} />{initialModule ? 'Modul in Apple Kalender' : 'Alle in Apple Kalender'}</a></div>
    <p className="planning-timezone"><Icon name="clock" size={15} />Alle Daten und Uhrzeiten: Europe/Berlin. Die Kalenderdatei (.ics) kannst du in Apple Kalender öffnen und importieren.</p>
    <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
    {actionError && <ErrorBox error={actionError} />}
    {loading ? <Loading /> : error ? <ErrorBox error={error} retry={reload} /> : <>
      <div className="planning-summary"><div className="card planning-next"><span className="eyebrow">DEIN NÄCHSTER OFFENER TERMIN</span>{next ? <><h2>{next.title}</h2><p><strong>{displayDate(next)}</strong> · {displayTime(next)}</p><small>{moduleName(modules, next.module_id)}</small></> : <><h2>Platz für deinen nächsten Schritt</h2><p>Aktuell ist kein offener Termin ab heute eingetragen. Du kannst einen eigenen Lernblock planen.</p></>}</div>
        <div className="card planning-counts"><div><strong>{events.filter(event => event.kind !== 'study').length}</strong><span>feste Termine</span></div><div><strong>{events.filter(event => event.kind === 'study' && event.status === 'planned').length}</strong><span>offene Lernblöcke</span></div><div><strong>{events.filter(event => event.status === 'done').length}</strong><span>als erledigt markiert</span></div></div></div>
      {!!data?.notes?.length && <aside className="planning-notes" aria-label="Hinweise zu den Terminen"><strong>Hinweise aus deinen Unterlagen</strong><ul>{data.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></aside>}
      <div className="planning-columns"><section className="card planning-column" aria-labelledby="planning-fixed-title"><div className="section-head"><div><span className="eyebrow">AUS DEINEN TERMINUNTERLAGEN</span><h2 id="planning-fixed-title">Feste Termine <span className="count-label">{fixed.length}</span></h2></div><Icon name="exam" size={24} /></div>
        <p className="planning-section-intro">Veranstaltungen, Prüfungen und Fristen in zeitlicher Reihenfolge. Die Markierung „erledigt“ ist dein persönlicher Arbeitsstand und bestätigt keine offizielle Abgabe oder Anmeldung.</p>
        {fixed.length ? <ol className="planning-events">{fixed.map(event => <EventCard key={event.id} event={event} modules={modules} today={today} busy={!!savingId} onStatus={changeStatus} />)}</ol> : <Empty icon="clock" title={status ? 'Keine festen Termine mit diesem Arbeitsstand' : 'Noch keine festen Termine'}>Hier erscheinen die Termine aus den hinzugefügten Unterlagen für {initialModule ? 'dieses Modul' : 'deine Module'}.</Empty>}</section>
        <section className="card planning-column" aria-labelledby="planning-study-title"><div className="section-head"><div><span className="eyebrow">VON DIR GEPLANT</span><h2 id="planning-study-title">Deine Lernblöcke <span className="count-label">{study.length}</span></h2></div><Icon name="book" size={24} /></div>
          <p className="planning-section-intro">Reserviere dir Zeit für ein Kapitel, eine Wiederholung oder ein Thema, das du besser verstehen möchtest.</p>
          {study.length ? <ol className="planning-events">{study.map(event => <EventCard key={event.id} event={event} modules={modules} today={today} busy={!!savingId} onStatus={changeStatus} />)}</ol> : <Empty icon="learn" title={status ? 'Keine Lernblöcke mit diesem Arbeitsstand' : 'Dein nächster Lernblock wartet'} action={<Button className="secondary" onClick={() => setShowForm(true)} disabled={!modules.length}>Lernblock planen <Icon name="plus" size={16} /></Button>}>Ein konkretes Vorhaben und eine feste Zeit helfen dir, regelmäßig dranzubleiben.</Empty>}</section></div>
    </>}
    {showForm && <StudyBlockForm modules={modules} initialModule={initialModule} today={today} onClose={() => setShowForm(false)} onCreated={createdModule => { setShowForm(false); setStatus('planned'); setAnnouncement('Dein Lernblock wurde gespeichert.'); if (initialModule && createdModule !== initialModule) onOpenModule(createdModule); else reload(); }} />}
  </div>;
}

export function PlanningPreview({ moduleId }: { moduleId: string }) {
  const { data, error, loading } = useLoad(() => api<PlanningData>(`/planning${query({ module_id: moduleId })}`), [moduleId]);
  const next = useMemo(() => ordered(data?.events || []).filter(event => event.status === 'planned' && eventDay(event) >= (data?.today || '')).slice(0, 3), [data]);
  return <section className="card planning-preview" aria-labelledby="planning-preview-title"><div className="planning-preview-heading"><div><span className="eyebrow">VOM VERSTEHEN INS TUN</span><h2 id="planning-preview-title">Dein nächster Lernschritt</h2></div><a className="button secondary" href={`#plan${query({ module: moduleId })}`}><Icon name="clock" size={16} />Lernplanung öffnen</a></div>
    {loading ? <p className="muted">Termine werden geladen …</p> : error ? <p className="muted">Öffne die Lernplanung, um deine Termine und Lernblöcke anzusehen.</p> : next.length ? <ul className="planning-preview-events">{next.map(event => <li key={event.id}><time dateTime={event.start}>{displayDate(event)}</time><strong>{event.title}</strong><span>{displayTime(event)}</span></li>)}</ul> : <p>Plane Zeit für ein Kapitel oder eine Wiederholung. In der Lernplanung findest du die festen Termine dieses Moduls und deine eigenen Lernblöcke.</p>}
  </section>;
}
