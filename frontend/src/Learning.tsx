import { useEffect, useMemo, useRef, useState } from 'react';
import { api, errorText, formatDate, query } from './api';
import { Badge, Button, Empty, ErrorBox, Field, Icon, Loading, PageTitle, Progress, TYPES, TypeSelect, useLoad } from './components';
import { Answer, Attempt, Module, Question, SourceImage } from './types';
import { SourceDocumentLink, SourceLinks } from './SourceLinks';
import { ModelAnswerBody } from './ModelAnswerBody';
import { unitLabel as unitLabelOf } from './unitLabel';
import { type PageContext, usePageDetail } from './pageContext';
import './training-focus.css';
import './practice.css';

export const openTypes=['free_text','case_analysis','exam_question'];
const shuffle=<T,>(items:T[])=>{const result=[...items];for(let index=result.length-1;index>0;index--){const other=Math.floor(Math.random()*(index+1));[result[index],result[other]]=[result[other],result[index]];}return result;};
export function blankAnswer(question:Question):Answer {return question.type==='matching'?{}:['single_choice','multiple_choice','cloze'].includes(question.type)?[]:'';}
export function answered(question:Question,answer:Answer){if(question.type==='flashcard')return true;if(question.type==='matching')return Object.values(answer||{}).filter(Boolean).length===(question.terms||question.pairs?.map(pair=>pair.term)||[]).length;if(question.type==='cloze')return Array.isArray(answer)&&answer.length>0&&answer.every(value=>String(value).trim());return Array.isArray(answer)?answer.length>0:typeof answer==='string'&&answer.trim().length>0;}

export function TaskContext({question,exam=false}:{question:Question;exam?:boolean}) {
 if(!question.question_context)return null;
 return <aside className="task-context" aria-label="Kontext zur Aufgabe"><strong><Icon name="book" size={16}/>Kontext zur Aufgabe</strong><p className="preserve-lines">{question.question_context}</p>{question.question_context_source&&!exam&&<small className="task-context-source"><SourceDocumentLink path={question.question_context_source.path} page={question.question_context_source.source_page}>Kontext nachlesen{question.question_context_source.source_page?` · PDF-Seite ${question.question_context_source.source_page}`:''}</SourceDocumentLink></small>}</aside>;
}

export function SourceImages({images,compact=false}:{images?:SourceImage[];compact?:boolean}) {
 if(!images?.length)return null;
 return <div className={`source-images ${compact?'compact':''}`}>{images.map((image,index)=>{
  const url=`/api/assets/${image.path.split('/').map(encodeURIComponent).join('/')}`;
  const caption=image.caption||`Abbildung aus der Originalquelle${image.source_page?` · Seite ${image.source_page}`:''}`;
  return <figure className="source-image" key={`${image.path}-${index}`}><a href={url} target="_blank" rel="noreferrer" aria-label={`${caption} – in voller Größe öffnen`}><img src={url} alt={caption} loading="lazy"/></a><figcaption><span>{caption}{image.source_page?` · Quelle: Seite ${image.source_page}`:''}</span><a href={url} target="_blank" rel="noreferrer">Abbildung öffnen <Icon name="search" size={13}/></a></figcaption></figure>;
 })}</div>;
}

export function QuestionInput({question,answer,onChange,disabled=false,exam=false}:{question:Question;answer:Answer;onChange:(value:Answer)=>void;disabled?:boolean;exam?:boolean}){
 const choices=useMemo(()=>shuffle((question.options||[]).map((value,index)=>({value,index}))),[question.id]);
 const definitions=useMemo(()=>shuffle(question.definitions||question.pairs?.map(pair=>pair.definition)||[]),[question.id]);
 const [revealed,setRevealed]=useState(false);const [dragging,setDragging]=useState('');
 if(question.type==='single_choice'||question.type==='multiple_choice'){const selected=Array.isArray(answer)?answer as number[]:[];return <><p className="input-instruction">{question.type==='multiple_choice'?'Mehrere Antworten können richtig sein. Wähle alle passenden Antworten.':'Wähle genau eine Antwort.'}</p><div className="answer-options" role="group" aria-label="Antwortmöglichkeiten">{choices.map(({value,index},position)=><label className={`answer-option ${selected.includes(index)?'selected':''} ${disabled?'disabled':''}`} key={index}><input type={question.type==='single_choice'?'radio':'checkbox'} name={`question-${question.id}`} checked={selected.includes(index)} disabled={disabled} onChange={()=>onChange(question.type==='single_choice'?[index]:selected.includes(index)?selected.filter(item=>item!==index):[...selected,index])}/><span className="option-letter">{String.fromCharCode(65+position)}</span><span>{value}</span></label>)}</div></>;}
 if(question.type==='matching'){const mapping=typeof answer==='object'&&!Array.isArray(answer)?answer as Record<string,string>:{};const terms=question.terms||question.pairs?.map(pair=>pair.term)||[];return <><p className="input-instruction">Ziehe die passende Definition zum Begriff. Du kannst auch das Auswahlfeld verwenden.</p><div className="matching-bank">{definitions.map((definition,index)=><div className={`drag-item ${dragging===definition?'dragging':''}`} key={`${definition}-${index}`} draggable={!disabled} onDragStart={event=>{event.dataTransfer.setData('text/plain',definition);setDragging(definition);}} onDragEnd={()=>setDragging('')}><span aria-hidden="true">⠿</span>{definition}</div>)}</div><div className="matching-rows">{terms.map(term=><div key={term} className={`matching-row ${mapping[term]?'assigned':''}`} onDragOver={event=>{if(!disabled)event.preventDefault();}} onDrop={event=>{event.preventDefault();if(disabled)return;const value=event.dataTransfer.getData('text/plain');if(definitions.includes(value))onChange({...mapping,[term]:value});setDragging('');}}><strong>{term}</strong><Icon name="arrow" size={17}/><select aria-label={`Definition für ${term}`} disabled={disabled} value={mapping[term]||''} onChange={event=>onChange({...mapping,[term]:event.target.value})}><option value="">Definition zuordnen …</option>{definitions.map((definition,index)=><option key={index} value={definition}>{definition}</option>)}</select></div>)}</div></>;}
 if(question.type==='cloze'){const text=question.text||question.question;const parts=text.split(/_{3,}/g);const values=Array.isArray(answer)?answer as string[]:[];return <><p className="input-instruction">Ergänze die fehlenden Begriffe. Großschreibung und hinterlegte Synonyme werden berücksichtigt.</p><div className="cloze-text">{parts.map((part,index)=><span key={index}>{part}{index<parts.length-1&&<input aria-label={`Lücke ${index+1}`} className="cloze-input" autoComplete="off" value={values[index]||''} disabled={disabled} onChange={event=>{const next=Array.from({length:parts.length-1},(_,i)=>values[i]||'');next[index]=event.target.value;onChange(next);}}/>}</span>)}</div></>;}
 if(question.type==='flashcard'&&!exam)return <div className={`flashcard ${revealed?'revealed':''}`}><span className="eyebrow">{revealed?'MUSTERLÖSUNG':'DENKE ZUERST AN DEINE ANTWORT'}</span>{revealed?<><ModelAnswerBody question={question}/><SourceImages images={question.original_solution_images}/></>:<p>Nimm dir einen Moment. Formuliere die Antwort für dich, bevor du die Karte umdrehst.</p>}<Button className="secondary" disabled={disabled} onClick={()=>{setRevealed(value=>!value);onChange(revealed?'':'revealed');}}>{revealed?'Frage anzeigen':'Lösung aufdecken'} <Icon name="refresh" size={16}/></Button></div>;
 return <><p className="input-instruction">{question.type==='case_analysis'?'Begründe deine Entscheidung und gehe auf die wichtigsten Kriterien ein.':question.type==='exam_question'?'Beantworte die Originalaufgabe in eigenen Worten.':'Formuliere deine Antwort in eigenen Worten.'}</p><textarea className="open-answer" aria-label="Deine Antwort" rows={exam?8:5} placeholder="Deine Gedanken und deine Antwort …" value={typeof answer==='string'?answer:''} disabled={disabled} onChange={event=>onChange(event.target.value)}/><span className="answer-word-count">{typeof answer==='string'&&answer.trim()?answer.trim().split(/\s+/).length:0} Wörter</span></>;
}
export function SourceDetails({question,reveal=true}:{question:Question;reveal?:boolean}) {
 const derived=question.source_kind==='course_material';
 return <details className="source-details"><summary><Icon name="file" size={16}/>{derived?'Quellen & Herleitung':'Quelle & ursprüngliche Aufgabe'}</summary><div className="source-content">
  <p><strong>{derived?'Grundlage der Lernfrage:':'Quelle der Originalaufgabe:'}</strong> {question.source}{question.source_page?` · PDF-Seite ${question.source_page}`:''}</p>
  <SourceDocumentLink path={question.source} page={question.source_page}>{derived?(question.source.toLowerCase().endsWith('.mp4')?'Vorlesung öffnen':'Lehrbrief öffnen'):'Originalquelle öffnen'}</SourceDocumentLink>
  <SourceLinks sources={question.theory_sources} title="Belege zur Erklärung"/>
  <p className="space-top"><strong>Fragen-ID:</strong> {question.id} · {question.generated_by}</p>
  {question.question_context_source&&<><p><strong>Quelle der Ausgangssituation:</strong> {question.question_context_source.path} · PDF-Seite {question.question_context_source.source_page}</p><SourceDocumentLink path={question.question_context_source.path} page={question.question_context_source.source_page}>Ausgangssituation nachlesen</SourceDocumentLink></>}
  {question.question_revision_note&&<p><strong>Aufbereitete Aufgabenfassung:</strong> {question.question_revision_note}</p>}
  <h4>{derived?'Herkunft der Lernfrage':'Originalfrage'}</h4><p className="preserve-lines">{question.original_question}</p><SourceImages images={question.original_question_images} compact/>
  {reveal&&<><h4>{derived?'Herleitung der Musterantwort':'Originale Musterlösung'}</h4><p className="preserve-lines">{question.original_solution}</p><SourceImages images={question.original_solution_images} compact/></>}
  {reveal&&question.correction_note&&<div className="alert warning"><strong>Korrekturhinweis</strong><p>{question.correction_note}</p></div>}
 </div></details>;
}
export function RatingButtons({onRate,disabled=false,labels=['Nicht gewusst','Schwer','Gut','Einfach']}:{onRate:(value:number)=>void;disabled?:boolean;labels?:string[]}){return <div className="rating-buttons">{[0,3,4,5].map((value,index)=><button className={`rating rating-${index}`} key={value} onClick={()=>onRate(value)} disabled={disabled}><span>{index===0?'↺':index===1?'◔':index===2?'✓':'✦'}</span><strong>{labels[index]}</strong></button>)}</div>;}
export function ModelAnswer({question}:{question:Question}) {
 return <div className="model-answer-content"><h3>Musterantwort</h3><ModelAnswerBody question={question}/><SourceImages images={question.original_solution_images}/></div>;
}
function SolutionDetails({question,answer,matched=[],missing=[]}:{question:Question;answer?:Answer;matched?:string[];missing?:string[]}) {
 return <div className="solution-details-content">
  {question.type==='matching'&&question.pairs&&<div className="solution-pairs">{question.pairs.map(pair=><p key={pair.term}><strong>{pair.term}</strong> → {pair.definition}</p>)}</div>}
  {['single_choice','multiple_choice'].includes(question.type)&&<div className="option-feedback-list" aria-label="Alle Antwortmöglichkeiten mit Korrektur"><h4>Alle Antwortmöglichkeiten im Vergleich</h4>{question.options?.map((option,index)=>{
   const correct=!!question.correct_answers?.includes(index),selected=Array.isArray(answer)&&answer.some(value=>value===index);
   return <article className={`option-feedback ${correct?'is-correct':'is-incorrect'}`} key={index}><div className="option-feedback-heading"><Icon name={correct?'check':'close'} size={17}/><strong>{option}</strong></div><div className="option-feedback-labels"><Badge tone={correct?'green':'red'}>{correct?'Richtige Antwort':'Keine richtige Antwort'}</Badge>{selected&&<Badge tone="teal">Deine Auswahl</Badge>}</div>{question.option_explanations?.[index]?<p>{question.option_explanations[index]}</p>:!correct&&<p>Zum Vergleich: {question.model_answer}</p>}</article>;
  })}</div>}
  {question.type==='cloze'&&<p><strong>Lücken:</strong> {question.answers?.join(' · ')}</p>}
  {question.explanation&&<><h4>Warum ist das so?</h4><p className="preserve-lines">{question.explanation}</p></>}
  {question.learning_context&&<section className="learning-context" aria-label="Zusammenhang verstehen"><h4>{question.learning_context.title}</h4>{question.learning_context.paragraphs?.map((paragraph,index)=><p key={index}>{paragraph}</p>)}{question.learning_context.table&&<div className="feedback-table-wrap"><table><thead><tr>{question.learning_context.table.headers.map((header,index)=><th key={index} scope="col">{header}</th>)}</tr></thead><tbody>{question.learning_context.table.rows.map((row,index)=><tr key={index}>{row.map((cell,column)=><td key={column}>{cell}</td>)}</tr>)}</tbody></table></div>}<SourceLinks sources={question.learning_context.sources} title="Diesen Zusammenhang nachlesen"/>{question.learning_context.lesson_id&&<a className="button secondary" href={`#pages${query({module:question.module_id,lesson:question.learning_context.lesson_id,section:question.learning_context.section_id})}`}>Zum vollständigen Lernabschnitt <Icon name="book" size={16}/></a>}</section>}
  <SourceLinks sources={question.theory_sources} title="Die Erklärung nachlesen"/>
  {!!question.checklist?.length&&<><h4>Wichtige Antwortbestandteile</h4><div className="checklist">{question.checklist.map((item,index)=><label key={index}><input type="checkbox"/>{item}</label>)}</div></>}
  {matched.length+missing.length>0&&<div className="keyword-results"><h4>Schlagworthinweise</h4><p className="muted">Worttreffer sind Hinweise. Prüfe Bedeutung und Begründung deiner Antwort selbst.</p>{matched.map(word=><Badge tone="green" key={word}>✓ {word}</Badge>)}{missing.map(word=><Badge tone="yellow" key={word}>Nicht erkannt: {word}</Badge>)}</div>}
  {question.correction_note&&<div className="alert warning"><strong>Korrekturhinweis zur Originalquelle</strong><p>{question.correction_note}</p></div>}
 </div>;
}
export function Solution({question,answer,matched=[],missing=[]}:{question:Question;answer?:Answer;matched?:string[];missing?:string[]}) {
 return <div className="solution"><ModelAnswer question={question}/><SolutionDetails question={question} answer={answer} matched={matched} missing={missing}/></div>;
}

export function LearningPage({modules,initialModule,initialUnit='',due=false}:{modules:Module[];initialModule:string;initialUnit?:string;due?:boolean}) {
 const [moduleId,setModuleId]=useState(initialModule);const [unit,setUnit]=useState(initialUnit);const [type,setType]=useState('');const [difficulty,setDifficulty]=useState('');
 useEffect(()=>{
  const route=`#${due?'review':'learn'}${query({module:moduleId,unit})}`;
  if(location.hash!==route)history.replaceState(null,'',route);
 },[moduleId,unit,due]);
 const {data,error,loading,reload}=useLoad(()=>api<Question[]>(`/questions${query({module_id:moduleId,unit,type,difficulty,due:due?'true':undefined})}`),[moduleId,unit,type,difficulty,due]);
 const [index,setIndex]=useState(0);const [finished,setFinished]=useState(false);const [done,setDone]=useState(0);
 const selectedModule=modules.find(module=>module.id===moduleId);
 const unitLabel=unitLabelOf(selectedModule);
 const selectedUnit=selectedModule?.unit_summaries?.find(item=>item.unit===Number(unit));
 const availableUnit=selectedModule?.unit_summaries?.find(item=>item.question_count>0);
 const unpreparedUnit=!due&&!!unit&&selectedUnit?.question_count===0;
 const unpreparedModule=!due&&!!selectedModule&&selectedModule.question_count===0;
 const filtersChanged=(action:()=>void)=>{action();setIndex(0);setDone(0);setFinished(false);};
 const clearAdditionalFilters=()=>filtersChanged(()=>{setType('');setDifficulty('');});
 const openAvailableUnit=()=>{
  const targetUnit=availableUnit!.unit;
  filtersChanged(()=>{setUnit(String(targetUnit));setType('');setDifficulty('');});
  location.hash=`learn${query({module:moduleId,unit:targetUnit})}`;
 };
 const question=data?.[index];
 const units=selectedModule?.units||Array.from(new Set((data||[]).map(question=>question.unit))).sort((a,b)=>a-b);
 const emptyTitle=due?'Aktuell keine Wiederholungen fällig':unpreparedUnit?`${unitLabel} ${unit} ist noch nicht aufbereitet`:unpreparedModule?'Dieses Modul hat noch keine Lernfragen':'Keine Fragen für diese Filter';
 const emptyMessage=due?'Deine nächsten Termine entstehen beim Lernen. Du kannst jederzeit im Lerntraining weiterüben.':unpreparedUnit||unpreparedModule?
  (availableUnit?`Für diese Auswahl wurden noch keine Lernfragen erstellt. In ${unitLabel} ${availableUnit.unit} sind ${availableUnit.question_count} Fragen verfügbar.`:'Die Lernfragen für dieses Modul werden noch aufbereitet.'):
  'Die ausgewählte Lernmethode oder Schwierigkeit passt zu keiner verfügbaren Frage. Setze diese Filter zurück, um die Fragen dieser Auswahl zu sehen.';
 const emptyAction=!due&&(unpreparedUnit||unpreparedModule)&&availableUnit?<Button onClick={openAvailableUnit}>{unitLabel} {availableUnit.unit} mit {availableUnit.question_count} Fragen öffnen <Icon name="arrow" size={16}/></Button>:!due&&!unpreparedUnit&&!unpreparedModule&&(type||difficulty)?<Button className="secondary" onClick={clearAdditionalFilters}>Zusätzliche Filter zurücksetzen</Button>:undefined;
 return <div className="learning-training">
  <PageTitle eyebrow={due?'WISSEN FESTIGEN':'DEIN LERNTRAINING'} title={due?'Heute wiederholen. Morgen sicherer.':'Verstehen. Anwenden. Behalten.'} description={due?'Fällige Fragen aus allen Modulen. Deine Antworten bestimmen den nächsten Wiederholungstermin.':'Wähle deinen Fokus und trainiere mit Aufgaben aus deinen Studienunterlagen.'}/>
  <div className="filter-bar learning-filters">
   <Field label="Studienmodul"><select value={moduleId} onChange={event=>filtersChanged(()=>{setModuleId(event.target.value);setUnit('');})}><option value="">Alle Module</option>{modules.map(module=><option value={module.id} key={module.id}>{module.name}</option>)}</select></Field>
   <Field label={unitLabel==='Session'?'Session':'Kurseinheit'}><select value={unit} onChange={event=>filtersChanged(()=>setUnit(event.target.value))}><option value="">Alle {unitLabel==='Session'?'Sessions':'Einheiten'}</option>{units.map(value=>{const count=selectedModule?.unit_summaries?.find(item=>item.unit===value)?.question_count;return <option key={value} value={value}>{unitLabel} {value}{count===undefined?'':count===0?' · noch nicht aufbereitet':` · ${count} Fragen`}</option>;})}</select></Field>
   <Field label="Lernmethode"><TypeSelect value={type} onChange={value=>filtersChanged(()=>setType(value))}/></Field>
   <Field label="Schwierigkeit"><select value={difficulty} onChange={event=>filtersChanged(()=>setDifficulty(event.target.value))}><option value="">Alle Stufen</option><option value="1">Grundlagen</option><option value="2">Anwendung</option><option value="3">Vertiefung</option></select></Field>
  </div>
  {loading?<Loading/>:error?<ErrorBox error={error} retry={reload}/>:!data?.length?<Empty icon={due?'repeat':'learn'} title={emptyTitle} action={emptyAction}>{emptyMessage}</Empty>:finished?
   <section className="card session-complete"><span className="completion-icon"><Icon name="check" size={34}/></span><h2>Ein guter Schritt nach vorn.</h2><p>Du hast {done} Fragen in dieser Runde bearbeitet. Deine Ergebnisse und Wiederholungen sind gespeichert.</p><Button onClick={()=>{setIndex(0);setDone(0);setFinished(false);reload();}}>Neue Runde starten <Icon name="repeat" size={18}/></Button></section>:
   question&&<><div className="session-progress"><span>Frage {index+1} von {data.length}</span><span>{done} bearbeitet</span><Progress value={index/data.length*100}/></div><TrainingQuestion key={question.id} question={question} unitLabel={unitLabelOf(modules.find(module=>module.id===question.module_id))} onNext={completed=>{if(completed)setDone(value=>value+1);if(index+1>=data.length)setFinished(true);else setIndex(value=>value+1);}}/><div className="training-note"><Icon name="repeat" size={16}/> Deine Wiederholungen werden mit SM-2 geplant. Sichere Antworten erhalten mehr Abstand.</div></>}
 </div>;
}

const clip=(value:string,limit:number)=>value.length>limit?`${value.slice(0,limit)} …`:value;
function modelAnswerText(question:Question){
 if(!question.model_answer_sections?.length)return question.model_answer||'';
 return question.model_answer_sections.map(section=>[section.title,...(section.paragraphs||[]),...(section.entries||[]).map(entry=>`${entry.term}${entry.description?`: ${entry.description}`:''}`),...(section.items||[]).map(item=>`- ${item}`)].filter(Boolean).join('\n')).join('\n');
}
function ownAnswerText(question:Question,answer:Answer){
 if(question.type==='single_choice'||question.type==='multiple_choice')return Array.isArray(answer)?(answer as number[]).map(index=>question.options?.[index]).filter(Boolean).join(' | '):'';
 if(question.type==='matching'){const mapping=answer&&typeof answer==='object'&&!Array.isArray(answer)?answer as Record<string,string>:{};return Object.entries(mapping).filter(([,value])=>value).map(([term,value])=>`${term} → ${value}`).join(' | ');}
 if(question.type==='cloze')return Array.isArray(answer)?(answer as string[]).join(' | '):'';
 if(question.type==='flashcard')return '';
 return typeof answer==='string'?answer:'';
}
/** What the "KI fragen" window may know about a training question; the model answer only once it is shown. */
export function trainingContext(question:Question,answer:Answer,solved:Question|null,unitLabel:string):PageContext {
 const lines=[`Aufgabe (${TYPES[question.type]||question.type}, ${unitLabel} ${question.unit}, Thema: ${question.topic}): ${question.question}`];
 if(question.question_context)lines.push(`Kontext zur Aufgabe: ${clip(question.question_context,1200)}`);
 if(question.options?.length)lines.push(`Antwortmöglichkeiten: ${question.options.join(' | ')}`);
 const own=ownAnswerText(question,answer).trim();
 if(question.type!=='flashcard')lines.push(`Eigene Antwort der lernenden Person: ${own?clip(own,1500):'(noch keine)'}`);
 if(solved){
  lines.push(`Musterantwort: ${clip(modelAnswerText(solved),1800)}`);
  if(['single_choice','multiple_choice'].includes(solved.type)&&solved.correct_answers?.length)lines.push(`Richtige Antwortmöglichkeiten: ${solved.correct_answers.map(index=>solved.options?.[index]).filter(Boolean).join(' | ')}`);
  if(solved.explanation)lines.push(`Erklärung: ${clip(solved.explanation,800)}`);
 } else lines.push('Musterantwort: noch verdeckt – nicht verraten, nur Hinweise geben.');
 return {key:`question:${question.id}`,module_id:question.module_id,title:`Frage: ${clip(question.question,100)}`,text:clip(lines.join('\n'),5900)};
}

export function TrainingQuestion({question,onNext,unitLabel='Einheit'}:{question:Question;onNext:(completed:boolean)=>void;unitLabel?:string}) {
 const [answer,setAnswer]=useState<Answer>(blankAnswer(question));const [result,setResult]=useState<Attempt|null>(null);const [saving,setSaving]=useState(false);const [error,setError]=useState('');const [rated,setRated]=useState(false);const [selfRating,setSelfRating]=useState<number|null>(null);
 const card=useRef<HTMLElement>(null);const revealed=!!result;
 usePageDetail(trainingContext(question,answer,result?.question||(question.type==='flashcard'&&answer==='revealed'?question:null),unitLabel));
 useEffect(()=>{if(revealed&&card.current){card.current.scrollIntoView({block:'start',behavior:'instant'});}},[revealed]);
 const submit=async(rating?:number)=>{setSaving(true);setError('');try{const next=await api<Attempt>('/attempts',{question_id:question.id,answer,rating});setResult(next);if(rating!==undefined){setRated(true);setSelfRating(rating);}}catch(error){setError(errorText(error));}finally{setSaving(false);}};
 const rate=async(rating:number)=>{if(!result){await submit(rating);return;}setSaving(true);setError('');try{setResult(await api<Attempt>(`/attempts/${result.id}`,{manual_score:rating===0?0:rating===3?.5:1,rating},'PATCH'));setRated(true);setSelfRating(rating);}catch(error){setError(errorText(error));}finally{setSaving(false);}};
 const isOpen=openTypes.includes(question.type),isFlash=question.type==='flashcard';
 const selfLabels:Record<number,string>={0:'Nicht gewusst',3:'Schwer',4:'Gut',5:'Einfach'};
 const feedbackTone=result?.grading==='keyword_hint'?'hint':result?.grading==='self'?'self':result?.correct?'correct':'incorrect';
 return <section ref={card} className={`card question-card training-question ${result?'answer-revealed':''}`} aria-label="Frage und Antwortvergleich">
  <div className="question-meta"><div><Badge tone="teal">{TYPES[question.type]}</Badge><Badge>{unitLabel} {question.unit}</Badge><Badge>{['','Grundlagen','Anwendung','Vertiefung'][question.difficulty]}</Badge></div><Badge tone={question.verified?'green':'yellow'}>{question.verified?'Geprüft':'Prüfung offen'}</Badge></div>
  <p className="eyebrow question-topic">{question.topic}</p><TaskContext question={question}/><h2 className="question-text">{question.question}</h2><SourceImages images={question.original_question_images}/>
  {(!result||(!isOpen&&!isFlash))&&<QuestionInput question={question} answer={answer} onChange={setAnswer} disabled={saving||!!result}/>}
  {error&&<ErrorBox error={error}/>} 
  {!result&&isFlash&&<div className="self-assessment"><h4>Wie gut hast du die Antwort gewusst?</h4><RatingButtons onRate={rate} disabled={saving||answer!=='revealed'}/></div>}
  {!result&&!isFlash&&<div className="question-actions"><button className="text-button muted" disabled={saving} onClick={()=>onNext(false)}>Überspringen</button><Button disabled={saving||!answered(question,answer)} onClick={()=>submit()}>{saving?'Wird ausgewertet …':isOpen?'Mit Musterantwort vergleichen':'Antwort prüfen'} <Icon name="check" size={17}/></Button></div>}
  {result&&<div className="feedback">
   {isOpen?<>
    <div className="answer-comparison" aria-label="Eigene Antwort und Musterantwort vergleichen">
     <section className="answer-panel own-answer-panel"><h3>Deine Antwort</h3><p className="preserve-lines own-answer-text">{typeof answer==='string'?answer:''}</p></section>
     <section className="answer-panel model-answer-panel"><ModelAnswer question={result.question}/></section>
    </div>
    <details className="solution-explanation"><summary>Erklärung und Antwortkriterien</summary><SolutionDetails question={result.question} answer={answer} matched={result.matched_keywords} missing={result.missing_keywords}/></details>
   </>:<Solution question={result.question} answer={answer} matched={result.matched_keywords} missing={result.missing_keywords}/>}
   <div className={`feedback-banner ${feedbackTone}`} aria-live="polite"><Icon name={result.grading==='keyword_hint'?'search':result.grading==='self'?'check':result.correct?'check':'repeat'} size={18}/><div>
    <strong>{result.grading==='keyword_hint'?'Vergleiche Inhalt und Begründung.':result.grading==='self'?`Selbstbewertung gespeichert${selfRating===null?'':`: ${selfLabels[selfRating]}`}.`:result.correct?'Richtig beantwortet.':'Das kannst du noch einmal üben.'}</strong>
    <p>{result.grading==='keyword_hint'?(question.keywords?.length?'Schlagwörter liefern nur Hinweise. Deine fachliche Selbstbewertung bestimmt die Wiederholung.':'Nutze Musterantwort und Antwortkriterien für deine fachliche Selbstbewertung. Sie bestimmt die Wiederholung.'):result.grading==='self'?`Nächste Wiederholung: ${formatDate(result.next_due)}.`:`Ergebnis: ${Math.round(result.score*100)} % · Nächste Wiederholung: ${formatDate(result.next_due)}.`}</p>
   </div></div>
   {isOpen&&!rated&&<div className="self-assessment"><h4>Wie vollständig und richtig ist deine Antwort?</h4><RatingButtons onRate={rate} disabled={saving}/></div>}
   <div className="question-actions"><span className="muted">{rated?'Selbstbewertung gespeichert':'Antwort gespeichert'}</span><Button onClick={()=>onNext(true)} disabled={saving}>Nächste Frage <Icon name="arrow" size={17}/></Button></div>
  </div>}
  <SourceDetails question={question} reveal={!!result}/>
 </section>;
}
