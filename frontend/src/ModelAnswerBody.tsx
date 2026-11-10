import { Question } from './types';
import './model-answer.css';

/** Shared answer body for feedback, exam reviews and revealed flashcards. */
export function ModelAnswerBody({question}:{question:Question}) {
 if(!question.model_answer_sections?.length)return <p className="preserve-lines model-answer-text">{question.model_answer}</p>;
 return <div className="model-answer-structured">{question.model_answer_sections.map((section,index)=><section className="model-answer-section" key={index}>
  {section.title&&<h4>{section.title}</h4>}
  {section.paragraphs?.map((paragraph,paragraphIndex)=><p key={paragraphIndex}>{paragraph}</p>)}
  {!!section.entries?.length&&<dl className="model-answer-entries">{section.entries.map((entry,entryIndex)=><div className="model-answer-entry" key={entryIndex}><dt><strong>{entry.term}</strong></dt>{entry.description&&<dd>{entry.description}</dd>}</div>)}</dl>}
  {!!section.items?.length&&<ul className="model-answer-items">{section.items.map((item,itemIndex)=><li key={itemIndex}>{item}</li>)}</ul>}
 </section>)}</div>;
}
