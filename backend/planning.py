"""Local course dates, personal learning blocks and an Apple Calendar export.

Course dates are a read-only, reviewed JSON seed. Only personal study blocks and
completion states are written to the Hub's existing metadata storage.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.responses import Response

from .learning_pages import resolve_study_source

TIMEZONE = 'Europe/Berlin'
BERLIN = ZoneInfo(TIMEZONE)
META_KEY = 'planning:state'
KINDS = {'deadline', 'exam', 'teaching', 'phase', 'study'}
STATUSES = {'planned', 'done'}
DEADLINE_CATEGORIES = {'submission', 'registration', 'reenrollment', 'other'}
_EVENT_FIELDS = {'id', 'module_id', 'title', 'kind', 'start', 'end', 'all_day',
                 'timezone', 'description', 'location', 'source', 'date_note', 'status', 'calendar_uid', 'category'}
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
_DATETIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z')
_CALENDAR_UID = re.compile(r'[^\s\x00-\x1f\x7f\\;,]{1,255}\Z')


def _text(value, field, required=True, limit=20000):
    if (not isinstance(value, str) or (required and not value.strip()) or len(value) > limit
            or any((ord(character) < 32 and character not in '\t\r\n') or ord(character) == 127 for character in value)):
        raise ValueError(f'{field}: gültiger Text wird benötigt.')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError(f'{field}: gültiger UTF-8-Text wird benötigt.')
    return value.strip()


def _moment(value, all_day, field):
    try:
        if not isinstance(value, str):
            raise ValueError()
        if all_day:
            if not _DATE.fullmatch(value):
                raise ValueError()
            return date.fromisoformat(value)
        if not _DATETIME.fullmatch(value):
            raise ValueError()
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.microsecond:
            raise ValueError()
        return parsed.astimezone(BERLIN)
    except (ValueError, OverflowError):
        expected = 'YYYY-MM-DD' if all_day else 'ISO-Datum und Uhrzeit mit Zeitzonenoffset (z. B. +02:00)'
        raise ValueError(f'{field}: {expected} wird benötigt; Sekundenbruchteile sind nicht erlaubt.')


def _validated_calendar_uid(value):
    # UID is emitted as an RFC 5545 TEXT value. Reject controls, whitespace and
    # characters requiring escaping so the original identity is kept verbatim.
    if (not isinstance(value, str) or not _CALENDAR_UID.fullmatch(value)
            or len(value.encode('utf-8')) > 255):
        raise ValueError('calendar_uid: Gültige Kalender-ID ohne Leer- oder Steuerzeichen wird benötigt.')
    return value


def _calendar_uid(event):
    if 'calendar_uid' in event:
        return _validated_calendar_uid(event['calendar_uid'])
    return hashlib.sha256(event['id'].encode('utf-8')).hexdigest() + '@master-learning-hub.local'


def _source_reference(value, source_root, project_root):
    if not isinstance(value, dict):
        raise ValueError('source: Quellnachweis muss ein Objekt sein.')
    relative = _text(value.get('path'), 'source.path')
    requested = Path(relative)
    if (requested.is_absolute() or '..' in requested.parts or '\\' in relative
            or any(part.startswith('.') for part in requested.parts)):
        raise ValueError('source.path: Nur Dateien innerhalb der Studienunterlagen sind erlaubt.')
    try:
        # Use the exact confinement policy of the original-source endpoint,
        # including lexical app paths and non-hidden private runtime folders.
        resolved = resolve_study_source(source_root, project_root, relative)
        if any(part.startswith('.') for part in resolved.relative_to(Path(source_root).resolve()).parts):
            raise ValueError()
    except (ValueError, OSError, RuntimeError):
        raise ValueError('source.path: Vorhandene Studienquelle außerhalb interner oder externer Ordner wird benötigt.')
    kinds = {'.pdf': 'pdf', '.ics': 'ics', '.png': 'image', '.jpg': 'image', '.jpeg': 'image'}
    if requested.suffix.lower() not in kinds or resolved.suffix.lower() != requested.suffix.lower() or not resolved.is_file():
        raise ValueError('source.path: Vorhandene PDF-, ICS- oder Bildquelle wird benötigt.')
    kind = value.get('kind', kinds[resolved.suffix.lower()])
    if not isinstance(kind, str) or kind != kinds[resolved.suffix.lower()]:
        raise ValueError('source.kind: Quelltyp und Dateiendung müssen übereinstimmen.')
    result = {'path': requested.as_posix(), 'title': _text(value.get('title'), 'source.title'), 'kind': kind}
    for field in ('chapter', 'source_kind'):
        if field in value:
            result[field] = _text(value[field], f'source.{field}')
    for field in ('pdf_page', 'pdf_page_end'):
        if field in value:
            if kind != 'pdf' or type(value[field]) is not int or value[field] < 1:
                raise ValueError(f'source.{field}: Positive PDF-Seite wird benötigt.')
            result[field] = value[field]
    if 'pdf_page_end' in result and result['pdf_page_end'] < result.get('pdf_page', 1):
        raise ValueError('source.pdf_page_end: Endseite darf nicht vor der Startseite liegen.')
    return result


def validate_event(value, hub, source_root, project_root, personal=False):
    """Validate an event without changing any database record or course date."""
    if not isinstance(value, dict) or set(value) - _EVENT_FIELDS:
        raise ValueError('Termin enthält unbekannte Felder oder ist kein Objekt.')
    event_id = value.get('id')
    if not isinstance(event_id, str) or not _ID.fullmatch(event_id):
        raise ValueError('id: Gültige Termin-ID wird benötigt.')
    kind = value.get('kind', 'study' if personal else None)
    if not isinstance(kind, str) or kind not in KINDS or (personal and kind not in {'study', 'deadline'}):
        raise ValueError('kind: Eigene Termine sind Lernblöcke oder Fristen.')
    deadline = personal and kind == 'deadline'
    mid = value.get('module_id')
    if mid is not None or not deadline:
        mid = _text(mid, 'module_id', limit=160)
        hub.module(mid)  # Preserve the normal 404 response for unknown modules.
    category = value.get('category')
    if ('category' in value or deadline) and (
            kind != 'deadline' or not isinstance(category, str) or category not in DEADLINE_CATEGORIES):
        raise ValueError('Bitte wähle eine gültige Fristart.')
    all_day = value.get('all_day')
    if type(all_day) is not bool or (personal and kind == 'study' and all_day):
        raise ValueError('all_day: Eigene Lernblöcke benötigen eine konkrete Uhrzeit.')
    if value.get('timezone', TIMEZONE) != TIMEZONE:
        raise ValueError('timezone: Die Planung verwendet Europe/Berlin.')
    start = _moment(value.get('start'), all_day, 'start')
    end = _moment(value['end'], all_day, 'end') if value.get('end') is not None else None
    if personal and kind == 'study' and end is None:
        raise ValueError('end: Eigene Lernblöcke benötigen eine Endzeit.')
    # Compare absolute instants during the repeated hour at the end of DST.
    later = (end.astimezone(timezone.utc) > start.astimezone(timezone.utc)
             if end is not None and not all_day else end > start if end is not None else True)
    if not later:
        raise ValueError('end: Endzeit muss nach dem Beginn liegen; ganztägige Enddaten sind exklusiv.')
    status = value.get('status', 'planned')
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError('status: Nur planned oder done sind erlaubt.')
    result = {'id': event_id, 'module_id': mid, 'title': _text(value.get('title'), 'title', limit=2000),
              'kind': kind, 'start': start.isoformat(), 'all_day': all_day,
              'timezone': TIMEZONE, 'description': _text(value.get('description', ''), 'description', required=False),
              'status': status}
    if category is not None:
        result['category'] = category
    if end is not None:
        result['end'] = end.isoformat()
    if 'calendar_uid' in value:
        if personal:
            raise ValueError('calendar_uid: Eigene Lernblöcke dürfen keine Quellidentität setzen.')
        result['calendar_uid'] = _validated_calendar_uid(value['calendar_uid'])
    for field in ('location', 'date_note'):
        if field in value:
            result[field] = _text(value[field], field, required=False)
    if 'source' in value:
        if personal:
            raise ValueError('source: Eigene Lernblöcke erhalten keinen amtlichen Quellnachweis.')
        result['source'] = _source_reference(value['source'], source_root, project_root)
    return result


def _load_state(hub):
    state = hub.get_meta(META_KEY) or {'events': {}, 'statuses': {}}
    if (not isinstance(state, dict) or not isinstance(state.get('events'), dict)
            or not isinstance(state.get('statuses'), dict)):
        raise ValueError('Die gespeicherte persönliche Planung ist beschädigt.')
    return state


def load_planning(hub, project_root, source_root):
    seed_path = Path(project_root) / 'planning' / 'study-events.json'
    notes, raw_events = [], []
    if seed_path.exists():
        try:
            seed = json.loads(seed_path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            raise ValueError('Die lokale Termindatei kann nicht gelesen werden.')
        if (not isinstance(seed, dict) or type(seed.get('schema_version')) is not int
                or seed['schema_version'] != 1 or not isinstance(seed.get('events'), list)
                or not isinstance(seed.get('notes', []), list)):
            raise ValueError('Die lokale Termindatei benötigt schema_version 1, events und notes als Listen.')
        raw_events = seed['events']
        notes = [_text(note, 'notes') for note in seed.get('notes', [])]
    state = _load_state(hub)
    events, seen = [], set()
    for raw in raw_events:
        event = validate_event(raw, hub, source_root, project_root)
        if event['id'] in seen:
            raise ValueError('Doppelte Termin-ID in der lokalen Termindatei.')
        seen.add(event['id'])
        events.append(event)
    for event_id, raw in state['events'].items():
        event = validate_event(raw, hub, source_root, project_root, personal=True)
        if event['id'] != event_id or event_id in seen:
            raise ValueError('Doppelte oder widersprüchliche Termin-ID in der persönlichen Planung.')
        seen.add(event_id)
        events.append(event)
    calendar_uids = set()
    for event in events:
        uid = _calendar_uid(event)
        if uid in calendar_uids:
            raise ValueError('Doppelte Kalender-ID in der Planung.')
        calendar_uids.add(uid)
        status = state['statuses'].get(event['id'], event['status'])
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError('Ungültiger gespeicherter Terminstatus.')
        event['status'] = status
    events.sort(key=lambda event: (event['start'][:10], 0 if event['all_day'] else 1,
                                   _moment(event['start'], False, 'start').timestamp() if not event['all_day'] else 0,
                                   event['id']))
    return {'events': events, 'timezone': TIMEZONE,
            'today': datetime.now(BERLIN).date().isoformat(), 'notes': notes}


def _ics_text(value):
    return str(value).replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def _fold_line(line):
    """Fold at 75 UTF-8 octets including continuation whitespace (RFC 5545)."""
    parts, current, size = [], '', 0
    for character in line:
        width = len(character.encode('utf-8'))
        if size + width > 75:
            parts.append(current)
            current, size = ' ', 1
        current += character
        size += width
    parts.append(current)
    return '\r\n'.join(parts)


def calendar_ics(events, generated_at=None):
    """Export actual instants as UTC, avoiding ambiguous local fall-back times.

    X-WR-TIMEZONE and VTIMEZONE retain the intended Apple Calendar display zone.
    All-day dates use RFC 5545's exclusive DTEND. No end is invented for a timed
    course date when the reviewed source does not give a duration.
    """
    stamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Master Learning Hub//Studienplanung//DE',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:Studienplanung',
             'X-WR-TIMEZONE:' + TIMEZONE,
             'BEGIN:VTIMEZONE', 'TZID:' + TIMEZONE, 'X-LIC-LOCATION:' + TIMEZONE,
             'BEGIN:DAYLIGHT', 'DTSTART:19960331T020000', 'TZOFFSETFROM:+0100',
             'TZOFFSETTO:+0200', 'TZNAME:CEST', 'RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU',
             'END:DAYLIGHT', 'BEGIN:STANDARD', 'DTSTART:19961027T030000',
             'TZOFFSETFROM:+0200', 'TZOFFSETTO:+0100', 'TZNAME:CET',
             'RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU', 'END:STANDARD', 'END:VTIMEZONE']
    for event in events:
        identity = _calendar_uid(event)
        lines.extend(['BEGIN:VEVENT', 'UID:' + identity, 'DTSTAMP:' + stamp])
        for field, name in (('start', 'DTSTART'), ('end', 'DTEND')):
            if field not in event:
                continue
            moment = _moment(event[field], event['all_day'], field)
            lines.append(name + (';VALUE=DATE:' + moment.strftime('%Y%m%d') if event['all_day']
                                 else ':' + moment.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
        lines.append('SUMMARY:' + _ics_text(event['title']))
        description = event.get('description', '')
        if event.get('date_note'):
            description += ('\n\n' if description else '') + event['date_note']
        if event.get('source'):
            ref = event['source']
            source = 'Quelle: ' + ref['title']
            if ref.get('pdf_page'):
                source += ', PDF-Seite ' + str(ref['pdf_page'])
            description += ('\n\n' if description else '') + source
        if description:
            lines.append('DESCRIPTION:' + _ics_text(description))
        if event.get('location'):
            lines.append('LOCATION:' + _ics_text(event['location']))
        lines.extend(['CATEGORIES:' + _ics_text(event['kind']), 'X-MLH-STUDY-STATUS:' + event['status'].upper(),
                      'END:VEVENT'])
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(_fold_line(line) for line in lines) + '\r\n').encode('utf-8')


def register_planning_routes(app, hub, project_root, source_root):
    """Register before the frontend's catch-all mount; reuse its write lock."""
    def selected(module_id=None, event_id=None):
        if module_id is not None:
            hub.module(module_id)
        result = load_planning(hub, project_root, source_root)
        result['events'] = [event for event in result['events']
                            if (module_id is None or event['module_id'] == module_id)
                            and (event_id is None or event['id'] == event_id)]
        if event_id is not None and not result['events']:
            raise HTTPException(404, 'Termin nicht gefunden.')
        return result

    @app.get('/api/planning')
    def planning(module_id: Optional[str] = None):
        with app.state.lock:
            return selected(module_id)

    @app.post('/api/planning/events', status_code=201)
    def create_study_event(value: dict):
        allowed = {'module_id', 'title', 'kind', 'start', 'end', 'all_day', 'timezone', 'description', 'location'}
        if set(value) - allowed:
            raise ValueError('Eigene Lernblöcke enthalten unbekannte oder geschützte Felder.')
        if value.get('kind', 'study') != 'study':
            raise ValueError('Eigene Lernblöcke benötigen den Typ study.')
        with app.state.lock:
            event = validate_event({**value, 'id': 'study-' + uuid.uuid4().hex}, hub, source_root, project_root, personal=True)
            # Validate the seed too, so a corrupt source cannot produce a hidden block.
            selected()
            state = _load_state(hub)
            state['events'][event['id']] = event
            hub.set_meta(META_KEY, state)
            return event

    def save_deadline(value, event_id=None):
        allowed = {'module_id', 'title', 'start', 'all_day', 'description', 'category'}
        if set(value) - allowed:
            raise ValueError('Eigene Fristen enthalten unbekannte oder geschützte Felder.')
        with app.state.lock:
            selected()
            state = _load_state(hub)
            if event_id is None:
                event_id = 'deadline-' + uuid.uuid4().hex
            elif state['events'].get(event_id, {}).get('kind') != 'deadline':
                raise HTTPException(404, 'Eigene Frist nicht gefunden.')
            event = validate_event({**value, 'id': event_id, 'kind': 'deadline'},
                                   hub, source_root, project_root, personal=True)
            state['events'][event_id] = event
            hub.set_meta(META_KEY, state)
            return {**event, 'status': state['statuses'].get(event_id, 'planned')}

    @app.post('/api/planning/deadlines', status_code=201)
    def create_deadline(value: dict):
        return save_deadline(value)

    @app.put('/api/planning/deadlines/{event_id}')
    def update_deadline(event_id: str, value: dict):
        return save_deadline(value, event_id)

    @app.delete('/api/planning/deadlines/{event_id}', status_code=204)
    def delete_deadline(event_id: str):
        with app.state.lock:
            state = _load_state(hub)
            if state['events'].get(event_id, {}).get('kind') != 'deadline':
                raise HTTPException(404, 'Eigene Frist nicht gefunden.')
            del state['events'][event_id]
            state['statuses'].pop(event_id, None)
            hub.set_meta(META_KEY, state)
        return Response(status_code=204)

    @app.patch('/api/planning/events/{event_id}')
    def mark_study_event(event_id: str, value: dict):
        if set(value) != {'status'} or not isinstance(value.get('status'), str) or value['status'] not in STATUSES:
            raise ValueError('Nur der Terminstatus planned oder done kann geändert werden.')
        with app.state.lock:
            event = selected(event_id=event_id)['events'][0]
            state = _load_state(hub)
            if state['statuses'].get(event_id) != value['status']:
                state['statuses'][event_id] = value['status']
                hub.set_meta(META_KEY, state)
            return {**event, 'status': value['status']}

    @app.get('/api/planning/calendar.ics')
    def export_calendar(module_id: Optional[str] = None, event_id: Optional[str] = None):
        with app.state.lock:
            content = calendar_ics(selected(module_id, event_id)['events'])
        return Response(content, media_type='text/calendar; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="studienplanung.ics"'})
