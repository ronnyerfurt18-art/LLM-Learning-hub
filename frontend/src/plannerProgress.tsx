import { useState } from 'react';
import { api, errorText, query } from './api';
import { Button, ErrorBox, useLoad } from './components';

export const lessonStatuses = { open: 'Offen', started: 'In Arbeit', done: 'Bearbeitet' };
export type LessonStatus = keyof typeof lessonStatuses;

export function saveLesson(moduleId: string, lessonId: string, status: LessonStatus, sectionId?: string) {
  return api<{ status: LessonStatus }>('/planner/progress', {
    module_id: moduleId, lesson_id: lessonId, status, section_id: sectionId,
  });
}

export function LessonProgressControl({ moduleId, lessonId, sections, initialSection }: {
  moduleId: string; lessonId: string; sections: { id: string; title: string }[]; initialSection: string;
}) {
  const { data, setData, loading, error, reload } = useLoad(() => api<{ status: LessonStatus }>(
    `/planner/lesson-status${query({ module_id: moduleId, lesson_id: lessonId })}`), [moduleId, lessonId]);
  const [section, setSection] = useState(sections.some(item => item.id === initialSection) ? initialSection : '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [actionError, setActionError] = useState('');
  async function save(status: LessonStatus, sectionId?: string) {
    setBusy(true);
    setMessage('');
    setActionError('');
    try {
      setData(await saveLesson(moduleId, lessonId, status, sectionId));
      setMessage(sectionId !== undefined ? 'Wiedereinstieg gespeichert.' : 'Lernstand gespeichert.');
    } catch (cause) { setActionError(errorText(cause)); }
    finally { setBusy(false); }
  }
  return <section className="card planner-lesson-controls" aria-label="Lernstand für diese Lernseite">
    <div className="planner-actions">
      <strong>Lernstand</strong>
      <select aria-label="Status dieser Lernseite" value={data?.status || 'open'}
        onChange={event => void save(event.target.value as LessonStatus)} disabled={loading || busy || !!error}>
        {Object.entries(lessonStatuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select>
      <select aria-label="Abschnitt für den Wiedereinstieg" value={section} onChange={event => setSection(event.target.value)}>
        <option value="">Seitenanfang</option>
        {sections.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      <Button className="secondary small" disabled={loading || busy || !!error} onClick={() => void save('started', section)}>Hier weitermachen</Button>
      <a className="text-button" href="#planner">KI-Planer öffnen</a>
    </div>
    <span role="status" className="muted">{message}</span>
    {error && <ErrorBox error={error} retry={reload} />}
    {actionError && <ErrorBox error={actionError} />}
  </section>;
}
