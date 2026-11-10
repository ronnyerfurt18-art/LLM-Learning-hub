import { ReactNode, useState } from 'react';
import { api, query } from './api';
import { Empty, ErrorBox, Field, Icon, Loading, PageTitle, useLoad } from './components';
import { TutorScope, TutorWorkspace } from './LearningTutor';
import { LearningPagesPackage, LearningPagesSummary, Module } from './types';
import { conceptUnits, unitCaption } from './tutorUnits';
import { SourceLinks } from './SourceLinks';
import { unitLabel as unitLabelOf } from './unitLabel';
import './learning-tutor.css';

type Selection = (moduleId: string, lessonId?: string, sectionId?: string, conceptId?: string) => void;
type Props = {
  modules: Module[];
  moduleId: string;
  lessonId: string;
  sectionId: string;
  conceptId: string;
  onSelect: Selection;
};

function StudySelection({ bundle, lessonId, sectionId, conceptId, onSelect, moduleSelect }: Omit<Props, 'modules' | 'moduleId'> & {
  bundle: LearningPagesPackage;
  moduleSelect: ReactNode;
}) {
  const [filter, setFilter] = useState('');
  const lesson = bundle.lessons.find(item => item.id === lessonId);
  const concept = bundle.overview.big_picture?.nodes.find(item => item.id === conceptId);
  const selectedUnits = lesson ? [lesson.unit] : concept ? conceptUnits(bundle, concept) : [];
  const unitTitles = bundle.overview.units.filter(item => selectedUnits.includes(item.unit));
  const unitLabel = unitLabelOf(bundle, 'Lerneinheit');
  const section = lesson?.sections.find(item => item.id === sectionId);
  const sourceRefs = section ? section.sources : lesson ? lesson.sections.flatMap(item => item.sources) : concept ? concept.sources : bundle.overview.sources;
  const sources = sourceRefs.filter((source, index) => sourceRefs.findIndex(other => JSON.stringify(other) === JSON.stringify(source)) === index);
  const invalid = !!((lessonId && !lesson) || (conceptId && !concept) || (sectionId && !section) || (lessonId && conceptId));
  const topic = lessonId ? `lesson:${lessonId}` : conceptId ? `concept:${conceptId}` : 'overview';
  const words = filter.trim().toLocaleLowerCase('de').split(/\s+/).filter(Boolean);
  const matches = (text: string) => words.every(word => text.toLocaleLowerCase('de').includes(word));
  const conceptLabel = (item: NonNullable<LearningPagesPackage['overview']['big_picture']>['nodes'][number]) => `${unitCaption(bundle, conceptUnits(bundle, item))} · ${item.title}`;
  const unitSearchText = (units: number[]) => bundle.overview.units.filter(item => units.includes(item.unit)).map(item => `${unitLabel} ${item.unit} ${item.title}`).join(' ');
  const lessons = bundle.lessons.filter(item => matches([unitSearchText([item.unit]), item.title, item.summary, ...item.learning_goals, ...item.sections.map(part => part.title)].join(' ')));
  const concepts = (bundle.overview.big_picture?.nodes || []).filter(item => matches(`${conceptLabel(item)} ${unitSearchText(conceptUnits(bundle, item))} ${item.summary}`));
  const overviewMatch = !words.length || matches(`Modulüberblick ${bundle.module_title} ${bundle.overview.title}`);
  const filteredCurrent = topic !== 'overview' && !lessons.some(item => item.id === lessonId) && !concepts.some(item => item.id === conceptId);
  const noMatches = !overviewMatch && !lessons.length && !concepts.length;
  const resultCount = lessons.length + concepts.length + Number(overviewMatch);
  const title = section?.title || lesson?.title || concept?.title || 'Modulüberblick';
  const scope: TutorScope = { module_id: bundle.module_id, ...(lessonId ? { lesson_id: lessonId } : {}), ...(sectionId ? { section_id: sectionId } : {}), ...(conceptId ? { concept_id: conceptId } : {}) };
  const readerLink = `#pages${query({ module: bundle.module_id, lesson: lessonId, section: sectionId, concept: conceptId })}`;

  return <div className="tutor-study-layout">
    <section className="card tutor-selection" aria-labelledby="tutor-selection-title">
      <span className="eyebrow">1 · THEMA FESTLEGEN</span><h2 id="tutor-selection-title">Was möchtest du lernen?</h2>
      {moduleSelect}
      <Field label="Themen filtern"><input type="search" value={filter} placeholder="z. B. Metadaten oder Datenqualität" onChange={event => setFilter(event.target.value)} /></Field>
      <Field label="Thema"><select value={topic} onChange={event => {
        const value = event.target.value;
        onSelect(bundle.module_id, value.startsWith('lesson:') ? value.slice(7) : '', '', value.startsWith('concept:') ? value.slice(8) : '');
      }}>
        {(overviewMatch || topic === 'overview') && <option value="overview">Modulüberblick</option>}
        {topic !== 'overview' && !lesson && !concept && <option value={topic}>Auswahl nicht verfügbar</option>}
        {!invalid && filteredCurrent && <option value={topic}>{lesson ? `${unitLabel} ${lesson.unit} · ${lesson.title}` : concept ? conceptLabel(concept) : ''} (aktuelle Auswahl)</option>}
        {!!lessons.length && <optgroup label="Lernseiten">{lessons.map(item => <option key={item.id} value={`lesson:${item.id}`}>{unitLabel} {item.unit} · {item.title}</option>)}</optgroup>}
        {!!concepts.length && <optgroup label="Bausteine im Gesamtbild">{concepts.map(item => <option key={item.id} value={`concept:${item.id}`}>{conceptLabel(item)}</option>)}</optgroup>}
      </select></Field>
      {words.length > 0 && <div className="tutor-filter-result" role="status"><p>{noMatches ? 'Kein passendes Thema gefunden. Deine bisherige Auswahl bleibt bestehen.' : `${resultCount} ${resultCount === 1 ? 'passendes Thema' : 'passende Themen'}. Wähle im Feld „Thema“.`}</p><button className="text-button" onClick={() => setFilter('')}>Filter zurücksetzen</button></div>}
      {lesson && <Field label="Abschnitt"><select value={sectionId} onChange={event => onSelect(bundle.module_id, lesson.id, event.target.value)}>
        <option value="">Ganze Lernseite</option>
        {sectionId && !section && <option value={sectionId}>Abschnitt nicht verfügbar</option>}
        {lesson.sections.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select></Field>}
      <button className="button secondary tutor-jump" onClick={() => {
        const heading = document.getElementById('tutor-chat-title');
        heading?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
        heading?.focus({ preventScroll: true });
      }}>Zum Lernchat <span aria-hidden="true">↓</span></button>
      <p className="tutor-selection-hint">Beim Wechsel von Modul, Thema oder Abschnitt beginnt ein neues Gespräch.</p>
    </section>

    <section className="card tutor-chat-panel" aria-labelledby="tutor-chat-title">
      <span className="eyebrow">2 · DEIN LERNZIEL</span><h2 id="tutor-chat-title" tabIndex={-1}>Dein Lernchat</h2>
      <p className="tutor-chat-intro">Du brauchst noch keine Antwort zu kennen. Wähle einen Einstieg oder beschreibe in eigenen Worten, was du verstehen möchtest.</p>
      {invalid ? <Empty title="Dieses Thema ist nicht verfügbar" action={<button className="button secondary" onClick={() => onSelect(bundle.module_id)}>Thema neu auswählen</button>}>Wähle ein verfügbares Thema, damit der Tutor die richtigen Inhalte erhält.</Empty> : <TutorWorkspace key={query(scope)} scope={scope} moduleTitle={bundle.module_title} />}
    </section>
      {!invalid && <section className="card tutor-focus" aria-labelledby="tutor-focus-title">
        <span className="eyebrow">DEIN AKTUELLER LERNSTOFF</span><h2 id="tutor-focus-title">Thema &amp; Quellen</h2><h3>{title}</h3>
        <p><strong>{bundle.module_title} ({bundle.module_number}){lesson || concept ? ` · ${unitCaption(bundle, selectedUnits)}` : ' · Modulüberblick'}</strong>{unitTitles.map(item => <span key={item.unit}><br />{unitLabel} {item.unit} · {item.title}</span>)}</p>
        <p>{section ? 'Du lernst gezielt diesen Abschnitt.' : lesson?.summary || concept?.summary || 'Ein erster Überblick über die Zusammenhänge. Für einzelne Inhalte wähle eine Lernseite oder einen Baustein.'}</p>
        <SourceLinks sources={sources} title="Daraus lernst du gerade" pdfLabel="Originalheft öffnen" />
        {!sources.length && <p>Für diese Auswahl ist keine Originalquelle hinterlegt.</p>}
        {!!lesson?.learning_goals.length && <details><summary>Lernziele dieser Lernseite</summary><ul>{lesson.learning_goals.map(goal => <li key={goal}>{goal}</li>)}</ul></details>}
        <a className="text-button" href={readerLink}><Icon name="book" size={15} /> Auf der Lernpage nachlesen</a>
      </section>}
  </div>;
}

export function TutorPage({ modules, moduleId, lessonId, sectionId, conceptId, onSelect }: Props) {
  const summaries = useLoad(() => api<LearningPagesSummary[]>('/learning-pages'), []);
  const available = !!summaries.data?.some(item => item.module_id === moduleId);
  const content = useLoad(() => available ? api<LearningPagesPackage>(`/learning-pages/${encodeURIComponent(moduleId)}`) : Promise.resolve<LearningPagesPackage | null>(null), [moduleId, available]);
  const moduleOptions = modules.map(module => ({ id: module.id, label: `${module.number} · ${module.name}` }));
  for (const summary of summaries.data || []) {
    if (!moduleOptions.some(item => item.id === summary.module_id)) moduleOptions.push({ id: summary.module_id, label: `${summary.module_number} · ${summary.module_title}` });
  }
  const selection = <Field label="Studienmodul"><select value={moduleId} onChange={event => onSelect(event.target.value)}>
    <option value="">Modul auswählen</option>
    {moduleId && !moduleOptions.some(item => item.id === moduleId) && <option value={moduleId}>{moduleId}</option>}
    {moduleOptions.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
  </select></Field>;
  return <div className="tutor-page">
    <PageTitle eyebrow="DEIN PERSÖNLICHER LERNBEGLEITER" title="Mit KI lernen" description="Verstehe die Grundlagen, arbeite Beispiele durch und prüfe dein Verständnis – in deinem Tempo." />
    {summaries.loading ? <Loading /> : summaries.error ? <ErrorBox error={summaries.error} retry={summaries.reload} /> : available && !content.loading && !content.error && content.data?.module_id === moduleId ?
      <StudySelection key={moduleId} bundle={content.data} lessonId={lessonId} sectionId={sectionId} conceptId={conceptId} onSelect={onSelect} moduleSelect={selection} /> :
      <section className="card tutor-module-start">{selection}{!moduleId ? <Empty title="Womit möchtest du anfangen?">Wähle zuerst ein Studienmodul. Danach kannst du ein Thema eingrenzen und deinen Lernauftrag formulieren.</Empty> : !available ? <Empty title="Lerninhalte noch in Vorbereitung">Für dieses Modul liegen noch keine aufbereiteten Lernseiten vor. Wähle ein anderes Modul.</Empty> : content.error ? <ErrorBox error={content.error} retry={content.reload} /> : <Loading />}</section>}
  </div>;
}
