"""Persistent, auditable self-assessment. Model prose never changes mastery."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

LABELS = {'open': 'Offen', 'treated': 'Behandelt', 'helped': 'Mit Hilfe gelöst', 'independent': 'Selbstständig gezeigt', 'confirmed': 'Nach Abstand bestätigt', 'unclear': 'Bewertung offen'}

class LearningMemory:
    def __init__(self, hub, project):
        self.hub = hub
        path = project / 'content/tutor/goals.json'
        self.goals = json.loads(path.read_text()) if path.exists() else []
        with hub.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tutor_learning_events (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, created_at TEXT NOT NULL, outcome TEXT NOT NULL, answer TEXT NOT NULL, note TEXT NOT NULL, snapshot TEXT NOT NULL, voided INTEGER NOT NULL DEFAULT 0)')

    def goal(self, id, module_id):
        for goal in self.goals:
            if goal['id'] == id and goal['module_id'] == module_id:
                return goal
        raise ValueError('Lernziel gehört nicht zum ausgewählten Modul.')

    def state(self, goal, at=None):
        at = at or datetime.now(timezone.utc)
        with self.hub.db() as db:
            events = [dict(r) for r in db.execute('SELECT * FROM tutor_learning_events WHERE goal_id=? ORDER BY created_at,id', (goal['id'],))]
        status, due, last_success, interval = 'open', None, None, 0
        for event in events:
            if event['voided']: continue
            when = datetime.fromisoformat(event['created_at'])
            outcome = event['outcome']
            if outcome == 'independent':
                if last_success and when >= last_success + timedelta(days=1):
                    status = 'confirmed'; interval = 6 if interval <= 1 else min(180, interval * 2)
                    last_success = when; due = when + timedelta(days=interval)
                elif last_success is None:
                    status = 'independent'; interval = 1; last_success = when; due = when + timedelta(days=1)
                # Repeating the same day neither promotes nor postpones a review.
            else:
                status = {'treated': 'treated', 'helped': 'helped', 'incorrect': 'treated', 'unclear': 'unclear'}[outcome]
                last_success = None; interval = 0
                due = when + (timedelta(minutes=10) if outcome in ('helped','incorrect') else timedelta(days=1))
        return {**goal, 'status': status, 'label': LABELS[status], 'next_due': due.isoformat() if due else None, 'due': bool(due and due <= at), 'events': [{**e, 'snapshot': json.loads(e['snapshot'])} for e in events]}

    def overview(self, module_id):
        goals = [self.state(g) for g in self.goals if g['module_id'] == module_id]
        next_goal = next((g for g in goals if g['due']), None) or next((g for g in goals if g['status'] not in ('independent','confirmed')), None)
        return {'goals': goals, 'next_goal_id': next_goal['id'] if next_goal else None, 'due_count': sum(g['due'] for g in goals), 'coverage': (f'{len(goals)} Lernziele sind für dieses Modul erfasst. Andere Themen sind noch nicht erfasst.' if goals
                             else 'Für dieses Modul sind noch keine Lernziele erfasst.')}

    def record(self, value, at=None):
        goal = self.goal(value.get('goal_id'), value.get('module_id'))
        id = value.get('id')
        try: uuid.UUID(id)
        except (ValueError, TypeError, AttributeError): raise ValueError('Gültige Versuch-ID erforderlich.')
        outcome = value.get('outcome')
        if outcome not in ('treated','helped','independent','incorrect','unclear'): raise ValueError('Ungültige Bewertung.')
        answer, note = value.get('answer', ''), value.get('note','')
        if not isinstance(answer,str) or len(answer)>12000 or not isinstance(note,str) or len(note)>2000: raise ValueError('Antwort oder Notiz zu lang.')
        if outcome != 'treated' and not answer.strip(): raise ValueError('Bitte zuerst deine eigene Antwort festhalten.')
        if outcome == 'independent' and value.get('without_help') is not True: raise ValueError('Ohne inhaltliche Hilfe beantwortet muss bestätigt sein.')
        with self.hub.db() as db:
            old = db.execute('SELECT * FROM tutor_learning_events WHERE id=?',(id,)).fetchone()
            if old:
                if (old['goal_id'],old['outcome'],old['answer'],old['note']) != (goal['id'],outcome,answer,note): raise ValueError('Versuch-ID bereits verwendet.')
            else:
                db.execute('INSERT INTO tutor_learning_events VALUES(?,?,?,?,?,?,?,0)',(id,goal['id'],(at or datetime.now(timezone.utc)).isoformat(),outcome,answer,note,json.dumps({**goal,'assessment':'Selbsteinschätzung anhand Antwortkriterien'},ensure_ascii=False)))
        return self.overview(goal['module_id'])

    def undo(self, module_id, goal_id, event_id):
        self.goal(goal_id,module_id)
        with self.hub.db() as db:
            result = db.execute('UPDATE tutor_learning_events SET voided=1 WHERE id=? AND goal_id=?',(event_id,goal_id))
            if not result.rowcount: raise ValueError('Versuch nicht gefunden.')
        return self.overview(module_id)


def register_memory_routes(app, hub, project):
    memory = LearningMemory(hub,project); app.state.learning_memory = memory
    @app.get('/api/tutor/learning-memory')
    def overview(module_id: str):
        return memory.overview(module_id)
    @app.post('/api/tutor/learning-memory')
    def record(value: dict):
        try: return memory.record(value)
        except ValueError as exc: raise HTTPException(400,str(exc))
    @app.post('/api/tutor/learning-memory/undo')
    def undo(value: dict):
        try: return memory.undo(value.get('module_id'),value.get('goal_id'),value.get('event_id'))
        except ValueError as exc: raise HTTPException(400,str(exc))
