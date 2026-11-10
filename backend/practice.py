"""Persisted practice rounds with immediate feedback and a shared mistakes pool."""
from __future__ import annotations

import json
import random
import uuid

from fastapi import Query

from .core import TYPES, grade, iso


PREFIX = 'practice_round:'


class Practice:
    def __init__(self, hub):
        self.hub = hub

    def mistakes(self, module_id=None, unit=None):
        if module_id:
            self.hub.module(module_id)
        clauses, args = ["q.type!='flashcard'"], []
        if module_id:
            clauses.append('q.module_id=?')
            args.append(module_id)
        if unit is not None:
            if type(unit) is not int or not 1 <= unit <= 999:
                raise ValueError('Eine positive Einheit wird benötigt.')
            clauses.append('q.unit=?')
            args.append(unit)
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        with self.hub.db() as db:
            rows = db.execute(f'''
                WITH latest AS (
                    SELECT a.*, row_number() OVER (
                        PARTITION BY question_id ORDER BY created_at DESC, rowid DESC
                    ) AS position FROM attempts a
                )
                SELECT a.* FROM latest a JOIN questions q ON q.id=a.question_id
                {where + ' AND' if where else 'WHERE'} a.position=1
                AND (a.score<0.9999 OR a.grading='keyword_hint')
                ORDER BY a.created_at DESC,a.question_id
            ''', args).fetchall()
        return [{**self.hub.question(row['question_id']),
                 'latest_attempt': {key: row[key] for key in ('id', 'score', 'grading', 'created_at')},
                 'mistake_status': 'needs_review' if row['grading'] == 'keyword_hint' else 'incorrect'}
                for row in rows]

    def create(self, config):
        if set(config) - {'module_id', 'units', 'types', 'count', 'mistakes_only', 'difficulty'}:
            raise ValueError('Unbekannte Einstellung für die Übungsrunde.')
        mid = config.get('module_id')
        if not isinstance(mid, str) or not mid.strip():
            raise ValueError('Bitte ein Studienmodul wählen.')
        self.hub.module(mid)
        count = config.get('count', 10)
        units, types = config.get('units', []), config.get('types', [])
        mistakes_only = config.get('mistakes_only', False)
        difficulty = config.get('difficulty')
        if type(count) is not int or not 1 <= count <= 200:
            raise ValueError('Eine Übungsrunde kann 1–200 Fragen enthalten.')
        if not isinstance(units, list) or any(type(unit) is not int or not 1 <= unit <= 999 for unit in units):
            raise ValueError('Einheiten müssen positive ganze Zahlen sein.')
        if not isinstance(types, list) or any(not isinstance(kind, str) or kind not in TYPES - {'flashcard'} for kind in types):
            raise ValueError('Für diese Übungsrunde werden bewertbare Fragetypen benötigt.')
        if type(mistakes_only) is not bool or (difficulty is not None and (type(difficulty) is not int or difficulty not in (1, 2, 3))):
            raise ValueError('Ungültige Einstellung für die Übungsrunde.')
        pool = self.mistakes(mid) if mistakes_only else self.hub.questions(module_id=mid)
        pool = [q for q in pool if q['type'] != 'flashcard'
                and (not units or q['unit'] in units) and (not types or q['type'] in types)
                and (difficulty is None or q['difficulty'] == difficulty)]
        if not pool:
            raise ValueError('Für diese Auswahl sind keine ' + ('Fehlerfragen' if mistakes_only else 'Übungsfragen') + ' vorhanden.')
        selected = random.sample(pool, min(count, len(pool)))
        round_id = uuid.uuid4().hex
        state = {'id': round_id, 'module_id': mid, 'status': 'active', 'created_at': iso(),
                 'question_ids': [q['id'] for q in selected], 'answers': {}, 'results': [],
                 'current_index': 0, 'count': len(selected), 'mistakes_only': mistakes_only}
        self.hub.set_meta(PREFIX + round_id, state)
        return self.public(state)

    def raw(self, round_id, db=None):
        if db is None:
            with self.hub.db() as connection:
                return self.raw(round_id, connection)
        row = db.execute('SELECT value FROM metadata WHERE key=?', (PREFIX + round_id,)).fetchone()
        if not row:
            raise KeyError('Übungsrunde nicht gefunden.')
        state = json.loads(row[0])
        if not isinstance(state, dict) or state.get('id') != round_id or not isinstance(state.get('question_ids'), list):
            raise ValueError('Die gespeicherte Übungsrunde ist beschädigt.')
        return state

    @staticmethod
    def save(db, state):
        db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',
                   (PREFIX + state['id'], json.dumps(state, ensure_ascii=False)))

    def public(self, state):
        questions = [self.hub.question(qid) for qid in state['question_ids']]
        by_id = {q['id']: q for q in questions}
        results = []
        with self.hub.db() as db:
            for saved in state['results']:
                qid = saved['question_id']
                if saved.get('unanswered'):
                    results.append({**saved, 'question': by_id[qid], 'answer': state['answers'].get(qid, ''),
                                    'attempt_id': None, 'score': 0, 'correct': False, 'grading': 'unanswered',
                                    'matched_keywords': [], 'missing_keywords': [],
                                    'answer_note': 'In dieser Runde nicht geprüft. Dafür wurde kein Lernversuch angelegt.'})
                    continue
                attempt = db.execute('SELECT * FROM attempts WHERE id=? AND question_id=?',
                                     (saved['attempt_id'], qid)).fetchone()
                if not attempt:
                    raise ValueError('Ein gespeicherter Lernversuch der Übungsrunde fehlt.')
                result = json.loads(attempt['result'])
                results.append({**result, 'question_id': qid, 'question': by_id[qid],
                                'answer': json.loads(attempt['answer']), 'attempt_id': attempt['id'],
                                'score': attempt['score'], 'grading': attempt['grading'],
                                'correct': attempt['score'] >= 0.9999, 'unanswered': False})
        score = round(sum(result['score'] for result in results), 4)
        return {**state, 'questions': questions, 'results': results, 'score': score,
                'max_score': len(questions), 'percentage': round(100 * score / max(1, len(questions))),
                'checked_count': sum(not r.get('unanswered') for r in results),
                'pending_count': sum(r['grading'] == 'keyword_hint' for r in results),
                'correct_count': sum(r['correct'] and r['grading'] != 'keyword_hint' for r in results)}

    def get(self, round_id):
        return self.public(self.raw(round_id))

    def all(self, module_id=None):
        if module_id:
            self.hub.module(module_id)
        with self.hub.db() as db:
            states = [json.loads(row[0]) for row in db.execute(
                'SELECT value FROM metadata WHERE key LIKE ? ORDER BY rowid DESC', (PREFIX + '%',))]
        return [self.public(state) for state in states if not module_id or state['module_id'] == module_id]

    def answer(self, round_id, value):
        if set(value) != {'question_id', 'answer'}:
            raise ValueError('Fragen-ID und eigene Antwort werden benötigt.')
        qid, answer = value['question_id'], value['answer']
        with self.hub.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.raw(round_id, db)
            if not isinstance(qid, str) or qid not in state['question_ids']:
                raise ValueError('Diese Frage gehört nicht zur Übungsrunde.')
            previous = next((r for r in state['results'] if r['question_id'] == qid and not r.get('unanswered')), None)
            if previous:
                if state['answers'].get(qid) != answer:
                    raise ValueError('Die Antwort ist bereits geprüft. Starte für einen neuen Versuch eine weitere Runde.')
            else:
                if state['status'] != 'active':
                    raise ValueError('Diese Übungsrunde ist bereits abgeschlossen.')
                question = self.hub.question(qid)
                result = grade(question, answer)
                aid, at = uuid.uuid4().hex, iso()
                row = db.execute('SELECT * FROM progress WHERE question_id=?', (qid,)).fetchone()
                progress = dict(row) if row else {'attempts': 0, 'correct': 0, 'incorrect': 0,
                                                 'interval': 0, 'repetitions': 0, 'ease': 2.5, 'mastery': 0}
                rating = 4 if result['correct'] and result['grading'] != 'keyword_hint' else 0
                self.hub.write_progress(db, qid, progress, result['score'], rating, at)
                db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (aid, qid, at, json.dumps(answer, ensure_ascii=False), result['score'], result['grading'],
                            rating, json.dumps(result), json.dumps(progress), None))
                db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('last_module_id', json.dumps(state['module_id'])))
                state['answers'][qid] = answer
                state['results'].append({'question_id': qid, 'attempt_id': aid})
                state['current_index'] = state['question_ids'].index(qid)
                self.save(db, state)
        return self.public(state)

    def update(self, round_id, value):
        if set(value) != {'current_index'}:
            raise ValueError('Nur die aktuelle Fragenposition kann hier gespeichert werden.')
        with self.hub.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.raw(round_id, db)
            index = value['current_index']
            if type(index) is not int or not 0 <= index < state['count']:
                raise ValueError('Ungültige Fragenposition.')
            if state['status'] == 'active':
                state['current_index'] = index
                self.save(db, state)
        return self.public(state)

    def finish(self, round_id):
        with self.hub.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.raw(round_id, db)
            if state['status'] == 'active':
                checked = {r['question_id'] for r in state['results']}
                state['results'].extend({'question_id': qid, 'unanswered': True}
                                        for qid in state['question_ids'] if qid not in checked)
                state.update(status='completed', completed_at=iso())
                self.save(db, state)
        return self.public(state)


def register_practice_routes(app, hub, lock):
    practice = Practice(hub)
    app.state.practice = practice

    @app.get('/api/mistakes')
    def mistakes(module_id: str = None, unit: int = Query(None, ge=1, le=999)):
        with lock:
            return practice.mistakes(module_id, unit)

    @app.get('/api/practice')
    def rounds(module_id: str = None):
        with lock:
            return practice.all(module_id)

    @app.post('/api/practice')
    def create(value: dict):
        with lock:
            return practice.create(value)

    @app.get('/api/practice/{round_id}')
    def get(round_id: str):
        with lock:
            return practice.get(round_id)

    @app.patch('/api/practice/{round_id}')
    def update(round_id: str, value: dict):
        with lock:
            return practice.update(round_id, value)

    @app.post('/api/practice/{round_id}/answer')
    def answer(round_id: str, value: dict):
        with lock:
            return practice.answer(round_id, value)

    @app.post('/api/practice/{round_id}/finish')
    def finish(round_id: str):
        with lock:
            return practice.finish(round_id)
