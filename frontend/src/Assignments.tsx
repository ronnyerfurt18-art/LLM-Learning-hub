import { useEffect, useMemo, useRef, useState } from 'react';
import { api, formatDate } from './api';
import { Badge, Button, Empty, ErrorBox, Icon, Loading, Progress, useLoad } from './components';
import { SourceDocumentLink, SourceLinks } from './SourceLinks';
import { Assignment, AssignmentQuestion, AssignmentsPackage } from './types';
import './assignments.css';

type StoredAnswer = { selected: string[]; checked: boolean };
type PracticeState = {
  signature: string;
  answers: Record<string, StoredAnswer>;
  currentQuestionId: string;
  roundIds: string[];
  finished: boolean;
};
type Props = { moduleId: string; initialAssignment?: string; onOpenAssignment: (id?: string) => void };

// Without a points table in the assignment's rules, each question scores the share of correctly judged statements.
function pointsFor(statements: number, correct: number, table?: number[]) {
  return table?.length === statements + 1 ? table[correct] || 0 : Math.round(correct / statements * 100);
}
const SOLUTION_NOTE = 'Die Musterlösungen wurden aus dem Kursmaterial hergeleitet. Sie sind keine offizielle Lösung der Einsendearbeiten.';

function contentSignature(assignment: Assignment) {
  return JSON.stringify(assignment.questions.map(question => [question.id, question.options.map(option => [option.id, option.text, option.is_correct])]));
}

function storageKey(moduleId: string, assignmentId: string) {
  return `mlh-assignments-v1:${moduleId}:${assignmentId}`;
}

function freshState(assignment: Assignment): PracticeState {
  return { signature: contentSignature(assignment), answers: {}, currentQuestionId: assignment.questions[0]?.id || '', roundIds: assignment.questions.map(question => question.id), finished: false };
}

function loadPractice(moduleId: string, assignment: Assignment): { state: PracticeState; storageProblem: boolean } {
  const fresh = freshState(assignment);
  try {
    const raw = localStorage.getItem(storageKey(moduleId, assignment.id));
    if (!raw) return { state: fresh, storageProblem: false };
    const saved = JSON.parse(raw);
    if (saved?.signature !== fresh.signature || !saved.answers || typeof saved.answers !== 'object') return { state: fresh, storageProblem: false };
    const answers: Record<string, StoredAnswer> = {};
    assignment.questions.forEach(question => {
      const answer = saved.answers[question.id];
      if (!answer || !Array.isArray(answer.selected)) return;
      const optionIds = new Set(question.options.map(option => option.id));
      answers[question.id] = { selected: [...new Set<string>(answer.selected.filter((id: unknown): id is string => typeof id === 'string' && optionIds.has(id)))], checked: answer.checked === true };
    });
    const questionIds = new Set(fresh.roundIds);
    const savedRound = Array.isArray(saved.roundIds) ? [...new Set<string>(saved.roundIds.filter((id: unknown): id is string => typeof id === 'string' && questionIds.has(id)))] : [];
    const roundIds = savedRound.length ? savedRound : fresh.roundIds;
    const currentQuestionId = roundIds.includes(saved.currentQuestionId) ? saved.currentQuestionId : roundIds[0] || '';
    return { state: { signature: fresh.signature, answers, currentQuestionId, roundIds, finished: saved.finished === true && roundIds.every(id => answers[id]?.checked) }, storageProblem: false };
  } catch {
    return { state: fresh, storageProblem: true };
  }
}

function questionResult(question: AssignmentQuestion, answer?: StoredAnswer, table?: number[]) {
  const correctStatements = answer?.checked ? question.options.filter(option => answer.selected.includes(option.id) === option.is_correct).length : 0;
  return {
    checked: answer?.checked === true,
    correctStatements,
    exact: answer?.checked === true && correctStatements === question.options.length,
    points: answer?.checked && answer.selected.length ? pointsFor(question.options.length, correctStatements, table) : 0,
  };
}

function assignmentResult(assignment: Assignment, answers: PracticeState['answers']) {
  return assignment.questions.reduce((total, question) => {
    const result = questionResult(question, answers[question.id], assignment.rules?.points);
    return { checked: total.checked + Number(result.checked), exact: total.exact + Number(result.exact), correctStatements: total.correctStatements + result.correctStatements, points: total.points + result.points };
  }, { checked: 0, exact: 0, correctStatements: 0, points: 0 });
}

function AssignmentCard({ assignment, moduleId, onOpen }: { assignment: Assignment; moduleId: string; onOpen: () => void }) {
  const result = assignmentResult(assignment, loadPractice(moduleId, assignment).state.answers);
  const statementCount = assignment.questions.reduce((count, question) => count + question.options.length, 0);
  return <article className="card assignment-card">
    <div className="assignment-card-top"><Badge tone="teal">Mehrfachauswahl</Badge><span><Icon name="clock" size={14} /> Abgabe: {formatDate(assignment.due_date)}</span></div>
    <h3>{assignment.title}</h3>
    <p>{assignment.questions.length} Fragen · {statementCount} Aussagen. Beurteile jede Aussage und erhalte die Erklärung mit der passenden Fundstelle.</p>
    {result.checked > 0 && <div className="assignment-card-progress"><Progress value={result.checked / assignment.questions.length * 100} label={`Bearbeitete Fragen: ${result.checked} von ${assignment.questions.length}`} /><span>{result.checked} von {assignment.questions.length} Fragen geprüft · {result.exact} exakt richtig</span></div>}
    <Button onClick={onOpen}>{result.checked ? 'Übung fortsetzen' : 'Fragen üben'} <Icon name="arrow" size={17} /></Button>
    <SourceLinks sources={[assignment.source]} title="Original der Einsendearbeit" pdfLabel="Original-PDF öffnen" />
  </article>;
}

function AssignmentPractice({ assignment, moduleId, onBack }: { assignment: Assignment; moduleId: string; onBack: () => void }) {
  const [initial] = useState(() => loadPractice(moduleId, assignment));
  const [state, setState] = useState(initial.state);
  const [storageProblem, setStorageProblem] = useState(initial.storageProblem);
  const questionHeading = useRef<HTMLHeadingElement>(null);
  const feedbackHeading = useRef<HTMLHeadingElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const questionsById = useMemo(() => new Map(assignment.questions.map(question => [question.id, question])), [assignment]);
  const roundQuestions = state.roundIds.flatMap(id => { const question = questionsById.get(id); return question ? [question] : []; });
  const index = Math.max(0, roundQuestions.findIndex(question => question.id === state.currentQuestionId));
  const question = roundQuestions[index];
  const answer = state.answers[question?.id] || { selected: [], checked: false };
  const result = question && questionResult(question, answer, assignment.rules?.points);
  const totals = assignmentResult(assignment, state.answers);
  const statementCount = assignment.questions.reduce((count, item) => count + item.options.length, 0);
  const roundComplete = roundQuestions.length > 0 && roundQuestions.every(item => state.answers[item.id]?.checked);
  const wrongIds = assignment.questions.filter(item => { const result = questionResult(item, state.answers[item.id], assignment.rules?.points); return result.checked && !result.exact; }).map(item => item.id);
  const unchecked = roundQuestions.find(item => !state.answers[item.id]?.checked);
  const roundChecked = roundQuestions.filter(item => state.answers[item.id]?.checked).length;
  const reducedRound = roundQuestions.length < assignment.questions.length;

  useEffect(() => {
    try { localStorage.setItem(storageKey(moduleId, assignment.id), JSON.stringify(state)); setStorageProblem(false); }
    catch { setStorageProblem(true); }
  }, [moduleId, assignment.id, state]);

  function focusQuestion() {
    requestAnimationFrame(() => {
      questionHeading.current?.scrollIntoView({ block: 'start', behavior: 'auto' });
      questionHeading.current?.focus({ preventScroll: true });
    });
  }
  function openQuestion(id: string) {
    setState(previous => ({ ...previous, currentQuestionId: id, finished: false }));
    focusQuestion();
  }
  function updateSelection(optionId: string) {
    if (!question || answer.checked) return;
    setState(previous => {
      const current = previous.answers[question.id] || { selected: [], checked: false };
      const selected = current.selected.includes(optionId) ? current.selected.filter(id => id !== optionId) : [...current.selected, optionId];
      return { ...previous, answers: { ...previous.answers, [question.id]: { selected, checked: false } } };
    });
  }
  function checkAnswer() {
    if (!question || answer.checked) return;
    setState(previous => ({ ...previous, answers: { ...previous.answers, [question.id]: { selected: [...answer.selected], checked: true } } }));
    requestAnimationFrame(() => feedbackHeading.current?.focus({ preventScroll: true }));
  }
  function restart(ids: string[]) {
    if (!ids.length) return;
    setState(previous => {
      const answers = { ...previous.answers };
      ids.forEach(id => { delete answers[id]; });
      return { ...previous, answers, roundIds: ids, currentQuestionId: ids[0], finished: false };
    });
    focusQuestion();
  }
  function showResult() {
    setState(previous => ({ ...previous, finished: true }));
    requestAnimationFrame(() => { resultHeading.current?.scrollIntoView({ block: 'start', behavior: 'auto' }); resultHeading.current?.focus({ preventScroll: true }); });
  }

  return <section className="assignment-practice" aria-label={assignment.title}>
    <button className="text-button assignment-back" onClick={onBack}><span aria-hidden="true">←</span> Alle Einsendearbeiten</button>
    <div className="assignment-heading"><div><span className="eyebrow">EINSENDEARBEIT · ÜBUNG</span><h2>{assignment.title}</h2><p>Abgabe laut Original: {formatDate(assignment.due_date)} · {assignment.questions.length} Fragen · {statementCount} Aussagen</p></div>
      <SourceDocumentLink path={assignment.source.path} page={assignment.source.kind === 'video' ? undefined : assignment.source.pdf_page}>Original-PDF öffnen</SourceDocumentLink>
    </div>
    <aside className="assignment-solution-note"><Icon name="book" size={18} /><p>{assignment.solution_note || SOLUTION_NOTE}</p></aside>
    <p className="assignment-local-note">Dein Übungsstand wird in diesem Browser gespeichert. Die Übung verändert deinen Lernfortschritt im Lerntraining nicht.</p>
    {storageProblem && <div className="alert warning" role="status">Der Browser kann den Übungsstand derzeit nicht dauerhaft speichern. Du kannst hier weiterüben; beim Schließen kann der Stand verloren gehen.</div>}
    <details className="assignment-rules"><summary>So übst und bewertest du die Antworten</summary><p>Markiere alle Aussagen, die du für richtig hältst. Eine unmarkierte Aussage beurteilst du als falsch. Es können mehrere Aussagen richtig sein. Mit „Antwort prüfen“ zeigst du die Lösung und Fundstellen an.</p>
      <p>{assignment.rules?.points ? `Originalbewertung je Frage: ${assignment.rules.points.map((_, index) => index).join(' / ')} korrekt beurteilte Aussagen ergeben ${assignment.rules.points.join(' / ')} Punkte.` : 'Bewertung je Frage: Der Anteil korrekt beurteilter Aussagen ergibt 0 bis 100 Punkte.'} Eine leere Auswahl erhält immer 0 Punkte. Eine Frage ist exakt richtig, wenn alle Aussagen korrekt beurteilt wurden.</p>
    </details>
    <div className="assignment-overall-progress"><div><span>{reducedRound ? 'Wiederholungsrunde' : 'Deine Übungsrunde'}</span><strong>{roundChecked} / {roundQuestions.length} Fragen geprüft</strong></div><Progress value={roundQuestions.length ? roundChecked / roundQuestions.length * 100 : 0} label="Geprüfte Fragen in dieser Runde" /></div>
    {state.finished ? <section className="card assignment-result" aria-labelledby="assignment-result-title"><Icon name="check" size={28} /><h3 id="assignment-result-title" ref={resultHeading} tabIndex={-1}>{roundComplete ? 'Runde abgeschlossen' : 'Dein Zwischenstand'}</h3>
      <p>{roundComplete ? `Du hast alle ${roundQuestions.length} Fragen dieser Runde geprüft.` : `Du hast ${roundChecked} von ${roundQuestions.length} Fragen dieser Runde geprüft.`} Die Übersicht zeigt deinen aktuellen Stand für die gesamte Einsendearbeit.</p>
      <dl className="assignment-result-stats"><div><dt>Exakt richtige Fragen</dt><dd>{totals.exact} <small>/ {assignment.questions.length}</small></dd></div><div><dt>Korrekt beurteilte Aussagen</dt><dd>{totals.correctStatements} <small>/ {statementCount}</small></dd></div><div><dt>{assignment.rules?.points ? 'Originalpunkte' : 'Punkte'}</dt><dd>{totals.points} <small>/ {assignment.questions.length * 100}</small></dd></div></dl>
      <p className="muted">{totals.checked} von {assignment.questions.length} Fragen sind geprüft. Ungeprüfte Fragen zählen mit 0 Punkten. Die Punkte beruhen auf den aus dem Kursmaterial hergeleiteten Musterlösungen.</p>
      <div className="button-row">{unchecked && <Button onClick={() => openQuestion(unchecked.id)}>Offene Fragen weiterüben <Icon name="arrow" size={16} /></Button>}{wrongIds.length > 0 && <Button onClick={() => restart(wrongIds)}>Falsche Fragen erneut üben ({wrongIds.length}) <Icon name="repeat" size={16} /></Button>}<Button className="secondary" onClick={() => restart(assignment.questions.map(item => item.id))}>Alle Fragen wiederholen</Button></div>
      {totals.checked > 0 && wrongIds.length === 0 && <p className="assignment-all-correct">Alle bisher geprüften Fragen sind exakt richtig.</p>}
    </section> : question && result ? <article className="card assignment-question" aria-labelledby="assignment-question-title">
      <div className="assignment-question-position"><span>{reducedRound ? 'Wiederholung' : 'Frage'} {index + 1} von {roundQuestions.length} · Originalfrage {question.number}</span><SourceDocumentLink path={assignment.source.path} page={question.source_page}>Aufgabe im Original</SourceDocumentLink></div>
      <h3 id="assignment-question-title" ref={questionHeading} tabIndex={-1}>{question.title || `Frage ${question.number}`}</h3>
      <p className="assignment-prompt preserve-lines">{question.prompt}</p>
      <form onSubmit={event => { event.preventDefault(); checkAnswer(); }}>
        <fieldset className="assignment-options"><legend className="sr-only">Beurteile die Aussagen A bis E. Markiere die richtigen Aussagen.</legend>
          {question.options.map(option => {
            const selected = answer.selected.includes(option.id);
            const judgedCorrectly = selected === option.is_correct;
            return <div className={`assignment-option${answer.checked ? judgedCorrectly ? ' is-correct' : ' is-incorrect' : ''}`} key={option.id}>
              <label className="assignment-option-label" htmlFor={`assignment-${question.id}-${option.id}`}><input id={`assignment-${question.id}-${option.id}`} type="checkbox" checked={selected} disabled={answer.checked} onChange={() => updateSelection(option.id)} /><span className="assignment-option-letter">{option.id}</span><span className="preserve-lines">{option.text}</span></label>
              {answer.checked && <div className="assignment-option-feedback"><div className="assignment-option-verdict"><Badge tone={judgedCorrectly ? 'green' : 'red'}>{judgedCorrectly ? 'Richtig beurteilt' : 'Falsch beurteilt'}</Badge><span>Deine Beurteilung: {selected ? 'richtig' : 'falsch'} · Die Aussage ist <strong>{option.is_correct ? 'richtig' : 'falsch'}</strong>.</span></div><p><strong>{option.is_correct ? 'Begründung: ' : 'Korrektur: '}</strong>{option.explanation}</p><SourceLinks sources={option.sources} title="Hier kannst du es nachlesen" /></div>}
            </div>;
          })}
        </fieldset>
        {!answer.checked && <div className="assignment-check"><p>{answer.selected.length ? `${answer.selected.length} ${answer.selected.length === 1 ? 'Aussage als richtig markiert' : 'Aussagen als richtig markiert'}. Alle anderen beurteilst du als falsch.` : 'Noch keine Aussage markiert. Eine leere Auswahl beurteilt alle Aussagen als falsch und erhält 0 Punkte.'}</p><Button type="submit">Antwort prüfen <Icon name="check" size={17} /></Button></div>}
      </form>
      {answer.checked && <section className={`assignment-feedback-summary${result.exact ? ' is-exact' : ''}`} aria-labelledby="assignment-feedback-title"><h4 id="assignment-feedback-title" ref={feedbackHeading} tabIndex={-1}>{result.exact ? 'Frage exakt richtig gelöst' : 'Antwort geprüft'}</h4><p><strong>{result.correctStatements} von {question.options.length}</strong> Aussagen korrekt beurteilt · <strong>{result.points} von 100</strong> Punkten.{!answer.selected.length ? ' Leere Auswahl: laut Originalbewertung 0 Punkte.' : ''}</p><button className="text-button" onClick={() => { setState(previous => ({ ...previous, answers: { ...previous.answers, [question.id]: { selected: [], checked: false } } })); focusQuestion(); }}>Diese Frage erneut üben <Icon name="repeat" size={15} /></button></section>}
      <nav className="assignment-question-navigation" aria-label="Fragen wechseln"><Button className="secondary" disabled={index === 0} onClick={() => openQuestion(roundQuestions[index - 1].id)}>← Vorherige Frage</Button>{index < roundQuestions.length - 1 ? <Button className={answer.checked ? '' : 'secondary'} onClick={() => openQuestion(roundQuestions[index + 1].id)}>Nächste Frage <Icon name="arrow" size={16} /></Button> : <Button onClick={showResult}>{roundComplete ? 'Ergebnis ansehen' : 'Zwischenstand ansehen'} <Icon name="chart" size={16} /></Button>}</nav>
    </article> : <Empty title="Noch keine Fragen vorhanden">Die Fragen dieser Einsendearbeit werden noch vorbereitet.</Empty>}
    <section className="assignment-question-overview" aria-labelledby="assignment-overview-title"><div className="assignment-overview-heading"><h3 id="assignment-overview-title">Fragenübersicht</h3>{!state.finished && <button className="text-button" onClick={showResult}>Ergebnis ansehen <Icon name="chart" size={15} /></button>}</div>
      <p>Ein Haken bedeutet: alle Aussagen korrekt beurteilt. „Noch Fehler“ zeigt mindestens eine falsche Beurteilung.</p>
      <ol>{assignment.questions.map(item => { const itemResult = questionResult(item, state.answers[item.id], assignment.rules?.points); const current = !state.finished && question?.id === item.id; return <li key={item.id}><button aria-current={current ? 'step' : undefined} className={itemResult.checked ? itemResult.exact ? 'is-correct' : 'is-incorrect' : ''} onClick={() => { if (!state.roundIds.includes(item.id)) setState(previous => ({ ...previous, roundIds: assignment.questions.map(question => question.id), currentQuestionId: item.id, finished: false })); else openQuestion(item.id); if (!state.roundIds.includes(item.id)) focusQuestion(); }}><span className="assignment-question-number">{itemResult.exact ? <Icon name="check" size={16} /> : item.number}</span><span><strong>{item.number}. {item.title || 'Frage'}</strong><small>{itemResult.checked ? `${itemResult.exact ? 'Exakt richtig' : 'Noch Fehler'} · ${itemResult.correctStatements}/${item.options.length} Aussagen · ${itemResult.points} Punkte` : state.answers[item.id]?.selected.length ? 'Auswahl noch nicht geprüft' : 'Noch nicht geprüft'}</small></span></button></li>; })}</ol>
    </section>
  </section>;
}

export function Assignments({ moduleId, initialAssignment = '', onOpenAssignment }: Props) {
  const { data, loading, error, reload } = useLoad(() => api<AssignmentsPackage>(`/assignments/${encodeURIComponent(moduleId)}`), [moduleId]);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const assignments = data?.assignments || [];
  if (!assignments.length) return <Empty title="Einsendearbeiten noch in Vorbereitung">Hier findest du die Originalfragen, sobald die Einsendearbeiten bereitstehen.</Empty>;
  const assignment = assignments.find(item => item.id === initialAssignment);
  if (initialAssignment && !assignment) return <Empty title="Diese Einsendearbeit ist nicht verfügbar" action={<Button onClick={() => onOpenAssignment()}>Alle Einsendearbeiten</Button>}>Wähle eine der veröffentlichten Einsendearbeiten aus der Übersicht.</Empty>;
  if (assignment) return <AssignmentPractice key={`${assignment.id}-${contentSignature(assignment)}`} moduleId={moduleId} assignment={assignment} onBack={() => onOpenAssignment()} />;
  return <section className="assignments" aria-labelledby="assignments-title"><div className="assignments-intro"><span className="eyebrow">ORIGINALFRAGEN MIT ERKLÄRUNGEN</span><h2 id="assignments-title">Einsendearbeiten</h2><p>Übe beide Einsendearbeiten mit den Multiple-Choice-Fragen aus den Originalen. Nach jeder Antwort siehst du für jede Aussage, ob deine Beurteilung richtig war, den richtigen Sachverhalt und die passende Quelle.</p></div><aside className="assignment-solution-note"><Icon name="book" size={18} /><p>{SOLUTION_NOTE}</p></aside><div className="assignment-cards">{assignments.map(item => <AssignmentCard key={item.id} moduleId={moduleId} assignment={item} onOpen={() => onOpenAssignment(item.id)} />)}</div><p className="assignment-local-note">Dein Übungsstand bleibt browserlokal. Die Ergebnisse werden unabhängig vom Lerntraining gespeichert.</p></section>;
}
