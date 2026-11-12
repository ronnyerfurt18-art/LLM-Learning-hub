"""Durable learning domain. No network or model calls; SQLite migrations and SM-2."""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath

TYPES = {'single_choice', 'multiple_choice', 'matching', 'cloze', 'flashcard', 'free_text', 'case_analysis', 'exam_question'}
OPEN = {'free_text', 'case_analysis', 'exam_question'}


def now():
    return datetime.now(timezone.utc)


def iso(value=None):
    return (value or now()).isoformat()


def norm(value):
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    return re.sub(r'\s+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


def near(value, expected):
    a, b = norm(value), norm(expected)
    return a == b or (len(b) >= 5 and SequenceMatcher(None, a, b).ratio() >= .86)


def validate_import(content):
    errors = []
    if not isinstance(content, dict):
        return ['Import muss ein JSON-Objekt sein.']
    if content.get('schema_version') != 1:
        errors.append('schema_version muss 1 sein.')
    module = content.get('module', {})
    if not isinstance(module, dict) or not isinstance(module.get('name'), str) or not module['name'].strip():
        errors.append('Modulname fehlt.')
    questions = content.get('questions')
    if not isinstance(questions, list) or not questions:
        return errors + ['questions muss eine nicht leere Liste sein.']
    ids = set()
    for i, q in enumerate(questions):
        prefix = f'Frage {i + 1}: '
        if not isinstance(q, dict):
            errors.append(prefix + 'kein Objekt.')
            continue
        for key in ('id', 'question', 'source', 'original_question', 'original_solution', 'model_answer', 'explanation', 'topic', 'generated_by'):
            if not isinstance(q.get(key), str) or not q[key].strip():
                errors.append(prefix + key + ' fehlt oder ist leer.')
        qid = q.get('id')
        if isinstance(qid, str):
            if qid in ids:
                errors.append(prefix + 'doppelte ID.')
            ids.add(qid)
        kind = q.get('type')
        if not isinstance(kind, str) or kind not in TYPES:
            errors.append(prefix + 'unbekannter Fragetyp.')
            kind = None
        if type(q.get('unit')) is not int or q['unit'] < 1:
            errors.append(prefix + 'unit muss eine positive Zahl sein.')
        if type(q.get('difficulty')) is not int or q['difficulty'] not in (1, 2, 3):
            errors.append(prefix + 'difficulty muss 1–3 sein.')
        if type(q.get('verified')) is not bool:
            errors.append(prefix + 'verified muss boolean sein.')
        if kind in {'single_choice', 'multiple_choice'}:
            opts, correct = q.get('options'), q.get('correct_answers')
            if not isinstance(opts, list) or len(opts) < 2 or not all(isinstance(v, str) and v.strip() for v in opts):
                errors.append(prefix + 'mindestens zwei Antwortoptionen nötig.')
            if not isinstance(correct, list) or not correct or not isinstance(opts, list) or any(type(c) is not int or c < 0 or c >= len(opts) for c in correct):
                errors.append(prefix + 'ungültige richtige Antworten.')
            elif len(set(correct)) != len(correct) or (kind == 'single_choice' and len(correct) != 1):
                errors.append(prefix + 'richtige Antwortindizes müssen eindeutig sein.')
        if 'option_explanations' in q:
            explanations = q['option_explanations']
            if kind not in {'single_choice', 'multiple_choice'} or not isinstance(explanations, list) or not isinstance(q.get('options'), list) or len(explanations) != len(q['options']) or any(not isinstance(item, str) or not item.strip() for item in explanations):
                errors.append(prefix + 'Jede Auswahloption benötigt eine eigene nicht leere Erklärung.')
        if 'model_answer_sections' in q:
            sections = q['model_answer_sections']
            if not isinstance(sections, list) or not sections:
                errors.append(prefix + 'Die gegliederte Musterantwort benötigt mindestens einen Abschnitt.')
            else:
                for section in sections:
                    if not isinstance(section, dict):
                        errors.append(prefix + 'Jeder Abschnitt der Musterantwort muss ein Objekt sein.')
                        continue
                    if 'title' in section and (not isinstance(section['title'], str) or not section['title'].strip()):
                        errors.append(prefix + 'Abschnittstitel der Musterantwort müssen lesbarer Text sein.')
                    for field in ('paragraphs', 'items'):
                        if field in section and (not isinstance(section[field], list) or not section[field] or any(not isinstance(item, str) or not item.strip() for item in section[field])):
                            errors.append(prefix + 'Absätze und Aufzählungen der Musterantwort benötigen nicht leere Textlisten.')
                    if 'entries' in section:
                        entries = section['entries']
                        if not isinstance(entries, list) or not entries or any(not isinstance(entry, dict) or not isinstance(entry.get('term'), str) or not entry['term'].strip() or ('description' in entry and (not isinstance(entry['description'], str) or not entry['description'].strip())) for entry in entries):
                            errors.append(prefix + 'Begriffserklärungen der Musterantwort benötigen einen Begriff und gegebenenfalls eine lesbare Erklärung.')
                    if not any(section.get(field) for field in ('paragraphs', 'items', 'entries')):
                        errors.append(prefix + 'Ein Abschnitt der Musterantwort benötigt Inhalt.')
        if 'learning_context' in q:
            context = q['learning_context']
            if not isinstance(context, dict) or not isinstance(context.get('title'), str) or not context['title'].strip():
                errors.append(prefix + 'Die Lernvertiefung benötigt einen Titel.')
            else:
                paragraphs, table = context.get('paragraphs', []), context.get('table')
                if not isinstance(paragraphs, list) or any(not isinstance(item, str) or not item.strip() for item in paragraphs):
                    errors.append(prefix + 'Die Lernvertiefung benötigt lesbare Absätze.')
                if not paragraphs and table is None:
                    errors.append(prefix + 'Die Lernvertiefung benötigt Inhalt.')
                if table is not None:
                    headers, rows = (table.get('headers'), table.get('rows')) if isinstance(table, dict) else (None, None)
                    if not isinstance(headers, list) or not headers or any(not isinstance(v, str) or not v.strip() for v in headers) or not isinstance(rows, list) or not rows or any(not isinstance(row, list) or len(row) != len(headers) or any(not isinstance(cell, str) or not cell.strip() for cell in row) for row in rows):
                        errors.append(prefix + 'Die Tabelle der Lernvertiefung benötigt passende Spalten und Zeilen.')
                refs = context.get('sources')
                if not isinstance(refs, list) or not refs:
                    errors.append(prefix + 'Die Lernvertiefung benötigt konkrete Quellen.')
                else:
                    # Reuse the established source contract without recursively validating feedback.
                    source_question = {k: v for k, v in q.items() if k not in {'learning_context', 'option_explanations'}}
                    source_question['theory_sources'] = refs
                    source_errors = validate_import({'schema_version': 1, 'module': {'name': 'Quellenprüfung'}, 'questions': [source_question]})
                    errors.extend(prefix + 'Lernvertiefung: ' + error for error in source_errors)
        if kind == 'matching':
            pairs = q.get('pairs')
            if not isinstance(pairs, list) or len(pairs) < 2 or any(not isinstance(p, dict) or not isinstance(p.get('term'), str) or not p['term'].strip() or not isinstance(p.get('definition'), str) or not p['definition'].strip() for p in pairs):
                errors.append(prefix + 'Zuordnungspaare fehlen.')
            elif len({norm(p['term']) for p in pairs}) != len(pairs) or len({norm(p['definition']) for p in pairs}) != len(pairs):
                errors.append(prefix + 'Begriffe und Definitionen müssen eindeutig sein.')
        if kind == 'cloze':
            answers, sentence = q.get('answers'), q.get('text')
            if not isinstance(answers, list) or not answers or not all(isinstance(a, str) and a for a in answers) or not isinstance(sentence, str) or sentence.count('___') != len(answers):
                errors.append(prefix + 'Anzahl ___ und Lückenlösungen muss übereinstimmen.')
        if q.get('source_page') is not None and (type(q['source_page']) is not int or q['source_page'] < 1):
            errors.append(prefix + 'source_page muss eine positive Zahl sein.')
        if 'source_kind' in q and q['source_kind'] != 'course_material':
            errors.append(prefix + 'source_kind muss course_material sein, wenn angegeben.')
        if 'theory_sources' in q:
            refs = q['theory_sources']
            if not isinstance(refs, list) or not refs:
                errors.append(prefix + 'theory_sources benötigt mindestens einen konkreten Beleg.')
            else:
                for ref in refs:
                    if not isinstance(ref, dict) or any(not isinstance(ref.get(key), str) or not ref[key].strip() for key in ('path', 'title')):
                        errors.append(prefix + 'Theoriebeleg benötigt Pfad und Titel.')
                        continue
                    path = PurePosixPath(ref['path'])
                    if path.is_absolute() or '..' in path.parts:
                        errors.append(prefix + 'Theoriebeleg benötigt einen relativen Studienpfad.')
                    if ref.get('kind') == 'video':
                        start, end = ref.get('timestamp_seconds'), ref.get('timestamp_end_seconds')
                        def valid_seconds(value):
                            try:
                                return type(value) in (int, float) and math.isfinite(value) and value >= 0
                            except OverflowError:
                                return False
                        if path.suffix.lower() != '.mp4' or not valid_seconds(start):
                            errors.append(prefix + 'Videobeleg benötigt eine MP4-Datei und eine gültige Zeitmarke.')
                        if 'timestamp_end_seconds' in ref and (not valid_seconds(end) or (valid_seconds(start) and end < start)):
                            errors.append(prefix + 'Ungültiges Zeitende im Videobeleg.')
                        if any(key in ref for key in ('pdf_page', 'pdf_page_end', 'printed_page')):
                            errors.append(prefix + 'Videobeleg darf keine PDF-Seiten enthalten.')
                    else:
                        if ref.get('kind') not in (None, 'pdf') or path.suffix.lower() != '.pdf':
                            errors.append(prefix + 'Theoriebeleg benötigt eine PDF-Datei oder kind video.')
                        if type(ref.get('pdf_page')) is not int or ref['pdf_page'] < 1:
                            errors.append(prefix + 'Theoriebeleg benötigt eine positive PDF-Seite.')
                        if 'pdf_page_end' in ref and (type(ref['pdf_page_end']) is not int or ref['pdf_page_end'] < 1 or (type(ref.get('pdf_page')) is int and ref['pdf_page_end'] < ref['pdf_page'])):
                            errors.append(prefix + 'Ungültiges Seitenende im Theoriebeleg.')
                        if any(key in ref for key in ('timestamp_seconds', 'timestamp_end_seconds')):
                            errors.append(prefix + 'PDF-Beleg darf keine Videozeitmarken enthalten.')
                    for key in ('chapter', 'printed_page'):
                        if key in ref and (not isinstance(ref[key], str) or not ref[key].strip()):
                            errors.append(prefix + key + ' im Theoriebeleg muss Text sein.')
        for field in ('keywords', 'checklist'):
            if field in q and (not isinstance(q[field], list) or not all(isinstance(s, str) and s.strip() for s in q[field])):
                errors.append(prefix + field + ' muss eine Textliste sein.')
        if 'question_context' in q and (not isinstance(q['question_context'], str) or not q['question_context'].strip()):
            errors.append(prefix + 'question_context muss ein nicht leerer Text sein.')
        if 'question_context_source' in q:
            ref = q['question_context_source']
            if not isinstance(ref, dict) or not isinstance(ref.get('path'), str) or not ref['path'].strip() or type(ref.get('source_page')) is not int or ref['source_page'] < 1:
                errors.append(prefix + 'Ausgangssituation benötigt Quellenpfad und positive Quellseite.')
        if 'synonyms' in q and (not isinstance(q['synonyms'], list) or any(not isinstance(s, list) or not all(isinstance(t, str) and t for t in s) for s in q['synonyms'])):
            errors.append(prefix + 'synonyms muss eine Liste von Textlisten sein.')
        for field in ('original_question_images', 'original_solution_images'):
            if field not in q:
                continue
            refs = q[field]
            if not isinstance(refs, list):
                errors.append(prefix + field + ' muss eine Liste sein.')
                continue
            for ref in refs:
                if not isinstance(ref, dict) or not isinstance(ref.get('path'), str) or not isinstance(ref.get('caption'), str):
                    errors.append(prefix + 'Abbildungen benötigen Pfad und Bildbeschreibung.')
                    continue
                path = PurePosixPath(ref['path'])
                if path.is_absolute() or '..' in path.parts or not ref['path'].startswith('assets/') or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
                    errors.append(prefix + 'Abbildung muss eine lokale Bilddatei in assets/ sein.')
                if type(ref.get('source_page')) is not int or ref['source_page'] < 1:
                    errors.append(prefix + 'Abbildung benötigt eine positive Quellseite.')
    originals = content.get('originals', [])
    if not isinstance(originals, list):
        errors.append('originals muss eine Liste sein.')
        originals = []
    original_ids = set()
    for orig in originals:
        if not isinstance(orig, dict) or any(not isinstance(orig.get(key), str) or not orig[key].strip() for key in ('id', 'original_question', 'original_solution', 'source')):
            errors.append('Ungültige Originalübung.')
        elif orig['id'] in original_ids:
            errors.append('Doppelte Original-ID.')
        else:
            original_ids.add(orig['id'])
    coverage = content.get('coverage', [])
    if not isinstance(coverage, list):
        errors.append('coverage muss eine Liste sein.')
        coverage = []
    for row in coverage:
        if not isinstance(row, dict) or not isinstance(row.get('topic'), str) or not row['topic'].strip() or not isinstance(row.get('coverage'), str) or row['coverage'] not in {'complete', 'partial', 'missing'} or not isinstance(row.get('method'), str) or row['method'] not in {'gpt_work', 'keyword', 'manual'}:
            errors.append('Ungültiger Abdeckungseintrag.')
    return errors


def grade(question, answer, rating=None, manual_score=None):
    kind = question['type']
    matched, missing = [], []
    if manual_score is not None:
        if not isinstance(manual_score, (int, float)) or isinstance(manual_score, bool) or not 0 <= manual_score <= 1:
            raise ValueError('Selbstbewertung muss zwischen 0 und 1 liegen.')
        score, grading = float(manual_score), 'self'
    elif kind == 'flashcard':
        if rating not in (0, 3, 4, 5):
            raise ValueError('Karteikarten benötigen eine Selbstbewertung.')
        score, grading = (0.0 if rating == 0 else 1.0), 'self'
    elif kind in {'single_choice', 'multiple_choice'}:
        if not isinstance(answer, list) or any(type(v) is not int or v < 0 or v >= len(question['options']) for v in answer) or len(set(answer)) != len(answer) or (kind == 'single_choice' and len(answer) > 1):
            raise ValueError('Bitte Antwortoptionen auswählen.')
        score, grading = float(set(answer) == set(question['correct_answers'])), 'automatic'
    elif kind == 'matching':
        if not isinstance(answer, dict) or any(not isinstance(v, str) for v in answer.values()):
            raise ValueError('Zuordnungen fehlen.')
        pairs = question['pairs']
        score = sum(norm(answer.get(p['term'], '')) == norm(p['definition']) for p in pairs) / len(pairs)
        grading = 'automatic'
    elif kind == 'cloze':
        if not isinstance(answer, list) or any(not isinstance(v, str) for v in answer):
            raise ValueError('Lückenantworten fehlen.')
        synonyms = question.get('synonyms', [])
        answers = question['answers']
        count = 0
        for i, target in enumerate(answers):
            extra = synonyms[i] if i < len(synonyms) and isinstance(synonyms[i], list) else []
            if i < len(answer) and any(near(answer[i], v) for v in [target] + extra):
                count += 1
        score, grading = count / len(answers), 'automatic'
    else:
        if not isinstance(answer, str):
            raise ValueError('Freitextantwort muss Text sein.')
        text = norm(answer)
        for keyword in question.get('keywords', []):
            # Phrases matched literally; no claim of semantic evaluation.
            (matched if norm(keyword) in text else missing).append(keyword)
        score = len(matched) / max(1, len(matched) + len(missing))
        grading = 'keyword_hint'
    return {'score': round(score, 4), 'correct': score >= .9999, 'grading': grading, 'matched_keywords': matched, 'missing_keywords': missing, 'max_score': 1}


def sm2(previous, rating, at=None):
    """SM-2 grades 0/3/4/5. Failures return in 10 minutes, then restart interval."""
    at = at or now()
    repetitions = previous.get('repetitions', 0)
    interval = previous.get('interval', 0)
    ease = max(1.3, previous.get('ease', 2.5) + .1 - (5 - rating) * (.08 + (5 - rating) * .02))
    if rating < 3:
        repetitions, interval, due = 0, 0, at + timedelta(minutes=10)
    else:
        interval = 1 if repetitions == 0 else 6 if repetitions == 1 else max(1, math.ceil(interval * ease))
        repetitions += 1
        due = at + timedelta(days=interval)
    return {'repetitions': repetitions, 'interval': interval, 'ease': round(ease, 3), 'next_due': iso(due), 'mastery': min(100, round(repetitions / 5 * 100))}


# How a module calls its numbered parts; stored per module in the metadata table.
UNIT_LABELS = ('Einheit', 'Session', 'Kapitel', 'Lektion', 'Woche')
UNIT_LABEL_KEY = 'module_unit_labels'


class Hub:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def migrate(self):
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS modules(id TEXT PRIMARY KEY,name TEXT NOT NULL,number TEXT,directory TEXT,exam_date TEXT,unit_count INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY,module_id TEXT NOT NULL REFERENCES modules(id),unit INTEGER NOT NULL,topic TEXT NOT NULL,type TEXT NOT NULL,difficulty INTEGER NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS originals(id TEXT PRIMARY KEY,module_id TEXT NOT NULL REFERENCES modules(id),payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS progress(question_id TEXT PRIMARY KEY REFERENCES questions(id),attempts INTEGER NOT NULL DEFAULT 0,correct INTEGER NOT NULL DEFAULT 0,incorrect INTEGER NOT NULL DEFAULT 0,last_seen TEXT,next_due TEXT,interval INTEGER NOT NULL DEFAULT 0,repetitions INTEGER NOT NULL DEFAULT 0,ease REAL NOT NULL DEFAULT 2.5,mastery INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,question_id TEXT NOT NULL REFERENCES questions(id),created_at TEXT NOT NULL,answer TEXT NOT NULL,score REAL NOT NULL,grading TEXT NOT NULL,rating INTEGER NOT NULL,result TEXT NOT NULL,previous_progress TEXT NOT NULL,exam_id TEXT);
            CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY,module_id TEXT NOT NULL REFERENCES modules(id),status TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,path TEXT UNIQUE NOT NULL,module_id TEXT REFERENCES modules(id),payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS coverage(id TEXT PRIMARY KEY,module_id TEXT NOT NULL REFERENCES modules(id),payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_questions_module ON questions(module_id,unit);
            CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id,created_at);
            CREATE INDEX IF NOT EXISTS idx_progress_due ON progress(next_due);
            ''')
            db.execute('INSERT OR IGNORE INTO migrations VALUES(1,?)', (iso(),))

    def get_meta(self, key):
        with self.db() as db:
            r = db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
            return json.loads(r[0]) if r else None

    def set_meta(self, key, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def _unit_label(self, value):
        label = value.get('unit_label') or UNIT_LABELS[0]
        if not isinstance(label, str):
            raise ValueError('Bezeichnung der Lerneinheiten muss Text sein.')
        return label.strip() or UNIT_LABELS[0]

    def _store_unit_label(self, mid, label):
        labels = self.get_meta(UNIT_LABEL_KEY) or {}
        if labels.get(mid, UNIT_LABELS[0]) != label:
            labels[mid] = label
            self.set_meta(UNIT_LABEL_KEY, labels)

    def add_module(self, value):
        if not isinstance(value.get('name'), str):
            raise ValueError('Modulname muss Text sein.')
        name = value['name'].strip()
        if not name:
            raise ValueError('Modulname fehlt.')
        number = str(value.get('number') or '').strip()
        directory = str(value.get('directory') or '').strip()
        units = value.get('unit_count', 1)
        if type(units) is not int or not 1 <= units <= 999:
            raise ValueError('Kurseinheiten müssen zwischen 1 und 999 liegen.')
        label = self._unit_label(value)
        exam_date = value.get('exam_date') or None
        if exam_date:
            try:
                datetime.strptime(exam_date, '%Y-%m-%d')
            except (ValueError, TypeError):
                raise ValueError('Prüfungstermin muss YYYY-MM-DD sein.')
        with self.db() as db:
            match = db.execute('SELECT id FROM modules WHERE number=?', (number,)).fetchone() if number else None
            if not match:
                match = db.execute('SELECT id FROM modules WHERE name=?', (name,)).fetchone()
            if match:
                return self.module(match[0])
            mid = 'M-' + (number if re.fullmatch(r'\d{5}', number) else uuid.uuid4().hex[:10])
            db.execute('INSERT INTO modules VALUES(?,?,?,?,?,?)', (mid, name, number, directory, exam_date, units))
        self._store_unit_label(mid, label)
        return self.module(mid)

    def patch_module(self, mid, value):
        old = self.module(mid)
        merged = {**old, **value}
        if not isinstance(merged.get('name'), str) or not merged['name'].strip() or type(merged['unit_count']) is not int or not 1 <= merged['unit_count'] <= 999:
            raise ValueError('Name und gültige Kurseinheiten benötigt.')
        if merged.get('exam_date'):
            if not isinstance(merged['exam_date'], str):
                raise ValueError('Prüfungstermin muss YYYY-MM-DD sein.')
            datetime.strptime(merged['exam_date'], '%Y-%m-%d')
        label = self._unit_label(merged)
        with self.db() as db:
            db.execute('UPDATE modules SET name=?,number=?,directory=?,exam_date=?,unit_count=? WHERE id=?', (merged['name'], str(merged.get('number') or '').strip(), merged.get('directory') or '', merged.get('exam_date') or None, merged['unit_count'], mid))
        self._store_unit_label(mid, label)
        return self.module(mid)

    def modules(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM modules ORDER BY number,name')]
        return [self.module(mid) for mid in ids]

    def module(self, mid):
        with self.db() as db:
            r = db.execute('SELECT * FROM modules WHERE id=?', (mid,)).fetchone()
            if not r:
                raise KeyError('Modul nicht gefunden.')
            m = dict(r)
            stored = db.execute('SELECT value FROM metadata WHERE key=?', (UNIT_LABEL_KEY,)).fetchone()
            m['unit_label'] = (json.loads(stored[0]) if stored else {}).get(mid, UNIT_LABELS[0])
            rows = db.execute('SELECT q.id,q.unit,q.topic,p.* FROM questions q LEFT JOIN progress p ON p.question_id=q.id WHERE q.module_id=?', (mid,)).fetchall()
            n = len(rows)
            studied = sum(bool(r['attempts']) for r in rows)
            mastered = sum((r['mastery'] or 0) >= 60 for r in rows)
            attempts = sum(r['attempts'] or 0 for r in rows)
            correct = sum(r['correct'] or 0 for r in rows)
            topics = {}
            for row in rows:
                if row['attempts']:
                    topic = topics.setdefault(row['topic'], [0, 0])
                    topic[0] += row['correct'] or 0
                    topic[1] += row['attempts'] or 0
            weak = sorted([{'topic': t, 'success_rate': round(c / a * 100)} for t, (c, a) in topics.items()], key=lambda t: t['success_rate'])[:3]
            units = sorted({r['unit'] for r in rows} | set(range(1, m['unit_count'] + 1)))
            summaries = []
            for unit in units:
                unit_rows = [r for r in rows if r['unit'] == unit]
                unit_studied = sum(bool(r['attempts']) for r in unit_rows)
                unit_attempts = sum(r['attempts'] or 0 for r in unit_rows)
                unit_correct = sum(r['correct'] or 0 for r in unit_rows)
                summaries.append({'unit': unit, 'question_count': len(unit_rows), 'studied_count': unit_studied, 'mastered_count': sum((r['mastery'] or 0) >= 60 for r in unit_rows), 'progress': round(unit_studied / max(len(unit_rows), 1) * 100), 'success_rate': round(unit_correct / max(unit_attempts, 1) * 100), 'topics': list(dict.fromkeys(r['topic'] for r in unit_rows))})
            m.update(question_count=n, studied_count=studied, mastered_count=mastered, progress=round(studied / max(n, 1) * 100), success_rate=round(correct / max(attempts, 1) * 100), last_activity=max((r['last_seen'] for r in rows if r['last_seen']), default=None), weak_topics=weak, units=units, unit_summaries=summaries)
            return m

    def question(self, qid):
        with self.db() as db:
            r = db.execute('SELECT payload,module_id FROM questions WHERE id=?', (qid,)).fetchone()
            if not r:
                raise KeyError('Frage nicht gefunden.')
            q = json.loads(r['payload'])
            q['module_id'] = r['module_id']
            p = db.execute('SELECT * FROM progress WHERE question_id=?', (qid,)).fetchone()
            q['progress'] = dict(p) if p else None
            return q

    def questions(self, module_id=None, unit=None, type=None, difficulty=None, due=False):
        sql, args = 'SELECT q.id FROM questions q LEFT JOIN progress p ON p.question_id=q.id WHERE 1=1', []
        for col, v in (('module_id', module_id), ('unit', unit), ('type', type), ('difficulty', difficulty)):
            if v is not None and v != '':
                sql += f' AND q.{col}=?'
                args.append(v)
        if due:
            sql += ' AND p.next_due<=?'
            args.append(iso())
        sql += ' ORDER BY COALESCE(p.next_due,\'9999\'),q.unit,q.id'
        with self.db() as db:
            ids = [r[0] for r in db.execute(sql, args)]
        return [self.question(i) for i in ids]

    def import_content(self, content, update_existing=False):
        errors = validate_import(content)
        if errors:
            raise ValueError('\n'.join(errors[:30]))
        m = self.add_module(content['module'])
        count = 0
        with self.db() as db:
            for q in content['questions']:
                existing = db.execute('SELECT module_id FROM questions WHERE id=?', (q['id'],)).fetchone()
                if existing:
                    if existing[0] != m['id']:
                        raise ValueError(f"Fragen-ID {q['id']} gehört zu einem anderen Modul.")
                    if update_existing:
                        # Explicitly approved source revisions keep IDs, answers and progress.
                        db.execute('UPDATE questions SET unit=?,topic=?,type=?,difficulty=?,payload=? WHERE id=?',
                                   (q['unit'], q['topic'], q['type'], q['difficulty'], json.dumps(q, ensure_ascii=False), q['id']))
                    continue  # Ordinary imports retain the existing learning/source content.
                db.execute('INSERT INTO questions VALUES(?,?,?,?,?,?,?)', (q['id'], m['id'], q['unit'], q['topic'], q['type'], q['difficulty'], json.dumps(q, ensure_ascii=False)))
                count += 1
            for orig in content.get('originals', []):
                existing = db.execute('SELECT module_id FROM originals WHERE id=?', (orig['id'],)).fetchone()
                if existing and existing[0] != m['id']:
                    raise ValueError(f"Original-ID {orig['id']} gehört zu einem anderen Modul.")
                db.execute('INSERT OR IGNORE INTO originals VALUES(?,?,?)', (orig['id'], m['id'], json.dumps(orig, ensure_ascii=False)))
            for row in content.get('coverage', []):
                cid = f"{m['id']}:{row.get('unit', 1)}:{row['topic']}:{row['method']}"
                db.execute('INSERT OR IGNORE INTO coverage VALUES(?,?,?)', (cid, m['id'], json.dumps(row, ensure_ascii=False)))
            max_unit = max(q['unit'] for q in content['questions'])
            db.execute('UPDATE modules SET unit_count=MAX(unit_count,?) WHERE id=?', (max_unit, m['id']))
        return {'imported': count, 'module_id': m['id']}

    def progress(self, qid):
        with self.db() as db:
            r = db.execute('SELECT * FROM progress WHERE question_id=?', (qid,)).fetchone()
        return dict(r) if r else {'attempts': 0, 'correct': 0, 'incorrect': 0, 'interval': 0, 'repetitions': 0, 'ease': 2.5, 'mastery': 0}

    def write_progress(self, db, qid, prev, score, rating, at):
        p = {**prev, **sm2(prev, rating, datetime.fromisoformat(at))}
        p.update(attempts=prev.get('attempts', 0) + 1, correct=prev.get('correct', 0) + int(score >= .9999), incorrect=prev.get('incorrect', 0) + int(score < .9999), last_seen=at)
        db.execute('INSERT OR REPLACE INTO progress VALUES(?,?,?,?,?,?,?,?,?,?)', (qid, p['attempts'], p['correct'], p['incorrect'], at, p['next_due'], p['interval'], p['repetitions'], p['ease'], p['mastery']))
        return p

    def attempt(self, qid, answer, rating=None, manual_score=None, exam_id=None):
        q = self.question(qid)
        if manual_score is not None and q['type'] not in OPEN | {'flashcard'}:
            raise ValueError('Nur offene Aufgaben lassen sich selbst bewerten.')
        result = grade(q, answer, rating, manual_score)
        rating = rating if rating is not None else (4 if result['correct'] else 0)
        if rating not in (0, 3, 4, 5):
            raise ValueError('Ungültige Wiederholungsbewertung.')
        aid, at = uuid.uuid4().hex, iso()
        with self.db() as db:
            row = db.execute('SELECT * FROM progress WHERE question_id=?', (qid,)).fetchone()
            prev = dict(row) if row else self.progress(qid)
            p = self.write_progress(db, qid, prev, result['score'], rating, at)
            db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)', (aid, qid, at, json.dumps(answer, ensure_ascii=False), result['score'], result['grading'], rating, json.dumps(result), json.dumps(prev), exam_id))
            db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('last_module_id', json.dumps(q['module_id'])))
        q['progress'] = p
        return {**result, 'id': aid, 'question': q, 'next_due': p['next_due']}

    def correct_attempt(self, aid, manual_score, rating=None):
        with self.db() as db:
            r = db.execute('SELECT * FROM attempts WHERE id=?', (aid,)).fetchone()
            if not r:
                raise KeyError('Versuch nicht gefunden.')
            r = dict(r)
            q = self.question(r['question_id'])
            if q['type'] not in OPEN | {'flashcard'}:
                raise ValueError('Nur offene Aufgaben lassen sich selbst bewerten.')
            result = grade(q, json.loads(r['answer']), manual_score=manual_score)
            rating = rating if rating is not None else (4 if result['correct'] else 0)
            if rating not in (0, 3, 4, 5):
                raise ValueError('Ungültige Wiederholungsbewertung.')
            db.execute('UPDATE attempts SET score=?,grading=?,rating=?,result=? WHERE id=?', (result['score'], result['grading'], rating, json.dumps(result), aid))
            # Replay all attempts in order: a correction cannot overwrite later reviews.
            p = {'attempts': 0, 'correct': 0, 'incorrect': 0, 'interval': 0, 'repetitions': 0, 'ease': 2.5, 'mastery': 0}
            for a in db.execute('SELECT * FROM attempts WHERE question_id=? ORDER BY created_at,id', (r['question_id'],)).fetchall():
                p = self.write_progress(db, r['question_id'], p, a['score'], a['rating'], a['created_at'])
        q['progress'] = p
        return {**result, 'id': aid, 'question': q, 'next_due': p['next_due']}

    def stats(self):
        # Expiration can create attempts; settle exams before computing statistics.
        exam_records = self.exams()
        with self.db() as db:
            activity = [dict(r) for r in db.execute('SELECT substr(created_at,1,10) date,count(*) attempts,sum(score>=0.9999) correct FROM attempts GROUP BY date ORDER BY date')]
            difficulty = [dict(r) for r in db.execute('SELECT difficulty,count(*) count FROM questions GROUP BY difficulty ORDER BY difficulty')]
            topics = [dict(r) for r in db.execute('SELECT q.topic,count(*) attempts,sum(a.score>=0.9999) correct,round(100.0*sum(a.score>=0.9999)/count(*)) success_rate FROM attempts a JOIN questions q ON q.id=a.question_id GROUP BY q.topic')]
            first_studied = db.execute('SELECT substr(min(created_at),1,10) date FROM attempts GROUP BY question_id').fetchall()
        new_per_day = {}
        for row in first_studied:
            new_per_day[row['date']] = new_per_day.get(row['date'], 0) + 1
        progress_history, studied = [], 0
        for date in sorted(new_per_day):
            studied += new_per_day[date]
            progress_history.append({'date': date, 'studied': studied})
        exams = []
        for exam in exam_records:
            if exam['status'] == 'submitted':
                exams.append({'id': exam['id'], 'module_id': exam['module_id'], 'module_name': self.module(exam['module_id'])['name'], 'date': exam['submitted_at'], 'score': exam['score'], 'max_score': exam['max_score'], 'percentage': exam['percentage']})
        return {'activity': activity, 'difficulty': difficulty, 'topics': topics, 'exams': exams, 'modules': self.modules(), 'progress_history': progress_history}

    def dashboard(self):
        stats = self.stats()
        modules = stats['modules']
        with self.db() as db:
            due = db.execute('SELECT count(*) FROM progress WHERE next_due<=?', (iso(),)).fetchone()[0]
            types = [dict(r) for r in db.execute('SELECT type,count(*) count FROM questions GROUP BY type')]
        forthcoming = sorted((m for m in modules if m['exam_date'] and m['exam_date'] >= now().date().isoformat()), key=lambda m: m['exam_date'])
        return {'modules': modules, 'total_questions': sum(m['question_count'] for m in modules), 'studied_questions': sum(m['studied_count'] for m in modules), 'mastered_questions': sum(m['mastered_count'] for m in modules), 'due_questions': due, 'next_exam': forthcoming[0] if forthcoming else None, 'last_module_id': self.get_meta('last_module_id'), 'recent_documents': [d for d in self.documents() if d['status'] == 'pending'][:5], 'activity': stats['activity'], 'question_types': types}

    def create_exam(self, config):
        self.module(config['module_id'])
        count, duration = config.get('count', 10), config.get('duration_minutes', 30)
        if type(count) is not int or not 1 <= count <= 200 or not isinstance(duration, (int, float)) or isinstance(duration, bool) or not 1 <= duration <= 360:
            raise ValueError('1–200 Fragen und 1–360 Minuten sind möglich.')
        pool = self.questions(module_id=config['module_id'], difficulty=config.get('difficulty') or None)
        pool = [q for q in pool if (not config.get('units') or q['unit'] in config['units']) and (not config.get('types') or q['type'] in config['types']) and q['type'] != 'flashcard']
        if not pool:
            raise ValueError('Keine passenden Prüfungsfragen vorhanden. Karteikarten sind vom Klausurmodus ausgeschlossen.')
        picked = random.sample(pool, min(count, len(pool)))
        eid = uuid.uuid4().hex
        exam = {'id': eid, 'module_id': config['module_id'], 'status': 'active', 'started_at': iso(), 'deadline': iso(now() + timedelta(minutes=duration)), 'duration_minutes': duration, 'question_ids': [q['id'] for q in picked], 'answers': {}, 'current_index': 0, 'count': len(picked)}
        self.save_exam(exam)
        return self.exam(eid)

    def save_exam(self, exam):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO exams VALUES(?,?,?,?)', (exam['id'], exam['module_id'], exam['status'], json.dumps(exam, ensure_ascii=False)))

    def raw_exam(self, eid):
        with self.db() as db:
            r = db.execute('SELECT payload FROM exams WHERE id=?', (eid,)).fetchone()
        if not r:
            raise KeyError('Klausur nicht gefunden.')
        return json.loads(r[0])

    def exams(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM exams ORDER BY rowid DESC')]
        return [self.exam(i) for i in ids]

    def exam(self, eid):
        e = self.raw_exam(eid)
        if e['status'] == 'active' and datetime.fromisoformat(e['deadline']) <= now():
            return self.submit_exam(eid)
        if e['status'] == 'active':
            hidden = {'correct_answers', 'pairs', 'answers', 'synonyms', 'model_answer', 'model_answer_sections', 'original_question', 'original_solution', 'original_solution_images', 'explanation', 'option_explanations', 'learning_context', 'correction_note', 'keywords', 'checklist', 'progress'}
            questions = []
            for qid in e['question_ids']:
                q = self.question(qid)
                public = {k: v for k, v in q.items() if k not in hidden}
                if q['type'] == 'matching':
                    public['terms'] = [p['term'] for p in q['pairs']]
                    defs = [p['definition'] for p in q['pairs']]
                    random.Random(eid + qid).shuffle(defs)
                    public['definitions'] = defs
                questions.append(public)
            return {**e, 'questions': questions}
        results = []
        for result in e.get('results', []):
            with self.db() as db:
                a = db.execute('SELECT result FROM attempts WHERE id=?', (result['attempt_id'],)).fetchone()
            results.append({**result, **(json.loads(a[0]) if a else {}), 'question': self.question(result['question_id'])})
        topics = {}
        for r in results:
            topic = topics.setdefault(r['question']['topic'], {'topic': r['question']['topic'], 'score': 0, 'max_score': 0})
            topic['score'] += r['score']
            topic['max_score'] += 1
        score = round(sum(r['score'] for r in results), 2)
        return {**e, 'results': results, 'score': score, 'max_score': len(results), 'percentage': round(score / max(len(results), 1) * 100), 'topics': list(topics.values()), 'recommended_question_ids': [r['question_id'] for r in results if not r['correct']]}

    def update_exam(self, eid, answers=None, current_index=None):
        e = self.raw_exam(eid)
        if e['status'] != 'active' or datetime.fromisoformat(e['deadline']) <= now():
            return self.exam(eid)
        if answers is not None:
            if not isinstance(answers, dict) or any(k not in e['question_ids'] for k in answers):
                raise ValueError('Ungültige Klausurantworten.')
            for qid, answer in answers.items():
                grade(self.question(qid), answer)
            e['answers'].update(answers)
        if current_index is not None:
            if type(current_index) is not int or not 0 <= current_index < e['count']:
                raise ValueError('Ungültige Fragenposition.')
            e['current_index'] = current_index
        self.save_exam(e)
        return self.exam(eid)

    def submit_exam(self, eid, answers=None):
        e = self.raw_exam(eid)
        if e['status'] == 'submitted':
            return self.exam(eid)
        if answers is not None and now() < datetime.fromisoformat(e['deadline']):
            if not isinstance(answers, dict) or any(k not in e['question_ids'] for k in answers):
                raise ValueError('Ungültige Klausurantworten.')
            e['answers'].update(answers)
        # Validate every answer before writing; commit attempts and submission atomically.
        prepared = []
        for qid in e['question_ids']:
            q = self.question(qid)
            empty = [] if q['type'] in {'single_choice', 'multiple_choice', 'cloze'} else {} if q['type'] == 'matching' else ''
            answer = e['answers'].get(qid, empty)
            try:
                result = grade(q, answer)
            except ValueError:
                if now() < datetime.fromisoformat(e['deadline']):
                    raise
                answer = empty
                result = {**grade(q, answer), 'answer_note': 'Die gespeicherte Antwort hatte ein ungültiges Format und wurde bei Ablauf als unbeantwortet gewertet.'}
            prepared.append((qid, answer, result))
        results = []
        with self.db() as db:
            for qid, answer, r in prepared:
                aid, at = uuid.uuid4().hex, iso()
                rating = 4 if r['correct'] else 0
                row = db.execute('SELECT * FROM progress WHERE question_id=?', (qid,)).fetchone()
                prev = dict(row) if row else {'attempts': 0, 'correct': 0, 'incorrect': 0, 'interval': 0, 'repetitions': 0, 'ease': 2.5, 'mastery': 0}
                self.write_progress(db, qid, prev, r['score'], rating, at)
                db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)', (aid, qid, at, json.dumps(answer, ensure_ascii=False), r['score'], r['grading'], rating, json.dumps(r), json.dumps(prev), eid))
                results.append({'question_id': qid, 'answer': answer, 'attempt_id': aid, **r})
            e.update(status='submitted', submitted_at=iso(), results=results)
            db.execute('UPDATE exams SET status=?,payload=? WHERE id=?', ('submitted', json.dumps(e, ensure_ascii=False), eid))
            db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('last_module_id', json.dumps(e['module_id'])))
        return self.exam(eid)

    def grade_exam(self, eid, qid, score, rating=None):
        e = self.exam(eid)
        if e['status'] != 'submitted':
            raise ValueError('Klausur zuerst abgeben.')
        row = next((r for r in e['results'] if r['question_id'] == qid), None)
        if not row:
            raise KeyError('Frage nicht Teil der Klausur.')
        self.correct_attempt(row['attempt_id'], score, rating)
        return self.exam(eid)

    def documents(self):
        with self.db() as db:
            rows = db.execute('SELECT id,payload FROM documents ORDER BY id DESC').fetchall()
        return [{k: v for k, v in {**json.loads(r['payload']), 'id': r['id']}.items() if k not in {'text', 'proposals', 'page_texts', 'import_content'}} for r in rows]

    def document(self, did):
        with self.db() as db:
            r = db.execute('SELECT payload FROM documents WHERE id=?', (did,)).fetchone()
        if not r:
            raise KeyError('Dokument nicht gefunden.')
        return {**json.loads(r[0]), 'id': did}

    def coverage(self, mid=None, unit=None):
        with self.db() as db:
            rows = db.execute('SELECT * FROM coverage' + (' WHERE module_id=?' if mid else '') + ' ORDER BY rowid', (mid,) if mid else ()).fetchall()
        result = [{**json.loads(r['payload']), 'unit': json.loads(r['payload']).get('unit', 1), 'id': r['id'], 'module_id': r['module_id']} for r in rows]
        return [r for r in result if unit is None or r['unit'] == unit]

    def confirm_coverage(self, cid, value):
        with self.db() as db:
            row = db.execute('SELECT * FROM coverage WHERE id=?', (cid,)).fetchone()
            if not row:
                raise KeyError('Abdeckungseintrag nicht gefunden.')
            payload = {**json.loads(row['payload']), **value, 'method': 'manual'}
            if payload['coverage'] not in {'complete', 'partial', 'missing'}:
                raise ValueError('Ungültige Abdeckung.')
            # Keep original automated/assistant assessment; human review gets its own row.
            new_id = cid.rsplit(':', 1)[0] + ':manual'
            db.execute('INSERT OR REPLACE INTO coverage VALUES(?,?,?)', (new_id, row['module_id'], json.dumps(payload, ensure_ascii=False)))
        return {**payload, 'id': new_id, 'module_id': row['module_id']}

    def export(self):
        result = {'schema_version': 1, 'exported_at': iso()}
        with self.db() as db:
            for table in ('modules', 'questions', 'originals', 'progress', 'attempts', 'exams', 'documents', 'coverage', 'metadata', 'migrations'):
                result[table] = [dict(r) for r in db.execute(f'SELECT * FROM {table}')]
        return result
