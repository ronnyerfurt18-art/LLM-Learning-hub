import { useEffect, useId, useRef, useState } from 'react';
import { Icon } from './components';
import { SourceLinks } from './SourceLinks';
import { TutorEntryLink } from './LearningTutor';
import { LearningPagesPackage } from './types';
import { unitLabel, unitLabelPlural } from './unitLabel';
import './module-big-picture.css';

type Box = { x: number; y: number; width: number; height: number };

function connectionPath(from: Box, to: Box) {
  const a = { x: from.x + from.width / 2, y: from.y + from.height / 2 };
  const b = { x: to.x + to.width / 2, y: to.y + to.height / 2 };
  const dx = b.x - a.x, dy = b.y - a.y;
  const exit = Math.min(dx ? from.width / 2 / Math.abs(dx) : Infinity, dy ? from.height / 2 / Math.abs(dy) : Infinity);
  const entry = Math.min(dx ? to.width / 2 / Math.abs(dx) : Infinity, dy ? to.height / 2 / Math.abs(dy) : Infinity);
  return `M ${a.x + dx * exit} ${a.y + dy * exit} L ${b.x - dx * entry} ${b.y - dy * entry}`;
}

export function ModuleBigPicture({ bundle, onOpenLesson, initialConcept = '', searchNavigation = 0 }: {
  bundle: LearningPagesPackage;
  onOpenLesson: (moduleId: string, lessonId: string) => void;
  initialConcept?: string;
  searchNavigation?: number;
}) {
  const picture = bundle.overview.big_picture!;
  const [selectedId, setSelectedId] = useState(picture.nodes[0].id);
  const [geometry, setGeometry] = useState<Record<string, Box>>({});
  const map = useRef<HTMLDivElement>(null);
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  const detail = useRef<HTMLDivElement>(null);
  const id = useId().replace(/:/g, '');
  const selected = picture.nodes.find(node => node.id === selectedId) || picture.nodes[0];
  const titles = new Map(picture.nodes.map(node => [node.id, node.title]));
  const lessons = bundle.lessons.filter(lesson => selected.lesson_ids?.includes(lesson.id));
  const taskSources = selected.sources.length > 0 && selected.sources.every(source => source.kind !== 'video' && source.source_kind === 'exam');

  useEffect(() => {
    const element = map.current;
    if (!element) return;
    const measure = () => {
      const base = element.getBoundingClientRect();
      const boxes: Record<string, Box> = {};
      for (const node of picture.nodes) {
        const rect = buttons.current[node.id]?.getBoundingClientRect();
        if (rect) boxes[node.id] = { x: rect.x - base.x, y: rect.y - base.y, width: rect.width, height: rect.height };
      }
      setGeometry(boxes);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    measure();
    return () => observer.disconnect();
  }, [picture]);

  const openDetail = () => {
    detail.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    detail.current?.focus({ preventScroll: true });
  };
  useEffect(() => {
    if (!initialConcept || !picture.nodes.some(node => node.id === initialConcept)) return;
    setSelectedId(initialConcept);
    const frame = requestAnimationFrame(openDetail);
    return () => cancelAnimationFrame(frame);
  }, [initialConcept, picture, searchNavigation]);
  const chooseNode = (nodeId: string) => {
    setSelectedId(nodeId);
    requestAnimationFrame(openDetail);
  };
  const returnToMap = () => {
    map.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    buttons.current[selected.id]?.focus({ preventScroll: true });
  };

  return <section className="card module-big-picture" aria-labelledby={`big-picture-title-${id}`}>
    <header className="big-picture-heading"><span className="eyebrow">DEIN BIG PICTURE</span>
      <h2 id={`big-picture-title-${id}`}>{picture.title}</h2><p>{picture.intro}</p>
    </header>
    <div className="big-picture-question"><span>Die Leitfrage</span><strong>{picture.central_question}</strong></div>
    <p className="big-picture-instruction">Wähle einen Baustein. Darunter findest du die Erklärung und passende Nachlesestellen.</p>
    <div className="big-picture-map" ref={map} role="group" aria-label="Bausteine des Moduls">
      <svg className="big-picture-lines" aria-hidden="true" focusable="false">
        <defs><marker id={`big-picture-arrow-${id}`} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
        {picture.connections.map((connection, index) => geometry[connection.from] && geometry[connection.to] &&
          <path key={index} d={connectionPath(geometry[connection.from], geometry[connection.to])} markerEnd={`url(#big-picture-arrow-${id})`} className={connection.from === selected.id || connection.to === selected.id ? 'is-relevant' : ''} />)}
      </svg>
      {picture.nodes.map((node, index) => <button key={node.id} ref={element => { buttons.current[node.id] = element; }}
        type="button" className={`big-picture-node${node.id === selected.id ? ' is-selected' : ''}`} aria-pressed={node.id === selected.id}
        aria-controls={`big-picture-detail-${id}`} onClick={() => chooseNode(node.id)}>
        <span className="big-picture-node-top"><span className="big-picture-number">{String(index + 1).padStart(2, '0')}</span><Icon name="arrow" size={16} /></span>
        <strong>{node.title}</strong><span className="big-picture-role">{node.role}</span>
      </button>)}
    </div>
    <div className="big-picture-relations" aria-labelledby={`big-picture-connections-${id}`}>
      <h3 id={`big-picture-connections-${id}`}>So hängt es zusammen</h3>
      <ul>{picture.connections.map((connection, index) => <li key={index} className={connection.from === selected.id || connection.to === selected.id ? 'is-relevant' : ''}>
        <button onClick={() => chooseNode(connection.from)}>{titles.get(connection.from)}</button>
        <span className="big-picture-relation-label"><span>{connection.label}</span><Icon name="arrow" size={14} /></span>
        <button onClick={() => chooseNode(connection.to)}>{titles.get(connection.to)}</button>
      </li>)}</ul>
    </div>
    <div className="big-picture-detail-entry"><strong>{selected.title}</strong><button className="text-button" onClick={openDetail}>Erklärung & Nachlesestellen <Icon name="chevron" size={16} /></button></div>
    <div className="big-picture-detail" id={`big-picture-detail-${id}`} ref={detail} tabIndex={-1} aria-labelledby={`big-picture-selected-${id}`}>
      <div className="big-picture-detail-top"><span className="eyebrow">BAUSTEIN VERTIEFEN</span><button className="text-button" onClick={returnToMap}>Zur Themenlandkarte <Icon name="arrow" size={14} /></button></div>
      <h3 id={`big-picture-selected-${id}`}>{selected.title}</h3><p>{selected.summary}</p>
      {selected.scope_note && <p className="big-picture-scope">{selected.scope_note}</p>}
      {!!lessons.length && <nav className="big-picture-lessons" aria-label="Passende Lernseiten"><h4>In deinen Lernseiten weiterlesen</h4>
        <ul>{lessons.map(lesson => <li key={lesson.id}><button onClick={() => onOpenLesson(bundle.module_id, lesson.id)}><span>{lesson.title}</span><Icon name="arrow" size={16} /></button></li>)}</ul>
      </nav>}
      <SourceLinks sources={selected.sources} title={taskSources ? 'Originalaufgaben zum Thema' : 'Nachlesestellen'} />
      <TutorEntryLink key={`${bundle.module_id}-${selected.id}`} bundle={bundle} conceptId={selected.id} />
    </div>
    <p className="big-picture-takeaway"><strong>Der rote Faden</strong>{picture.takeaway}</p>
    {picture.generated_by && <p className="big-picture-origin">Entwurf: {picture.generated_by}.{picture.units?.length ? ` Stand: ${picture.units.length === 1 ? unitLabel(bundle) : unitLabelPlural(bundle)} ${picture.units.join(', ')}.` : ''} Fachlich nicht geprüft.</p>}
  </section>;
}
