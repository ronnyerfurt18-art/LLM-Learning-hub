import { useEffect, useState } from 'react';
import { api, errorText, formatDate } from './api';
import { SourceLinks } from './SourceLinks';
import { SourceRef } from './types';

type Event = { id: string; created_at: string; outcome: string; answer: string; note: string; voided: number };
type Goal = { id: string; title: string; question: string; criteria: string; kind: string; label: string; due: boolean; next_due: string | null; events: Event[]; sources: SourceRef[] };
type Overview = { goals: Goal[]; due_count: number; next_goal_id: string | null; coverage: string };
export function LearningMemory({ moduleId, goalId, disabled, lastAnswer, onSelect, onQuestion }: { moduleId: string; goalId: string; disabled: boolean; lastAnswer: string; onSelect: (id: string) => void; onQuestion: (text: string) => void }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState('');
  const [note, setNote] = useState('');
  const [outcome, setOutcome] = useState('unclear');
  const [withoutHelp, setWithoutHelp] = useState(false);
  const [notice, setNotice] = useState('');
  const [version, setVersion] = useState(0);
  const [attemptId, setAttemptId] = useState(() => crypto.randomUUID());
  useEffect(() => { let active = true; setData(null); setError(''); api<Overview>(`/tutor/learning-memory?module_id=${encodeURIComponent(moduleId)}`).then(d => { if (active) setData(d); }).catch(e => { if (active) setError(errorText(e)); }); return () => { active = false; }; }, [moduleId, version]);
  useEffect(() => { setAnswer(''); setNote(''); setOutcome('unclear'); setWithoutHelp(false); setNotice(''); setAttemptId(crypto.randomUUID()); }, [goalId]);
  const goal = data?.goals.find(g => g.id === goalId);
  const save = async () => { setBusy(true); setError(''); try { setData(await api('/tutor/learning-memory', { id: attemptId, module_id: moduleId, goal_id: goalId, answer, note, outcome, without_help: withoutHelp })); setAttemptId(crypto.randomUUID()); setNotice('Selbsteinschätzung dauerhaft gespeichert.'); setAnswer(''); setNote(''); setWithoutHelp(false); setOutcome('unclear'); } catch(e) { setError(errorText(e)); } finally { setBusy(false); } };
  const undo = async (eventId: string) => { setBusy(true); setError(''); try { setData(await api('/tutor/learning-memory/undo', { module_id: moduleId, goal_id: goalId, event_id: eventId })); setNotice('Bewertung zurückgenommen; Lernstand neu berechnet.'); } catch(e) { setError(errorText(e)); } finally { setBusy(false); } };
  return <details className="tutor-memory">
    <summary>Dein Lernprotokoll {goal && <small>· {goal.title}</small>} {data && data.due_count > 0 && <small>· {data.due_count} fällig</small>}</summary>
    {error && <p role="alert">{error} <button type="button" onClick={() => setVersion(v => v + 1)}>Erneut laden</button></p>}
    {!data && !error && <p role="status">Lernstand wird geladen …</p>}
    {data && !data.goals.length && <p>Für dieses Modul sind noch keine überprüfbaren Lernziele erfasst. Es wird noch kein Verständnisfortschritt berechnet.</p>}
    {!!data?.goals.length && <>
      <p>{data.coverage}</p>
      <label>Lernziel auswählen<select disabled={disabled || busy} value={goalId} onChange={e => onSelect(e.target.value)}><option value="">Freies Gespräch ohne Lernziel</option>{data.goals.map(g => <option key={g.id} value={g.id}>{g.due ? '↻ ' : ''}{g.title} · {g.label}</option>)}</select></label>
      {data.next_goal_id && <button type="button" className="button secondary small" disabled={disabled || busy} onClick={() => onSelect(data.next_goal_id!)}>Nächstes empfohlenes Lernziel</button>}
      {goal && <>
        <p><strong>{goal.label}</strong> · Selbsteinschätzung · Wiederholung: {formatDate(goal.next_due || undefined)}{goal.due ? ' (fällig)' : ''}</p>
        <p>{goal.kind}</p><p><strong>{goal.question}</strong></p>
        <div className="button-row"><button type="button" className="button secondary small" disabled={disabled || busy} onClick={() => onQuestion('Erkläre mir zuerst das aktuelle Lernziel mit einem einfachen Beispiel. Stelle danach eine leichte Verständnisfrage.')}>Mit Erklärung starten</button><button type="button" className="button secondary small" disabled={disabled || busy} onClick={() => onQuestion('Prüfe jetzt das aktuelle Lernziel mit genau einer Frage, ohne Lösung oder Antwortkriterien vorwegzunehmen. Warte auf meine Antwort.')}>Im Chat prüfen</button></div>
        <details key={goal.id}><summary>Eigene Antwort prüfen und Lernstand speichern</summary>
          <p>Nur deine eigene Leistung bewerten. Nachgesprochene Lösungen und Antworten mit inhaltlichen Hinweisen zählen als „Mit Hilfe“. KI-Lob ist kein Nachweis.</p>
          <label>Deine Antwort<textarea value={answer} maxLength={12000} rows={4} disabled={busy} onChange={e => setAnswer(e.target.value)} /></label>
          {!!lastAnswer && <button type="button" className="text-button" disabled={busy} onClick={() => setAnswer(lastAnswer)}>Letzten eigenen Chatbeitrag übernehmen</button>}
          <details><summary>Antwortkriterien und Quellen zum Abgleichen</summary><p>{goal.criteria}</p><SourceLinks sources={goal.sources} title="Prüfgrundlage" /></details>
          <label>Deine Einschätzung<select value={outcome} disabled={busy} onChange={e => setOutcome(e.target.value)}><option value="unclear">Bewertung noch unklar</option><option value="treated">Nur behandelt / gelesen</option><option value="incorrect">Noch nicht richtig beantwortet</option><option value="helped">Mit Hilfe gelöst</option><option value="independent">Selbstständig richtig beantwortet</option></select></label>
          {outcome === 'independent' && <label className="tutor-memory-check"><input type="checkbox" checked={withoutHelp} disabled={busy} onChange={e => setWithoutHelp(e.target.checked)} />Ich habe vor dem Ansehen der Kriterien ohne inhaltliche Hilfe geantwortet und meine Antwort damit abgeglichen.</label>}
          <label>Was fehlt oder war schwierig?<textarea value={note} rows={2} maxLength={2000} disabled={busy} onChange={e => setNote(e.target.value)} /></label>
          <button type="button" className="button" disabled={busy || disabled || (outcome !== 'treated' && !answer.trim()) || (outcome === 'independent' && !withoutHelp)} onClick={() => void save()}>Lernstand speichern</button>
        </details>
        <details><summary>Gespeicherte Versuche ({goal.events.filter(e => !e.voided).length})</summary>{goal.events.map(e => <article key={e.id}><strong>{new Date(e.created_at).toLocaleString('de-DE')} · {e.voided ? 'Zurückgenommen' : ({treated:'Behandelt',incorrect:'Noch nicht richtig',helped:'Mit Hilfe',independent:'Selbstständig',unclear:'Unklar'} as Record<string,string>)[e.outcome]}</strong><p className="preserve-lines">{e.answer}</p>{e.note && <p>Offen: {e.note}</p>}{!e.voided && <button type="button" className="text-button" disabled={busy || disabled} onClick={() => void undo(e.id)}>Bewertung zurücknehmen</button>}</article>)}</details>
      </>}
      <p className="tutor-notice">Ein späterer selbstständiger Versuch frühestens nach 24 Stunden bestätigt das Ziel. Lernstände bleiben bei Modellwechsel und Neustart erhalten.</p>
    </>}
    {notice && <p role="status">{notice}</p>}
  </details>;
}
