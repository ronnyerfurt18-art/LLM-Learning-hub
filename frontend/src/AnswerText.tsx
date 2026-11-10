import { type ReactNode } from 'react';
import { SourceRef } from './types';

/** Shared rendering of model answers (chat and Musterlösung): light Markdown incl. tables,
 * clickable [S1] references – React elements only, no HTML injection. */
export type TutorSource = SourceRef & { id: string };

const citeGroup = /\[(S\d+(?:\s*[,;]\s*S\d+)*)\]/g;

export function citedIds(text: string): string[] {
  const ids: string[] = [];
  for (const match of text.matchAll(citeGroup)) {
    for (const id of match[1].split(/\s*[,;]\s*/)) if (!ids.includes(id)) ids.push(id);
  }
  return ids;
}

/** Inline formatting without HTML injection: **bold** and clickable [S1] references. */
function inline(text: string, sources: TutorSource[], onCite: ((id: string) => void) | undefined, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*|\[(S\d+(?:\s*[,;]\s*S\d+)*)\]/g;
  let last = 0;
  let index = 0;
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0;
    if (at > last) nodes.push(text.slice(last, at));
    const key = `${keyBase}-${index++}`;
    if (match[1] !== undefined) {
      nodes.push(<strong key={key}>{inline(match[1], sources, onCite, key)}</strong>);
    } else {
      match[2].split(/\s*[,;]\s*/).forEach((id, position) => {
        const source = sources.find(item => item.id === id);
        nodes.push(source
          ? <button type="button" key={`${key}-${position}`} className="tutor-cite" disabled={!onCite}
              title={`${source.title}${source.chapter ? ` · ${source.chapter}` : ''} – zum Originalauszug`} onClick={() => onCite?.(id)}>{id}</button>
          : <span key={`${key}-${position}`} className="tutor-cite tutor-cite-unknown" title="Diese Quellen-ID gehört nicht zum Lernkontext.">{id}?</span>);
      });
    }
    last = at + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type LineKind = 'blank' | 'hr' | 'heading' | 'bullet' | 'number' | 'table' | 'text' | 'task';
type AnswerLine = { kind: LineKind; text: string; indented: boolean };

function classify(raw: string, highlightTask: boolean): AnswerLine {
  const indented = /^\s{2,}\S/.test(raw);
  const line = raw.trim();
  if (!line) return { kind: 'blank', text: '', indented };
  const task = highlightTask && /^(?:#{1,6}\s+)?(?:\*\*Deine Aufgabe:\*\*|Deine Aufgabe:)\s+(.+)$/i.exec(line);
  if (task) return { kind: 'task', text: task[1], indented };
  if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(line)) return { kind: 'hr', text: '', indented };
  if (/^\|.*\|$/.test(line)) return { kind: 'table', text: line, indented };
  let match = /^#{1,6}\s+(.*)$/.exec(line);
  if (match) return { kind: 'heading', text: match[1].replace(/\*\*/g, ''), indented };
  match = /^[-*•]\s+(.*)$/.exec(line);
  if (match) return { kind: 'bullet', text: match[1], indented };
  match = /^\d+[.)]\s+(.*)$/.exec(line);
  if (match) return { kind: 'number', text: match[1], indented };
  return { kind: 'text', text: line, indented };
}

/** Light Markdown (headings, lists, rules, bold) rendered as React elements only. */
export function AnswerText({ text, sources, onCite, highlightTask = false }: {
  text: string; sources: TutorSource[]; onCite?: (id: string) => void; highlightTask?: boolean;
}) {
  const lines = text.trimEnd().split('\n').map(line => classify(line, highlightTask));
  const last = lines[lines.length - 1];
  const previous = lines[lines.length - 2];
  // Older replies may finish with a standalone question without the task heading.
  if (highlightTask && last.kind === 'text' && (!previous || previous.kind === 'blank')
      && /\?(?:\*\*)?$/.test(last.text) && !/[.!?]\s/.test(last.text)
      && !lines.some(line => line.kind === 'task')) {
    last.kind = 'task';
  }
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.kind === 'blank') { index += 1; continue; }
    const key = `b${index}`;
    if (line.kind === 'hr') { blocks.push(<hr key={key} />); index += 1; continue; }
    if (line.kind === 'task') {
      blocks.push(<h4 key={key} className="tutor-answer-task">
        <span>Deine Aufgabe</span>{inline(line.text, sources, onCite, key)}
      </h4>);
      index += 1;
      continue;
    }
    if (line.kind === 'heading') { blocks.push(<h4 key={key}>{inline(line.text, sources, onCite, key)}</h4>); index += 1; continue; }
    if (line.kind === 'table') {
      const rows: string[][] = [];
      let header = false;
      while (index < lines.length && lines[index].kind === 'table') {
        const cells = lines[index].text.slice(1, -1).split('|').map(cell => cell.trim());
        if (cells.every(cell => /^:?-{3,}:?$/.test(cell))) header = rows.length === 1;
        else rows.push(cells);
        index += 1;
      }
      const [head, ...body] = header ? rows : [[], ...rows];
      blocks.push(<div className="tutor-table-wrap" key={key}><table className="tutor-table">
        {header && <thead><tr>{head.map((cell, position) => <th key={position}>{inline(cell, sources, onCite, `${key}-h${position}`)}</th>)}</tr></thead>}
        <tbody>{body.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, position) => <td key={position}>{inline(cell, sources, onCite, `${key}-${rowIndex}-${position}`)}</td>)}</tr>)}</tbody>
      </table></div>);
      continue;
    }
    if (line.kind === 'bullet' || line.kind === 'number') {
      const kind = line.kind;
      const items: string[] = [];
      while (index < lines.length) {
        const current = lines[index];
        if (current.kind === kind) items.push(current.text);
        else if (items.length && current.kind === 'text' && current.indented) items[items.length - 1] += ' ' + current.text;
        else break;
        index += 1;
      }
      const children = items.map((item, position) => <li key={position}>{inline(item, sources, onCite, `${key}-${position}`)}</li>);
      blocks.push(kind === 'number' ? <ol key={key}>{children}</ol> : <ul key={key}>{children}</ul>);
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].kind === 'text') { paragraph.push(lines[index].text); index += 1; }
    blocks.push(<p key={key}>{inline(paragraph.join('\n'), sources, onCite, key)}</p>);
  }
  return <div className="tutor-answer">{blocks}</div>;
}

export function sourcePosition(source: TutorSource) {
  if (source.kind === 'video') return `Video ab Sekunde ${source.timestamp_seconds}`;
  const pages = source.pdf_page_end && source.pdf_page_end !== source.pdf_page ? `${source.pdf_page}–${source.pdf_page_end}` : String(source.pdf_page);
  return `PDF-Seite ${pages}${source.printed_page ? ` (gedruckt: ${source.printed_page})` : ''}`;
}
