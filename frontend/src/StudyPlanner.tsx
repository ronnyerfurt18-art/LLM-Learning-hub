import { FormEvent, useState } from 'react';
import { api, errorText, query } from './api';
import { AnswerText } from './AnswerText';
import { Badge, Button, ErrorBox, Field, Icon, Loading, Modal, PageTitle, useLoad } from './components';
import { berlinDateTime, deadlineCategories, displayDate, displayTime, EventCard, PlanningEvent, StudyBlockForm } from './Planning';
import { LessonStatus, lessonStatuses, saveLesson } from './plannerProgress';
import { Module } from './types';
import './study-planner.css';

type Position = {
  module_id: string; module_name: string; title: string; unit?: number;
  lesson_id?: string; section_id?: string; section_title?: string;
};
type Lesson = Position & { lesson_id: string; status: LessonStatus };
type Resume = Position & { kind: 'checkpoint' | 'practice' | 'tutor'; at: string };
type ModuleProgress = {
  id: string; name: string; lessons: Lesson[]; questions: number; studied: number; mastered: number; due: number;
  goals: { id: string; title: string; label: string; due: boolean; lesson_id: string; section_id: string }[];
};
type PlannerEvent = PlanningEvent & { overdue: boolean };
type PlannerData = {
  modules: ModuleProgress[]; resume: Resume | null; next_lesson: Lesson | null;
  events: PlannerEvent[]; today: string; notes: string[]; content_errors: boolean;
};
type PlannerAnswer = { answer: string; generated: boolean; notice?: string };

const quickQuestions = [
  { id: 'resume', label: 'Wo mache ich weiter?' },
  { id: 'progress', label: 'Was habe ich gelernt und was ist offen?' },
  { id: 'deadlines', label: 'Welche Fristen sind offen?' },
  { id: 'next', label: 'Was soll ich als Nächstes einplanen?' },
];

function positionUrl(position: Position, route = 'pages') {
  return `#${route}${query({ module: position.module_id, lesson: position.lesson_id, section: position.section_id,
    unit: route === 'learn' ? position.unit : undefined })}`;
}

function DeadlineForm({ modules, moduleId, today, existing, onClose, onSaved }: {
  modules: Module[]; moduleId: string; today: string; existing: PlanningEvent | null;
  onClose: () => void; onSaved: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState('');
  const endpoint = '/planning/deadlines' + (existing ? `/${encodeURIComponent(existing.id)}` : '');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const date = String(fields.get('date'));
    const time = String(fields.get('time') || '');
    setError('');
    setBusy(true);
    try {
      await api(endpoint, {
        title: String(fields.get('title')).trim(),
        category: fields.get('category'),
        module_id: fields.get('module') || null,
        start: time ? berlinDateTime(date, time) : date,
        all_day: !time,
        description: String(fields.get('description')).trim(),
      }, existing ? 'PUT' : 'POST');
      onSaved('Frist gespeichert.');
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true);
    setError('');
    try {
      await api(endpoint, undefined, 'DELETE');
      onSaved('Frist gelöscht.');
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }
  return <Modal title={existing ? 'Eigene Frist bearbeiten' : 'Eigene Frist hinzufügen'} onClose={() => { if (!busy) onClose(); }}>
    <form className="planning-form" onSubmit={submit}>
      <p className="muted">Übernimm das Datum aus deinen Unterlagen. Eine Frist kann für ein Modul oder für das gesamte Studium gelten.</p>
      {error && <ErrorBox error={error} />}
      <Field label="Bezeichnung"><input name="title" defaultValue={existing?.title} maxLength={240} required /></Field>
      <div className="form-grid">
        <Field label="Fristart"><select name="category" defaultValue={existing?.category || 'submission'}>
          {Object.entries(deadlineCategories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></Field>
        <Field label="Studienmodul"><select name="module" defaultValue={existing ? existing.module_id || '' : moduleId}>
          <option value="">Studienweit</option>
          {modules.map(module => <option key={module.id} value={module.id}>{module.name}</option>)}
        </select></Field>
      </div>
      <div className="form-grid">
        <Field label="Fällig am"><input name="date" type="date" defaultValue={existing?.start.slice(0, 10) || today} required /></Field>
        <Field label="Uhrzeit in Berlin (optional)"><input name="time" type="time" defaultValue={existing?.all_day ? '' : existing?.start.slice(11, 16)} /></Field>
      </div>
      <Field label="Notiz oder Herkunft (optional)"><textarea name="description" rows={3} defaultValue={existing?.description} maxLength={4000} /></Field>
      {confirmDelete && <p role="status">„{existing?.title}“ dauerhaft aus der Planung löschen?</p>}
      <div className="modal-actions">
        {existing && <Button className="secondary" disabled={busy} onClick={() => confirmDelete ? void remove() : setConfirmDelete(true)}>{confirmDelete ? 'Frist endgültig löschen' : 'Frist löschen'}</Button>}
        <Button className="secondary" onClick={onClose} disabled={busy}>Abbrechen</Button>
        <Button type="submit" disabled={busy}>{busy ? 'Wird gespeichert …' : 'Frist speichern'}</Button>
      </div>
    </form>
  </Modal>;
}

function PlannerQuestions({ moduleId }: { moduleId: string }) {
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState('');
  const [answer, setAnswer] = useState<PlannerAnswer | null>(null);
  const [history, setHistory] = useState<{ role: 'user' | 'assistant'; content: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function ask(message: string, topic?: string) {
    setBusy(true);
    setAsked(message);
    setError('');
    setAnswer(null);
    try {
      const result = await api<PlannerAnswer>('/planner/ask', { module_id: moduleId, topic, message, history });
      setAnswer(result);
      setHistory([...history.slice(-2), { role: 'user', content: message },
        { role: 'assistant', content: result.answer.slice(0, 2000) }]);
      if (!topic) setQuestion('');
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  return <section className="card planner-panel" aria-labelledby="planner-questions">
    <h2 id="planner-questions">Frag deinen KI-Planer</h2>
    <p className="muted">Die Antworten beziehen sich auf deine gespeicherten Daten und die Modulauswahl oben. Freie Fragen verarbeitet das lokale KI-Modell.</p>
    <div className="planner-actions">
      {quickQuestions.map(item => <Button key={item.id} className="secondary small" disabled={busy}
        onClick={() => void ask(item.label, item.id)}>{item.label}</Button>)}
    </div>
    <form className="planner-question-form" onSubmit={event => { event.preventDefault(); if (question.trim()) void ask(question.trim()); }}>
      <Field label="Deine Frage"><input value={question} onChange={event => setQuestion(event.target.value)}
        maxLength={1500} placeholder="Wann muss ich mich für die BI-Portfolioprüfung anmelden?" required /></Field>
      <Button type="submit" disabled={busy || !question.trim()}>Fragen <Icon name="arrow" size={16} /></Button>
    </form>
    {busy && <p role="status" className="muted">Antwort wird vorbereitet …</p>}
    {error && <ErrorBox error={error} />}
    {answer && <div className="planner-answer" role="status">
      <h3>{asked}</h3>
      {answer.generated ? <AnswerText text={answer.answer} sources={[]} /> : <p className="preserve-lines">{answer.answer}</p>}
      {answer.generated && <small className="muted">{answer.notice} Die Quellen zu Fristen findest du in der Terminliste.</small>}
    </div>}
  </section>;
}

function PlannerWorkspace({ modules, moduleId }: { modules: Module[]; moduleId: string }) {
  const { data, error, loading, reload } = useLoad(() => api<PlannerData>(`/planner${query({ module_id: moduleId })}`), [moduleId]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [message, setMessage] = useState('');
  const [deadline, setDeadline] = useState<{ event: PlanningEvent | null } | null>(null);
  const [studyBlock, setStudyBlock] = useState(false);

  async function change(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setActionError('');
    setMessage('');
    try { await action(); setMessage(success); reload(); }
    catch (cause) { setActionError(errorText(cause)); }
    finally { setBusy(false); }
  }

  if (error) return <ErrorBox error={error} retry={reload} />;
  if (!data) return <Loading />;

  const resume = data.resume || data.next_lesson;
  const resumeKind = resume && 'kind' in resume ? resume.kind : null;
  const resumeRoute = resumeKind === 'practice' ? 'learn' : resumeKind === 'tutor' ? 'tutor' : 'pages';
  const isPriority = (event: PlannerEvent) => event.status === 'planned' && (event.kind === 'deadline' || event.kind === 'exam');
  const priorities = data.events.filter(isPriority);
  const remaining = data.events.filter(event => !isPriority(event));
  const nextDeadline = priorities.find(event => !event.overdue);

  function eventCard(event: PlannerEvent) {
    return <EventCard key={event.id} event={event} modules={modules} today={data!.today} busy={busy || loading}
      overdue={event.overdue} onEdit={event.category ? item => setDeadline({ event: item }) : undefined}
      onStatus={item => void change(() => api(`/planning/events/${encodeURIComponent(item.id)}`,
        { status: item.status === 'done' ? 'planned' : 'done' }, 'PATCH'), 'Terminstatus gespeichert.')} />;
  }

  return <div className="planner-workspace" aria-busy={loading || busy}>
    <span className="sr-only" role="status">{message}</span>
    {actionError && <ErrorBox error={actionError} />}
    <div className="planner-overview">
      <section className="card planner-panel" aria-labelledby="planner-resume">
        <div className="eyebrow">LERNEN FORTSETZEN</div>
        <h2 id="planner-resume">Dein Wiedereinstieg</h2>
        {resume ? <>
          <Badge tone="teal">{resumeKind === 'checkpoint' ? 'Gespeicherter Lernpunkt' : resumeKind === 'practice' ? 'Letzte Übung' : resumeKind === 'tutor' ? 'Letztes Tutor-Lernziel' : 'Nächste offene Lernseite'}</Badge>
          <p><strong>{resume.title}</strong>{resume.section_title && ` · ${resume.section_title}`}<br /><span className="muted">{resume.module_name}</span></p>
          <a className="button" href={positionUrl(resume, resumeRoute)}>Weiterlernen <Icon name="arrow" size={16} /></a>
        </> : <p>Dein Wiedereinstieg erscheint, sobald du einen Lernpunkt speicherst oder eine Übung bearbeitest.</p>}
        {resumeKind !== 'checkpoint' && <p className="muted">Über „Hier weitermachen“ auf einer Lernseite kannst du einen Abschnitt speichern.</p>}
      </section>
      <section className="card planner-panel" aria-labelledby="planner-next">
        <div className="eyebrow">TERMINE UND AUFGABEN</div>
        <h2 id="planner-next">Als Nächstes</h2>
        {nextDeadline ? <p><strong>{nextDeadline.title}</strong><br /><time dateTime={nextDeadline.start}>{displayDate(nextDeadline)}</time> · {displayTime(nextDeadline)}</p> : <p>Hier ist keine bevorstehende Frist oder Prüfung eingetragen.</p>}
        {priorities.some(event => event.overdue) && <Badge tone="yellow">{priorities.filter(event => event.overdue).length} vergangene Termine mit offenem Status</Badge>}
        <div className="planner-actions">
          <a className="button secondary" href="#planner-dates" onClick={event => { event.preventDefault(); document.getElementById('planner-dates')?.focus(); }}>Zu den Fristen</a>
          <Button className="secondary" onClick={() => setStudyBlock(true)} disabled={!modules.length}>Lernblock planen</Button>
        </div>
      </section>
    </div>
    <PlannerQuestions moduleId={moduleId} />
    <section className="card planner-panel" aria-labelledby="planner-progress">
      <h2 id="planner-progress">Lernfortschritt nach Modul</h2>
      <p className="muted">Lernseiten markierst du selbst. Übungsfragen und erfasste Tutor-Lernziele werden aus deinem bisherigen Lernverlauf übernommen.</p>
      {data.content_errors && <p className="muted">Einige Lerninhalte konnten nicht geladen werden. Die Übersicht kann unvollständig sein.</p>}
      {!data.modules.length && <p>Es sind noch keine Studienmodule erfasst.</p>}
      {data.modules.map(module => <details key={module.id} className="planner-module" open={moduleId ? true : undefined}>
        <summary><strong>{module.name}</strong><span className="muted">{module.lessons.length
          ? `${module.lessons.filter(lesson => lesson.status === 'done').length} von ${module.lessons.length} Lernseiten bearbeitet`
          : 'Keine Lernseiten verfügbar'}</span></summary>
        {module.questions > 0 ? <p>{module.studied} von {module.questions} Übungsfragen bearbeitet · {module.questions - module.studied} offen · {module.mastered} gefestigt · {module.due} zur Wiederholung fällig</p>
          : <p className="muted">Für dieses Modul sind keine Übungsfragen erfasst.</p>}
        {!!module.lessons.length && <ul className="planner-lessons">{module.lessons.map(lesson => <li key={lesson.lesson_id}>
          <a href={positionUrl(lesson)}>{lesson.title}</a>
          <select value={lesson.status} aria-label={`Lernstand für ${lesson.title}`} disabled={busy || loading}
            onChange={event => { const status = event.target.value as LessonStatus;
              void change(() => saveLesson(module.id, lesson.lesson_id, status), 'Lernstand gespeichert.'); }}>
            {Object.entries(lessonStatuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </li>)}</ul>}
        {!!module.goals.length && <><h3>Erfasste Tutor-Lernziele</h3><ul className="planner-lessons">{module.goals.map(goal => <li key={goal.id}>
          <a href={positionUrl({ ...goal, module_id: module.id, module_name: module.name }, 'tutor')}>{goal.title}</a>
          <span><Badge tone={goal.due ? 'yellow' : 'neutral'}>{goal.label}{goal.due && ' · Wiederholung fällig'}</Badge></span>
        </li>)}</ul></>}
      </details>)}
    </section>
    <section className="card planner-panel" id="planner-dates" tabIndex={-1} aria-labelledby="planner-deadlines">
      <div className="section-head">
        <h2 id="planner-deadlines">Fristen und Termine</h2>
        <Button className="secondary" onClick={() => setDeadline({ event: null })}><Icon name="plus" size={16} />Frist hinzufügen</Button>
      </div>
      <p className="muted">Hier stehen die Termine aus deinen Unterlagen und deine eigenen Einträge. Modulübergreifende Fristen sind bei jeder Modulauswahl sichtbar. Alle Zeiten gelten für Berlin.</p>
      {!priorities.length && <p>Für diese Auswahl sind keine offenen Fristen oder Prüfungen eingetragen.</p>}
      {!!priorities.length && <ul className="planning-events">{priorities.map(eventCard)}</ul>}
      {!!remaining.length && <details className="planner-module"><summary>Weitere und erledigte Termine ({remaining.length})</summary>
        <ul className="planning-events">{remaining.map(eventCard)}</ul>
      </details>}
      {!!data.notes.length && <details className="planner-module"><summary>Hinweise aus den Terminunterlagen</summary>
        <ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul>
      </details>}
      <a className="text-button" href={`#plan${query({ module: moduleId })}`}>Gesamte Kalenderplanung öffnen <Icon name="arrow" size={16} /></a>
    </section>
    {deadline && <DeadlineForm modules={modules} moduleId={moduleId} today={data.today} existing={deadline.event}
      onClose={() => setDeadline(null)} onSaved={notice => { setDeadline(null); setMessage(notice); reload(); }} />}
    {studyBlock && <StudyBlockForm modules={modules} today={data.today} initialModule={resume?.module_id || moduleId}
      initialTitle={resume?.title} onClose={() => setStudyBlock(false)}
      onCreated={() => { setStudyBlock(false); setMessage('Lernblock gespeichert.'); reload(); }} />}
  </div>;
}

export function StudyPlannerPage({ modules }: { modules: Module[] }) {
  const [moduleId, setModuleId] = useState('');
  return <div className="study-planner">
    <PageTitle eyebrow="DEIN STUDIENSTAND" title="KI-Planer"
      description="Setze dein Lernen an der richtigen Stelle fort, sieh offene Themen und behalte Abgaben, Anmeldungen und Rückmeldung im Blick."
      action={<Field label="Studienmodul"><select value={moduleId} onChange={event => setModuleId(event.target.value)}>
        <option value="">Alle Module</option>
        {modules.map(module => <option key={module.id} value={module.id}>{module.name}</option>)}
      </select></Field>} />
    <PlannerWorkspace key={moduleId} moduleId={moduleId} modules={modules} />
  </div>;
}
