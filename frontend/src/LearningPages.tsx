import { LessonProgressControl } from './plannerProgress';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api, query } from './api';
import { Badge, Button, Empty, ErrorBox, Field, Icon, Loading, PageTitle, useLoad } from './components';
import { TrainingQuestion } from './Learning';
import { ModuleBigPicture } from './ModuleBigPicture';
import { TutorEntryLink } from './LearningTutor';
import { PlanningPreview } from './Planning';
import { SourceLinks } from './SourceLinks';
import { Assignments } from './Assignments';
import { LearningLesson, LearningPagesPackage, LearningPagesSummary, LearningPagesTab, LearningSection, Module, Question } from './types';
import { unitLabel as unitLabelOf } from './unitLabel';
import './learning-pages.css';

type LearningPagesProps = {
  modules: Module[];
  initialModule: string;
  initialLesson?: string;
  initialSection?: string;
  initialConcept?: string;
  initialTab?: LearningPagesTab;
  initialAssignment?: string;
  searchNavigation?: number;
  onOpenLesson: (moduleId: string, lessonId: string) => void;
  onOpenModule: (moduleId: string) => void;
  onOpenTraining: (moduleId: string, unit: number) => void;
  onOpenTab: (moduleId: string, tab: LearningPagesTab, assignmentId?: string) => void;
};

function sectionId(lessonId: string, section: string) {
  return `learning-page-${lessonId}-${section}`;
}

function goToSection(id: string) {
  const target = document.getElementById(id);
  if (!target) return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  target.focus({ preventScroll: true });
}

function OriginalDiagram({ image }: { image: NonNullable<LearningSection['image']> }) {
  const [failed, setFailed] = useState(false);
  const url = `/api/assets/${image.path.split('/').map(encodeURIComponent).join('/')}`;
  const caption = image.caption || 'Abbildung aus dem Lehrbrief';
  return <figure className="learning-page-diagram">
    {failed ? <p className="learning-page-image-error" role="status">Die Abbildung konnte nicht angezeigt werden. Du kannst sie über den Link öffnen.</p> :
      <a href={url} target="_blank" rel="noreferrer" aria-label={`${caption} – in voller Größe öffnen`}>
        <img src={url} alt={caption} loading="lazy" onError={() => setFailed(true)} />
      </a>}
    <figcaption><span>{caption}{image.source_page ? ` · PDF-Seite ${image.source_page}` : ''}</span>
      <a href={url} target="_blank" rel="noreferrer">Abbildung öffnen <Icon name="search" size={13} /></a>
    </figcaption>
  </figure>;
}

function LessonSection({ section, lessonId, moduleId, selected = false }: { section: LearningSection; lessonId: string; moduleId: string; selected?: boolean }) {
  return <section className={`learning-page-section${selected ? ' is-search-target' : ''}`} aria-labelledby={sectionId(lessonId, section.id)}>
    <h2 id={sectionId(lessonId, section.id)} tabIndex={-1}>{section.title}</h2>
    {section.paragraphs.map((paragraph, index) => <p className="preserve-lines" key={index}>{paragraph}</p>)}
    {!!section.bullets?.length && <ul className="learning-page-list">{section.bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}</ul>}
    {section.table && <div className="learning-page-table-wrap" role="region" tabIndex={0} aria-label={`Tabelle: ${section.title}`}>
      <table className="learning-page-table"><caption className="sr-only">{section.title}</caption>
        <thead><tr>{section.table.headers.map((header, index) => <th scope="col" key={index}>{header}</th>)}</tr></thead>
        <tbody>{section.table.rows.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column}>{cell}</td>)}</tr>)}</tbody>
      </table>
    </div>}
    {section.image && <OriginalDiagram key={section.image.path} image={section.image} />}
    {section.note && <aside className="learning-page-note"><strong>Für dein Verständnis</strong><p className="preserve-lines">{section.note}</p></aside>}
    <SourceLinks sources={section.sources} />
    <a className="text-button tutor-section-link" href={`#tutor${query({ module: moduleId, lesson: lessonId, section: section.id })}`}><Icon name="learn" size={16} /> Diesen Abschnitt mit KI lernen</a>
  </section>;
}

function LessonExercises({ lesson, moduleId, unitLabel = 'Einheit', onOpenTraining }: {
  lesson: LearningLesson;
  moduleId: string;
  unitLabel?: string;
  onOpenTraining: (moduleId: string, unit: number) => void;
}) {
  const [started, setStarted] = useState(false);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(0);
  const [skipped, setSkipped] = useState(0);
  const [finished, setFinished] = useState(false);
  const [round, setRound] = useState(0);
  const exerciseKey = lesson.exercise_ids.join('|');
  const { data, error, loading, reload } = useLoad(() => started && lesson.exercise_ids.length
    ? api<Question[]>(`/questions${query({ module_id: moduleId })}`)
    : Promise.resolve<Question[]>([]), [started, moduleId, exerciseKey]);
  const selected = useMemo(() => {
    const questions = new Map((data || []).map(question => [question.id, question]));
    return lesson.exercise_ids.flatMap(id => {
      const question = questions.get(id);
      return question ? [question] : [];
    });
  }, [data, exerciseKey]);
  const missing = lesson.exercise_ids.length - selected.length;
  const question = selected[index];
  const roundTitle = useRef<HTMLHeadingElement>(null);
  const restart = () => {
    setIndex(0); setDone(0); setSkipped(0); setFinished(false); setRound(value => value + 1); reload();
  };
  return <section className="learning-page-exercises" aria-labelledby={sectionId(lesson.id, 'exercises')}>
    <div className="learning-page-exercise-heading">
      <div><span className="eyebrow">VERSTÄNDNIS PRÜFEN</span><h2 id={sectionId(lesson.id, 'exercises')} tabIndex={-1} ref={roundTitle}>Übe zu dieser Lernseite</h2></div>
      <button className="text-button" onClick={() => onOpenTraining(moduleId, lesson.unit)}>{unitLabel} im Lerntraining <Icon name="arrow" size={16} /></button>
    </div>
    {!lesson.exercise_ids.length ? <div className="learning-page-exercise-intro"><p>Für diese Lernseite sind noch keine Aufgaben verknüpft. Du kannst die verfügbaren Aufgaben der Kurseinheit im Lerntraining öffnen.</p></div> :
      !started ? <div className="learning-page-exercise-intro"><p>Formuliere zuerst deine eigene Antwort. Anschließend vergleichst du sie mit der Musterlösung und erhältst die Erklärung.</p>
        <p className="muted">{lesson.exercise_ids.length} {lesson.exercise_ids.length === 1 ? 'Aufgabe ist' : 'Aufgaben sind'} mit dieser Lernseite verknüpft. Deine bearbeiteten Antworten werden im Lerntraining gespeichert.</p>
        <Button onClick={() => setStarted(true)}>Aufgaben laden <Icon name="learn" size={17} /></Button>
      </div> : loading ? <Loading /> : error ? <ErrorBox error={error} retry={reload} /> : <>
        {missing > 0 && <div className="alert warning" role="status"><strong>{missing} {missing === 1 ? 'verknüpfte Aufgabe ist' : 'verknüpfte Aufgaben sind'} derzeit nicht verfügbar.</strong>
          <p>{selected.length ? `Diese Runde enthält ${selected.length} von ${lesson.exercise_ids.length} verknüpften Aufgaben. Die fehlenden Aufgaben werden nicht als bearbeitet gezählt.` : 'Die Aufgaben konnten in der Fragenbank nicht gefunden werden. Die Lernseite bleibt verfügbar.'}</p>
        </div>}
        {!selected.length ? <div className="learning-page-exercise-intro"><Button className="secondary" onClick={reload}>Verfügbarkeit erneut prüfen <Icon name="refresh" size={16} /></Button></div> :
          finished ? <div className="learning-page-round-complete" role="status"><Icon name="check" size={26} /><h3>Runde beendet</h3>
            <p>{done} von {selected.length} Aufgaben bearbeitet.{skipped > 0 ? ` ${skipped} ${skipped === 1 ? 'Aufgabe wurde' : 'Aufgaben wurden'} übersprungen.` : ''}{missing > 0 ? ' Die Runde umfasst nur die verfügbaren Aufgaben.' : ''}</p>
            <div className="button-row"><Button onClick={restart}>Aufgaben noch einmal üben <Icon name="repeat" size={16} /></Button>
              <Button className="secondary" onClick={() => onOpenTraining(moduleId, lesson.unit)}>{unitLabel} weitertrainieren</Button></div>
          </div> : question && <>
            <div className="learning-page-exercise-position" aria-live="polite"><span>Aufgabe {index + 1} von {selected.length}</span><span>{done} bearbeitet{skipped ? ` · ${skipped} übersprungen` : ''}</span></div>
            <TrainingQuestion key={`${round}-${question.id}-${index}`} question={question} unitLabel={unitLabel} onNext={completed => {
              if (completed) setDone(value => value + 1); else setSkipped(value => value + 1);
              if (index + 1 >= selected.length) { setFinished(true); roundTitle.current?.focus({ preventScroll: true }); }
              else { setIndex(value => value + 1); goToSection(sectionId(lesson.id, 'exercises')); }
            }} />
          </>}
      </>}
  </section>;
}

function ModuleOverview({ bundle, onOpenLesson, initialConcept = '', initialSection = '', searchNavigation = 0 }: {
  bundle: LearningPagesPackage;
  onOpenLesson: (moduleId: string, lessonId: string) => void;
  initialConcept?: string;
  initialSection?: string;
  searchNavigation?: number;
}) {
  const background = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (initialSection !== 'overview') return;
    if (background.current) background.current.open = true;
    const frame = requestAnimationFrame(() => goToSection('learning-page-overview-title'));
    return () => cancelAnimationFrame(frame);
  }, [bundle.module_id, initialSection, searchNavigation]);
  const unitLabel = unitLabelOf(bundle);
  const singleSession = unitLabel === 'Session' && bundle.overview.units.length === 1;
  const overview = <section className="card learning-page-overview" aria-labelledby="learning-page-overview-title">
    <span className="eyebrow">{singleSession ? 'SESSION-ÜBERBLICK' : 'MODUL-GESAMTBILD'}</span><h2 id="learning-page-overview-title" tabIndex={-1}>{bundle.overview.title}</h2>
    {bundle.overview.paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
    <SourceLinks sources={bundle.overview.sources} title="Quellen zum Gesamtbild" />
  </section>;
  return <>
    <PlanningPreview key={bundle.module_id} moduleId={bundle.module_id} />
    {bundle.overview.big_picture ? <><ModuleBigPicture key={bundle.module_id} bundle={bundle} onOpenLesson={onOpenLesson} initialConcept={initialConcept} searchNavigation={searchNavigation} />
      <details ref={background} className="card learning-page-background"><summary>Modulüberblick und weitere Quellen</summary>{overview}</details></> : <>{overview}<TutorEntryLink key={bundle.module_id} bundle={bundle} /></>}
    {!!bundle.overview.learning_path.length && <section className="learning-page-path" aria-labelledby="learning-page-path-title">
      <h2 id="learning-page-path-title">Dein Weg durch {singleSession ? 'die Session' : 'das Modul'}</h2>
      <ol>{bundle.overview.learning_path.map((step, index) => <li key={index}>{step}</li>)}</ol>
    </section>}
    {!!bundle.overview.units.length && <section className={`learning-page-units${bundle.overview.units.length === 1 ? ' single-unit' : ''}`} aria-label="Kurseinheiten und Lernseiten">
      {bundle.overview.units.map(unit => {
        const lessons = bundle.lessons.filter(lesson => lesson.unit === unit.unit);
        return <section className="card learning-page-unit" key={unit.unit} aria-labelledby={`learning-page-unit-${unit.unit}`}>
          <div className="learning-page-unit-heading"><Badge tone="teal">{unitLabel} {unit.unit}</Badge><span>{lessons.length ? `${lessons.length} ${lessons.length === 1 ? 'Lernseite' : 'Lernseiten'}` : 'Noch in Vorbereitung'}</span></div>
          <h3 id={`learning-page-unit-${unit.unit}`}>{unit.title}</h3><p>{unit.description}</p>
          {!!unit.topics.length && <ul className="learning-page-topics">{unit.topics.map((topic, index) => <li key={index}>{topic}</li>)}</ul>}
          {lessons.length ? <ol className="learning-page-lesson-list">{lessons.map(lesson => <li key={lesson.id}>
            <button onClick={() => onOpenLesson(bundle.module_id, lesson.id)}><span><strong>{lesson.title}</strong><small>{lesson.summary}</small></span><Icon name="arrow" size={19} /></button>
          </li>)}</ol> : <p className="learning-page-pending">Die Lernseiten für diese {unitLabel === 'Session' ? 'Session' : 'Kurseinheit'} werden noch erarbeitet.</p>}
        </section>;
      })}
    </section>}
  </>;
}

function LessonReader({ bundle, lesson, onOpenLesson, onOpenModule, onOpenTraining, initialSection = '', searchNavigation = 0 }: {
  bundle: LearningPagesPackage;
  lesson: LearningLesson;
  onOpenLesson: LearningPagesProps['onOpenLesson'];
  onOpenModule: LearningPagesProps['onOpenModule'];
  onOpenTraining: LearningPagesProps['onOpenTraining'];
  initialSection?: string;
  searchNavigation?: number;
}) {
  useEffect(() => {
    if (!initialSection || !(initialSection === 'goals' || lesson.sections.some(section => section.id === initialSection))) return;
    const frame = requestAnimationFrame(() => goToSection(sectionId(lesson.id, initialSection)));
    return () => cancelAnimationFrame(frame);
  }, [lesson.id, initialSection, searchNavigation]);
  const lessonIndex = bundle.lessons.findIndex(item => item.id === lesson.id);
  const previous = bundle.lessons[lessonIndex - 1];
  const next = bundle.lessons[lessonIndex + 1];
  return <>
    <button className="text-button learning-page-back" onClick={() => onOpenModule(bundle.module_id)}><span aria-hidden="true">←</span> Zur Lernseitenübersicht</button>
    <PageTitle eyebrow={`${unitLabelOf(bundle).toUpperCase()} ${lesson.unit} · ${bundle.module_title}`} title={lesson.title} description={lesson.summary} />
    <TutorEntryLink key={`${bundle.module_id}-${lesson.id}`} bundle={bundle} initialLessonId={lesson.id} initialSectionId={lesson.sections.some(item => item.id === initialSection) ? initialSection : ''} />
    <LessonProgressControl key={initialSection} moduleId={bundle.module_id} lessonId={lesson.id} sections={lesson.sections} initialSection={initialSection} />
    <div className="learning-page-reader-layout">
      <aside className="learning-page-outline"><nav aria-label="Inhalt dieser Lernseite"><h2>Auf dieser Lernseite</h2><ol>
        {!!lesson.learning_goals.length && <li><button onClick={() => goToSection(sectionId(lesson.id, 'goals'))}>Das kannst du anschließend</button></li>}
        {lesson.sections.map(section => <li key={section.id}><button onClick={() => goToSection(sectionId(lesson.id, section.id))}>{section.title}</button></li>)}
        <li><button onClick={() => goToSection(sectionId(lesson.id, 'exercises'))}>Üben und überprüfen</button></li>
      </ol></nav><button className="text-button" onClick={() => onOpenModule(bundle.module_id)}>Alle Lernseiten <Icon name="book" size={16} /></button></aside>
      <article className="learning-page-reader" aria-label={lesson.title}>
        {!!lesson.learning_goals.length && <section className="learning-page-goals" aria-labelledby={sectionId(lesson.id, 'goals')}>
          <h2 id={sectionId(lesson.id, 'goals')} tabIndex={-1}>Das kannst du anschließend</h2>
          <ul className="learning-page-list">{lesson.learning_goals.map((goal, index) => <li key={index}>{goal}</li>)}</ul>
        </section>}
        {lesson.sections.map(section => <LessonSection key={section.id} section={section} lessonId={lesson.id} moduleId={bundle.module_id} selected={section.id === initialSection} />)}
      </article>
    </div>
    <LessonExercises key={`${bundle.module_id}-${lesson.id}`} lesson={lesson} moduleId={bundle.module_id} unitLabel={unitLabelOf(bundle)} onOpenTraining={onOpenTraining} />
    <nav className="learning-page-neighbors" aria-label="Weitere Lernseiten">
          {previous ? <button onClick={() => onOpenLesson(bundle.module_id, previous.id)}><small>← Vorherige Lernseite</small><strong>{previous.title}</strong></button> : <span />}
          {next ? <button onClick={() => onOpenLesson(bundle.module_id, next.id)}><small>Nächste Lernseite →</small><strong>{next.title}</strong></button> : <button onClick={() => onOpenModule(bundle.module_id)}><small>Zur Übersicht →</small><strong>Alle Lernseiten</strong></button>}
    </nav>
  </>;
}

export function LearningPagesPage({ modules, initialModule, initialLesson = '', initialSection = '', initialConcept = '', initialTab = 'lessons', initialAssignment = '', searchNavigation = 0, onOpenLesson, onOpenModule, onOpenTraining, onOpenTab }: LearningPagesProps) {
  const summaries = useLoad(() => api<LearningPagesSummary[]>('/learning-pages'), []);
  const moduleId = initialModule || summaries.data?.[0]?.module_id || '';
  const knownSummary = summaries.data?.find(summary => summary.module_id === moduleId);
  const unavailable = !!summaries.data && !summaries.error && !knownSummary;
  const content = useLoad(() => moduleId && !unavailable
    ? api<LearningPagesPackage>(`/learning-pages/${encodeURIComponent(moduleId)}`)
    : Promise.resolve<LearningPagesPackage | null>(null), [moduleId, unavailable]);
  const bundle = content.data;
  const lesson = bundle?.lessons.find(item => item.id === initialLesson);
  const module = modules.find(item => item.id === moduleId);
  const heading = bundle?.module_title || module?.name || 'Lernseiten';
  const hasAssignments = !!(bundle?.has_assignments || module?.has_assignments);
  const assignmentsActive = hasAssignments && initialTab === 'assignments';
  const selection = <div className="learning-page-selector"><Field label="Studienmodul"><select value={moduleId} onChange={event => onOpenModule(event.target.value)}>
    {!moduleId && <option value="">Modul auswählen</option>}
    {moduleId && !knownSummary && <option value={moduleId}>{module?.name || moduleId}</option>}
    {summaries.data?.map(summary => <option key={summary.module_id} value={summary.module_id}>{summary.module_number ? `${summary.module_number} · ` : ''}{summary.module_title}</option>)}
  </select></Field></div>;
  return <div className="learning-pages">
    {initialLesson && !assignmentsActive ? selection : <PageTitle eyebrow="VERSTEHEN UND ÜBEN" title={heading} description={assignmentsActive ? 'Übe die Originalfragen der beiden Einsendearbeiten und lies die Begründung zu jeder Antwort nach.' : 'Lerne die Zusammenhänge des Moduls und prüfe dein Verständnis mit den passenden Aufgaben.'} action={selection} />}
    {hasAssignments && <nav className="learning-page-tabs" aria-label="Bereiche dieser Lernpage">
      {(['lessons', 'assignments'] as const).map(tab => <a key={tab} href={`#pages?module=${encodeURIComponent(moduleId)}${tab === 'assignments' ? '&tab=assignments' : ''}`} aria-current={(assignmentsActive ? 'assignments' : 'lessons') === tab ? 'page' : undefined} onClick={event => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onOpenTab(moduleId, tab); } }}><Icon name={tab === 'assignments' ? 'exam' : 'book'} size={17} />{tab === 'assignments' ? 'Einsendearbeiten' : 'Lernseiten'}</a>)}
    </nav>}
    {summaries.error && <ErrorBox error={`Die Modulübersicht konnte nicht geladen werden: ${summaries.error}`} retry={summaries.reload} />}
    {assignmentsActive ? <Assignments key={moduleId} moduleId={moduleId} initialAssignment={initialAssignment} onOpenAssignment={assignmentId => onOpenTab(moduleId, 'assignments', assignmentId)} /> : summaries.loading && !initialModule ? <Loading /> : unavailable ? <Empty title="Lernseiten noch in Vorbereitung">Für dieses Modul sind noch keine Lernseiten veröffentlicht. Verfügbare Module kannst du oben auswählen.</Empty> :
      content.loading ? <Loading /> : content.error ? <ErrorBox error={content.error} retry={content.reload} /> : !bundle ?
        <Empty title="Noch keine Lernseiten veröffentlicht">Sobald ein Lernmodul fertig ist, findest du hier sein Gesamtbild, die Lernseiten und passende Übungen.</Empty> :
        initialLesson && !lesson ? <Empty title="Diese Lernseite ist nicht verfügbar" action={<Button className="secondary" onClick={() => onOpenModule(bundle.module_id)}>Modul-Gesamtbild öffnen</Button>}>Die angefragte Lernseite wurde nicht gefunden. In der Modulübersicht siehst du die veröffentlichten Inhalte.</Empty> :
          lesson ? <LessonReader key={`${bundle.module_id}-${lesson.id}`} bundle={bundle} lesson={lesson} onOpenLesson={onOpenLesson} onOpenModule={onOpenModule} onOpenTraining={onOpenTraining} initialSection={initialSection} searchNavigation={searchNavigation} /> :
            <ModuleOverview bundle={bundle} onOpenLesson={onOpenLesson} initialConcept={initialConcept} initialSection={initialSection} searchNavigation={searchNavigation} />}
  </div>;
}
