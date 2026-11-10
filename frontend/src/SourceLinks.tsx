import { ReactNode } from 'react';
import { Icon } from './components';
import { SourceRef } from './types';
import './source-links.css';

export function sourceUrl(path:string,page?:number,timestamp?:number,end?:number) {
 const fragment=path.toLowerCase().endsWith('.mp4')&&timestamp!==undefined?`#t=${timestamp}${end!==undefined?`,${end}`:''}`:page&&path.toLowerCase().endsWith('.pdf')?`#page=${page}`:'';
 return `/api/source?path=${encodeURIComponent(path)}${fragment}`;
}

/** The script from the cited page onward (up to 40 pages): opens exactly there in every browser. */
export function pageUrl(path:string,page:number) {
 return `/api/source/pages?path=${encodeURIComponent(path)}&start=${page}`;
}

export function SourceDocumentLink({path,page,pageEnd,timestamp,end,children}:{path:string;page?:number|null;pageEnd?:number;timestamp?:number;end?:number;children?:ReactNode}) {
 const pdfPage=page&&path.toLowerCase().endsWith('.pdf')?page:undefined;
 const main=<a className="source-document-link" href={pdfPage?pageUrl(path,pdfPage):sourceUrl(path,page||undefined,timestamp,end)} target="_blank" rel="noreferrer" title={pdfPage?`Öffnet das Skript ab PDF-Seite ${pdfPage}; weiterblättern möglich`:undefined}><Icon name="file" size={15}/>{children||'Quelle öffnen'}<Icon name="arrow" size={14}/></a>;
 if(!pdfPage)return main;
 return <span className="source-document-links">{main}<a className="source-document-full" href={sourceUrl(path,pdfPage)} target="_blank" rel="noreferrer" title="Ganzes Skript; springt in Chrome und Firefox zur Seite, Safari öffnet am Anfang">Ganzes Skript</a></span>;
}

function videoTime(seconds:number) {
 const total=Math.floor(seconds),hours=Math.floor(total/3600),minutes=Math.floor(total%3600/60),remaining=total%60;
 return `${hours?`${hours}:`:''}${String(minutes).padStart(2,'0')}:${String(remaining).padStart(2,'0')}`;
}

export function SourceLinks({sources,title='Quellen zum Nachlesen und Ansehen',pdfLabel='Im Skript öffnen'}:{sources?:SourceRef[];title?:string;pdfLabel?:string}) {
 if(!sources?.length)return null;
 return <aside className="source-links" aria-label={title}><strong><Icon name="book" size={16}/>{title}</strong><ul>{sources.map((source,index)=>{
  if(source.kind==='video'){
   const times=source.timestamp_end_seconds!==undefined?`${videoTime(source.timestamp_seconds)}–${videoTime(source.timestamp_end_seconds)}`:videoTime(source.timestamp_seconds);
   return <li key={`${source.path}-${source.timestamp_seconds}-${index}`}><div><span className="source-reference-title">{source.title}</span><span className="source-reference-meta">{source.chapter&&`${source.chapter} · `}Video · {times}</span></div><SourceDocumentLink path={source.path} timestamp={source.timestamp_seconds} end={source.timestamp_end_seconds}>Im Video ansehen</SourceDocumentLink></li>;
  }
  const pages=source.pdf_page_end&&source.pdf_page_end!==source.pdf_page?`${source.pdf_page}–${source.pdf_page_end}`:String(source.pdf_page);
   return <li key={`${source.path}-${source.pdf_page}-${index}`}><div><span className="source-reference-title">{source.title}</span><span className="source-reference-meta">{source.chapter&&`${source.chapter} · `}PDF-Seite {pages}{source.printed_page&&` · gedruckte Seite ${source.printed_page}`}</span></div><SourceDocumentLink path={source.path} page={source.pdf_page} pageEnd={source.pdf_page_end}>{source.source_kind==='exam'?'Originalaufgabe öffnen':pdfLabel==='Im Skript öffnen'?`Ab PDF-Seite ${source.pdf_page} öffnen`:pdfLabel}</SourceDocumentLink></li>;
 })}</ul></aside>;
}
