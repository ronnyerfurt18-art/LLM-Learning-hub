# Local API contract v1
Same origin `/api`. JSON errors `{detail: string}`. Times ISO UTC. IDs strings except documents integer. All collections return arrays unless documented otherwise.

- GET /api/learning-pages -> [{module_id,module_number,module_title,lesson_count,has_big_picture?:true}]. `has_big_picture` is included with value `true` when the validated package has a Big Picture; it is omitted otherwise. `lesson_count` counts only actual lessons and can be 0 for an overview-only package. Module IDs resolve from existing module numbers; reads do not create modules or change progress.
- GET /api/learning-pages/:module_id -> complete validated content package plus module_id. Packages are local JSON files in `content/`. Each section and Big Picture node has concrete source references; images remain local under imports/assets. Missing packages return 404, invalid content returns 422 with details.
- GET /api/source?path=study-relative-path -> confined study original with its native MIME and inline Content-Disposition. PDF page navigation uses the browser fragment #page=N. MP4 playback supports Range (206 / 416), Accept-Ranges: bytes and #t=start,end (seconds). Application internals, external symlinks and directory traversal are rejected. Existing document download endpoint is retained.
- Optional Question fields: source_kind="course_material" labels newly derived course exercises; theory_sources contains PDF references {kind?:"pdf",path,title,chapter?,pdf_page,pdf_page_end?,printed_page?} or video references {kind:"video",path:MP4,title,chapter?,timestamp_seconds,timestamp_end_seconds?}. Paths are relative to the study folder, printed_page is text, times are finite numbers >=0 and end>=start. PDF and video fields must not be mixed. Video questions use source_page:null.

## Learning-page Big Picture

The additive optional field `overview.big_picture` uses the following shape. All required text fields are non-empty strings; `SourceRef` is the PDF/video reference shape documented above.

```text
overview.big_picture?: {
  title: string,
  central_question: string,
  intro: string,
  takeaway: string,
  nodes: [{
    id: string,
    title: string,
    summary: string,
    role: string,
    sources: SourceRef[],
    lesson_ids?: string[],
    scope_note?: string
  }],
  connections: [{from: string, to: string, label: string}]
}
```

Validation requires 3–7 nodes with unique IDs and at least one valid source per node. `connections` must contain at least one relationship; `from` and `to` reference existing, different node IDs, and `label` explains the relationship. Each optional `lesson_ids` entry must resolve to a lesson in the same package. Optional `scope_note` supplies a visible statement about the evidence or content scope. Sources must resolve to allowed existing study files and meet the shared PDF/video field contract.

An overview-only package may use `lessons: []` and `overview.units: []` only when it contains a valid Big Picture. Required overview text, learning path and source fields still apply. Such a package is available through the same learning-pages endpoints and does not create lessons or questions. For example, such a module has `lesson_count: 0` and `has_big_picture: true`.


Client behavior: selecting a concept scrolls and focuses its explanation, source links and matching lesson buttons. **Zur Themenlandkarte** returns to the selected concept in the map. Module cards expose **Big Picture öffnen** when `has_big_picture` is true, including packages with no lessons. PDF source links use `/api/source?path=…#page=N`. These navigation actions do not write learning progress. Content provenance and scope are recorded in [Big Pictures](big-pictures.md).

## Optional text tutor

- GET /api/tutor/status -> {configured:boolean,provider:"none"|"openai"|"ollama",model:string|null,data_flow:"none"|"local"|"cloud",message:string,capabilities:{text:true,voice:false}}. Reads process configuration without calling a model. configured means required settings exist, not successful connectivity.
- GET /api/tutor/context?module_id=&lesson_id=&section_id=&concept_id= -> {module_id,lesson_id?,section_id?,concept_id?,title,context_text,sources:[SourceRef & {id:"S1"...}],suggestions:string[],notice,instructions,context_preamble,excerpts:{S1:[{pdf_page,text}]}}. `excerpts` holds the cleaned original PDF text per source ID exactly as it was added to the context (watermark/checksum lines, repeated figure labels and line-break hyphens removed). Select a lesson (optionally one of its sections), a Big Picture concept, or the default module overview. Conflicting or unknown selections are rejected. Reads only the selected curated material and bounded referenced PDF excerpts. No model call or learning write.
- POST /api/tutor/chat {module_id,lesson_id?,section_id?,concept_id?,message,history?:[{role:"user"|"assistant",content}]} -> {answer,sources,provider,model,notice}. Requires explicitly configured provider/model and, for OpenAI, a server-only API key. Unconfigured requests return 503 with a readable explanation. Current message is limited to 4,000 characters; history to 12 messages and 20,000 characters. Caller system instructions, arbitrary source paths and extra fields are rejected. References returned to the UI are the server's validated context sources, not paths generated by the model.

- POST /api/tutor/chat and /api/tutor/chat/stream accept an optional boolean `think` (default false). It is applied only when the local model reports the `thinking` capability (`/api/tutor/status` field `thinking`); then `num_predict` rises to 6144 because reasoning tokens count towards it.
- POST /api/tutor/chat/stream (same body as /api/tutor/chat) -> `application/x-ndjson`, one JSON event per line: optional {type:"thinking",text} …, {type:"delta",text} …, then {type:"done",answer,sources,provider,model,notice} or {type:"error",status,detail}. Validation, context and configuration errors keep their HTTP status (400/404/503) before streaming starts; busy (429), provider and connection errors arrive as an error event. Ollama is called with `stream:true`; the generation lock is held only while the stream runs and is released on completion, error or browser disconnect. OpenAI falls back to one complete delta.

- GET /api/source/pages?path=&start=&end? -> application/pdf (inline). The study PDF from `start` onward (default up to 40 pages; explicit `end` at most 40 pages). Same path checks as /api/source; opens at the cited page in every browser, including Safari, which ignores `#page=`.

- Lernwiki (Etappe 2): GET /api/tutor/wiki?module_id=&goal_id=&id? -> {entry|null, versions:[{id,version,status,model,thinking,created_at}], stale}. POST /api/tutor/wiki/generate/stream {module_id, goal_id, think?:bool, improve?:str≤1000, base_id?} -> NDJSON like the chat stream (thinking/delta…, then {type:"done", …, entry} or error); creates the next version for the learning goal (content/tutor/goals.json) with separate solution instructions and 2200/8192 output tokens. POST /api/tutor/wiki/status {module_id, goal_id, id, status: draft|reviewed}. Table `tutor_wiki_entries` stores answer, sources, cited excerpt texts, provider, model, thinking flag, context hash (→ `stale`), improvement note, duration. Entries never change learning progress.

Chat turns, credentials and other tutor responses are not stored in SQLite; the only exception are Musterlösungen the learner explicitly creates in the Lernwiki. The tutor cannot mutate learning progress, perform tool actions or submit external coursework. Status and context reads and browser copy/export remain usable without a provider. Provider selection is opt-in via process environment, with fixed HTTPS OpenAI Responses or local loopback Ollama endpoints. Existing local host/origin checks also protect these routes. GET /api/settings adds tutor status independently of the existing disabled grading/import AI extension. See [setup and data flow](lernchat.md).

## Planning

- GET /api/planning?module_id= -> {events:StudyEvent[],timezone:"Europe/Berlin",today:"YYYY-MM-DD",notes:string[]}. Course dates are read-only seed entries in planning/study-events.json; reads do not create learning attempts or progress.
- POST /api/planning/events {module_id,title,kind:"study",start,end,all_day:false,timezone?:"Europe/Berlin",description?,location?} -> 201 StudyEvent. Start and end require offset-aware ISO datetimes; end must follow start. Personal study blocks cannot set source references or calendar_uid.
- PATCH /api/planning/events/:id {status:"planned"|"done"} -> StudyEvent. This updates a personal work status; it does not confirm an official submission or registration and cannot shift a source date.
- GET /api/planning/calendar.ics?module_id=&event_id= -> RFC 5545 calendar download (all events, module or single event). Stable UIDs preserve the identity of seeded calendar events. Explicit calendar_uid may only come from reviewed seeds and must be unique. Timed instants export in UTC; date-only ends are exclusive. Missing source end times are not invented.

StudyEvent: {id,module_id,title,kind:"deadline"|"exam"|"teaching"|"phase"|"study",start,end?,all_day,timezone:"Europe/Berlin",description,location?,source?,date_note?,status:"planned"|"done",calendar_uid?}. Source: {kind:"pdf"|"image"|"ics",path,title,chapter?,pdf_page?,pdf_page_end?}. Sources must resolve to existing permitted study originals, excluding application and private runtime directories. /api/source also serves PNG/JPEG and ICS originals with their native MIME types. Personal events and statuses use metadata key planning:state; existing question, attempt and progress tables are unchanged. Unlike the core learning timestamps, planning values use Berlin offsets or plain dates as appropriate.

## Learning, documents and progress

- GET /api/dashboard -> {modules:[Module], total_questions, studied_questions, mastered_questions, due_questions, next_exam:Module|null, last_module_id:string|null, recent_documents:[Document], activity:[{date,attempts,correct}], question_types:[{type,count}]}
- GET /api/modules -> Module[]
- POST /api/modules {name,number?,exam_date?,unit_count?,directory?} -> Module
- PATCH /api/modules/:id same -> Module
Module: {id,name,number,directory,exam_date,unit_count,question_count,studied_count,mastered_count,progress,success_rate,last_activity,weak_topics:[{topic,success_rate}],units:[number],unit_summaries:[{unit,question_count,studied_count,mastered_count,progress,success_rate,topics:string[]}]}
- GET /api/questions?module_id=&unit=&type=&difficulty=&due=true -> Question[]
Question: {id,module_id,unit,topic,type,question,original_question,original_solution,source,source_page,original_question_images?:ImageRef[],original_solution_images?:ImageRef[],options?:string[],correct_answers?:number[],pairs?:[{term,definition}],text?:string (contains ___),answers?:string[],synonyms?:string[][],model_answer,keywords?:string[],checklist?:string[],explanation,difficulty,verified,generated_by,correction_note?,progress?:{attempts,correct,incorrect,last_seen,next_due,interval,repetitions,ease,mastery}}
ImageRef: {path:string (assets/...),caption:string,source_page:positive integer}. GET /api/assets/:path serves a local raster source image from imports/assets/. Active exams retain question images and strip solution images.
Types single_choice, multiple_choice, matching, cloze, flashcard, free_text, case_analysis, exam_question. matching answer = {term: definition}; cloze answer = string[]; choices answer = number[] (indices from unshuffled options); open answer = string.
- POST /api/attempts {question_id,answer,rating?:0|3|4|5,manual_score?:0..1} -> {id,correct,score,max_score:1,grading:'automatic'|'keyword_hint'|'self',matched_keywords,missing_keywords,question:Question,next_due}
Open answer initial submission keyword_hint; can later PATCH /api/attempts/:id {manual_score,rating?} -> same response; do not create duplicate attempts. Flashcards require rating. Ratings 0=Nicht gewusst,3=Schwer,4=Gut,5=Einfach.
- GET /api/stats -> {activity:[{date,attempts,correct}], progress_history:[{date,studied}], exams:[{id,module_id,module_name,date,score,max_score,percentage}], difficulty:[{difficulty,count}], topics:[{topic,attempts,correct,success_rate}], modules:[Module]}
- GET /api/exams -> Exam[]
- POST /api/exams {module_id,units?:number[],types?:string[],difficulty?:number,count:number,duration_minutes:number} -> Exam
Exam active: {id,module_id,status:'active',started_at,deadline,duration_minutes,questions:[Question without solutions],answers:{qid:answer},current_index,count}
Exam submitted adds status:'submitted',submitted_at,score,max_score,percentage,results:[{question:Question,answer,correct,score,grading,matched_keywords,missing_keywords,attempt_id}],topics:[{topic,score,max_score}],recommended_question_ids:string[]
- GET /api/exams/:id -> Exam (expired auto-submits)
- PATCH /api/exams/:id {answers,current_index} -> Exam (autosave; expiration auto-submit)
- POST /api/exams/:id/submit {answers?} -> Exam
- PATCH /api/exams/:id/grade {question_id,manual_score,rating?} -> Exam
- GET /api/documents -> Document[]
Document: {id,path,title,module_id,module_name,unit,kind,status:'pending'|'imported'|'error'|'missing',error,size,pages,sha256,proposal_count,updated_at}
- POST /api/scan {} -> {new,changed,errors,total}
- GET /api/documents/:id -> Document + {text,proposals:[Question proposals]}
- PATCH /api/documents/:id {module_id,unit} -> Document (manual assignment, also possible with no proposals; persists on source changes)
- POST /api/documents/:id/confirm {module_id,unit,questions:[Question]} -> {imported}
- POST /api/import/preview {content:parsed JSON object} -> {valid,errors:string[],questions:[Question],module:{name,number},coverage:[],originals:[]}
- POST /api/import/confirm {content:parsed JSON object} -> {imported,module_id}
- GET /api/coverage?module_id=&unit= -> [{id,module_id,unit,topic,coverage:'complete'|'partial'|'missing',method:'keyword'|'gpt_work'|'manual',notes,keywords,source,summary_source}]
- POST /api/coverage/analyze {module_id,unit?} -> coverage rows (keyword hints separate from GPT assessment; each unit compared only with that unit's assigned summaries)
- PATCH /api/coverage/:id {coverage,notes} -> row (method manual)
- GET /api/export -> JSON download full modules/questions/progress/attempts/exams/coverage
- GET /api/backup -> SQLite snapshot download
- GET /api/settings -> {source_root,scan_interval_seconds,ai:{enabled:false,provider:'none'},database_path}
- GET /api/health -> {status:'ok',database_version,question_count}

Import JSON: {schema_version:1,module:{name,number,directory?,unit_count?,exam_date?},originals:[{id,unit,topic,source,source_page,original_question,original_solution,correction_note?}],questions:[Question minus module_id with id],coverage:[coverage row minus id/module_id]}. All question types must include model_answer, explanation, source, original_question, original_solution, unit,topic,difficulty (1-3), verified boolean,generated_by. AI additions labelled and originals kept intact. Verified means manually verified, default false; gpt_work assessments visibly labelled.

## Inhaltssuche

`GET /api/search?q=Kapital&module_id=M-10001&limit=30&offset=0` liest ausschließlich lokale Lernpakete und den bestehenden Dokumentenindex. `module_id` ist optional, ohne Angabe werden alle Module durchsucht. `q` ist auf 200 Zeichen begrenzt; `limit` liegt zwischen 1 und 100, `offset` beginnt bei 0. Leere Suchwörter liefern eine leere Ergebnismenge. Unbekannte Module liefern 404, ungültige Suchtexte 400, ungültige Parametergrenzen 422.

Antwort: `{query, terms, total, limit, offset, results, notice}`. Jeder Treffer besitzt `{id, kind, module_id, module_title, title, snippet}` sowie passende optionale Felder `unit`, `section_title`, `lesson_id`, `section_id`, `concept_id`, `source`, `sources`. `kind` ist `lesson`, `concept` oder `document`. Ein Modulüberblick nutzt `section_id: overview`; Kapitelzusammenfassungen können ohne Abschnittsziel erscheinen. PDF-Dateitreffer liefern in `source` die echte `pdf_page`; andere Dateitypen verwenden `kind: document` und gegebenenfalls eine Folien-/Blattbezeichnung in `chapter`. Diese Dokumentquelle ist ein Suchformat und erweitert nicht das strengere Quellenformat der Lernseiten.

Alle Suchwörter müssen in derselben Fundstelle einschließlich ihrer Überschrift vorkommen; Wortteile werden akzeptiert. Unicode, Akzente, Groß-/Kleinschreibung und ß/ss werden vereinheitlicht. Ergebnisse sind stabil sortiert und enthalten reine Textausschnitte, kein HTML. Die Suche schreibt keine Lern- oder Suchhistorie in die Datenbank und ruft kein Modell auf. Die unveränderte lokale HTTP-Zugriffsprotokollierung kann Anfrage-URLs enthalten. Siehe [Bedienung und Datenwege](inhaltssuche.md).
