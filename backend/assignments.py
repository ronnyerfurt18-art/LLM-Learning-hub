"""Read-only practice copies of prepared assignments (content/assignments/*.json)."""
from __future__ import annotations

import json
import math
import re
import string
from datetime import date
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .learning_pages import resolve_study_source


@lru_cache(maxsize=64)
def _pdf_pages(path, modified, size):
    # File identity in the cache key keeps corrected/replaced PDFs current.
    return len(PdfReader(path).pages)


_ID = re.compile(r'[a-z0-9][a-z0-9-]{1,39}')


def assignment_rules(content):
    """Optional fixed shape of one assignment: question_count, option_count, min_true, points."""
    rules = content.get('rules') if isinstance(content, dict) and isinstance(content.get('rules'), dict) else {}
    return {key: rules[key] for key in ('question_count', 'option_count', 'min_true', 'points') if key in rules}


def validate_assignment(content, source_root, project_root):
    errors = []

    def fail(where, message):
        errors.append(f'{where}: {message}')

    def text(value, where):
        if not isinstance(value, str) or not value.strip():
            fail(where, 'Nicht leerer Text benötigt.')

    def reference(ref, where):
        if not isinstance(ref, dict):
            fail(where, 'Konkreter PDF-Nachweis benötigt.')
            return 0
        text(ref.get('title'), where + '.title')
        if ref.get('kind') == 'video':
            try:
                path = resolve_study_source(source_root, project_root, ref.get('path'))
                if path.suffix.lower() != '.mp4':
                    raise ValueError('Videobeleg muss eine MP4-Datei sein.')
                start = ref.get('timestamp_seconds')
                end = ref.get('timestamp_end_seconds', start)
                if any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, end)) or not 0 <= start <= end:
                    raise ValueError('Gültige Videozeitmarke benötigt.')
            except (ValueError, OSError, RuntimeError) as exc:
                fail(where, str(exc))
            return 0
        if ref.get('kind', 'pdf') != 'pdf':
            fail(where, 'PDF- oder Videonachweis benötigt.')
        page = ref.get('pdf_page')
        end = ref.get('pdf_page_end', page)
        if type(page) is not int or page < 1 or type(end) is not int or end < page:
            fail(where, 'Gültige PDF-Seiten ab 1 benötigt.')
        try:
            path = resolve_study_source(source_root, project_root, ref.get('path'))
            if path.suffix.lower() != '.pdf':
                raise ValueError('Nachlesestelle muss eine PDF-Datei sein.')
            stat = path.stat()
            count = _pdf_pages(str(path), stat.st_mtime_ns, stat.st_size)
            if type(end) is int and end > count:
                fail(where, f'PDF hat nur {count} Seiten.')
            return count
        except (ValueError, OSError, RuntimeError, PyPdfError) as exc:
            fail(where, str(exc))
            return 0

    if not isinstance(content, dict):
        return ['Einsendearbeit muss ein JSON-Objekt sein.']
    if not isinstance(content.get('id'), str) or not _ID.fullmatch(content['id']):
        fail('id', 'Eindeutige Einsendearbeit-ID benötigt (Kleinbuchstaben, Ziffern, Bindestriche).')
    if not isinstance(content.get('module_number'), str) or not content['module_number'].strip():
        fail('module_number', 'Modulnummer des zugehörigen Moduls benötigt.')
    rules = assignment_rules(content)
    for key, low, high in (('question_count', 1, 200), ('option_count', 2, 8), ('min_true', 0, 8)):
        if key in rules and (type(rules[key]) is not int or not low <= rules[key] <= high):
            fail('rules.' + key, f'Ganze Zahl zwischen {low} und {high} benötigt.')
            rules.pop(key)
    points = rules.get('points')
    if points is not None and (not isinstance(points, list) or len(points) != rules.get('option_count', -1) + 1
                               or any(type(value) is not int or not 0 <= value <= 100 for value in points)):
        fail('rules.points', 'Punkte je Anzahl korrekter Aussagen benötigt (option_count + 1 Werte von 0 bis 100).')
    for key in ('title', 'solution_note'):
        text(content.get(key), key)
    try:
        date.fromisoformat(content.get('due_date', ''))
    except (TypeError, ValueError):
        fail('due_date', 'Gültiges Datum benötigt.')
    original_pages = reference(content.get('source'), 'source')
    questions = content.get('questions')
    wanted = rules.get('question_count')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 200 or (wanted and len(questions) != wanted):
        return errors + [f'questions: Genau {wanted} Originalfragen benötigt.' if wanted else 'questions: 1 bis 200 Originalfragen benötigt.']
    option_count, min_true = rules.get('option_count'), rules.get('min_true', 0)
    ids = set()
    for i, question in enumerate(questions, 1):
        where = f'Frage {i}'
        if not isinstance(question, dict):
            fail(where, 'Frage muss ein Objekt sein.')
            continue
        qid = question.get('id')
        if not isinstance(qid, str) or not qid.startswith(str(content.get('id')) + '-q') or qid in ids:
            fail(where, 'Eindeutige Frage-ID benötigt.')
        if isinstance(qid, str):
            ids.add(qid)
        if type(question.get('number')) is not int or question['number'] != i:
            fail(where, 'Fortlaufende Originalnummer benötigt.')
        for key in ('title', 'prompt'):
            text(question.get(key), f'{where}.{key}')
        page = question.get('source_page')
        if type(page) is not int or not 1 <= page <= original_pages:
            fail(where, 'Gültige Seite der Originalaufgabe benötigt.')
        options = question.get('options')
        if not isinstance(options, list) or not 2 <= len(options) <= 8 or (option_count and len(options) != option_count):
            fail(where, f'Genau {option_count} Originalaussagen benötigt.' if option_count else 'Zwei bis acht Originalaussagen benötigt.')
            continue
        for letter, option in zip(string.ascii_uppercase, options):
            label = f'{where}, Aussage {letter}'
            if not isinstance(option, dict):
                fail(label, 'Aussage muss ein Objekt sein.')
                continue
            if option.get('id') != letter:
                fail(label, 'Fortlaufender Originalbuchstabe ab A benötigt.')
            for key in ('text', 'explanation'):
                text(option.get(key), f'{label}.{key}')
            if type(option.get('is_correct')) is not bool:
                fail(label, 'Explizite Wahr/Falsch-Einordnung benötigt.')
            sources = option.get('sources')
            if not isinstance(sources, list) or not sources:
                fail(label, 'Mindestens eine Nachlesestelle benötigt.')
            else:
                for n, ref in enumerate(sources, 1):
                    reference(ref, f'{label}, Quelle {n}')
                    if isinstance(ref, dict) and isinstance(content.get('source'), dict) and ref.get('path') == content['source'].get('path'):
                        fail(label, 'Theoriebeleg muss über die Originalaufgabe hinausführen.')
        if sum(isinstance(option, dict) and option.get('is_correct') is True for option in options) < min_true:
            fail(where, f'Laut Vorgabe sind mindestens {min_true} Aussagen wahr.' if min_true != 1 else 'Laut Original ist mindestens eine Aussage wahr.')
    return errors


def _directory(project_root):
    project = Path(project_root).resolve()
    directory = project / 'content' / 'assignments'
    if not directory.resolve().is_relative_to(project):
        raise ValueError('Einsendearbeiten liegen außerhalb der Anwendung.')
    return directory


def assignment_module_numbers(project_root):
    """Module numbers that have prepared assignment files; unreadable files count as none."""
    numbers = set()
    directory = _directory(project_root)
    for path in sorted(directory.glob('*.json')) if directory.is_dir() else []:
        try:
            content = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(content, dict) and isinstance(content.get('module_number'), str):
            numbers.add(content['module_number'].strip())
    return numbers - {''}


def load_assignments(project_root, source_root, module_number=None):
    """All prepared assignments in file-name order, optionally of one module only."""
    project = Path(project_root).resolve()
    directory = _directory(project)
    assignments, ids = [], set()
    for path in sorted(directory.glob('*.json')) if directory.is_dir() else []:
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Einsendearbeit liegt außerhalb des Inhaltsverzeichnisses.')
        try:
            content = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise ValueError(f'Einsendearbeit {path.name} kann nicht geladen werden: {exc}') from exc
        if module_number is not None and isinstance(content, dict) and content.get('module_number') != module_number:
            continue
        errors = validate_assignment(content, source_root, project)
        if isinstance(content, dict) and content.get('id') in ids:
            errors.append('Die ID wird bereits von einer anderen Einsendearbeit verwendet.')
        if errors:
            raise ValueError(f'Einsendearbeit {path.name}: ' + '; '.join(errors[:20]))
        ids.add(content['id'])
        assignments.append(content)
    return assignments


def assignments_for_module(module, project_root, source_root):
    """Prepared assignments of one module; modules without prepared files have none."""
    number = str(module.get('number') or '').strip()
    return load_assignments(project_root, source_root, module_number=number) if number else []


def _pages(ref):
    start = ref.get('pdf_page')
    return (start, ref.get('pdf_page_end', start)) if type(start) is int else None


def assignment_overview(assignment, lessons=(), with_statements=False):
    """Planner text for one assignment: questions, reading places and matching learning pages.

    Truth values and explanations stay out on purpose: a study plan needs the
    topics, and the practice tab must remain a real self-test.
    """
    due = date.fromisoformat(assignment['due_date']).strftime('%d.%m.%Y')
    lines = [f"{assignment['title']} · Abgabe {due} · {len(assignment['questions'])} Fragen mit Wahr/Falsch-Aussagen"]
    for question in assignment['questions']:
        places, matched = {}, {}
        for option in question['options']:
            for ref in option['sources']:
                pages = _pages(ref)
                if ref.get('kind') == 'video' or not pages:
                    places.setdefault(ref['title'], {}).setdefault(ref.get('chapter') or 'Video', set())
                    continue
                places.setdefault(ref['title'], {}).setdefault(ref.get('chapter') or 'ohne Kapitelangabe', set()).update(pages)
                for lesson in lessons:
                    for section in lesson.get('sections', []):
                        for source in section.get('sources', []):
                            other = _pages(source)
                            if other and source.get('path') == ref['path'] and other[0] <= pages[1] and pages[0] <= other[1]:
                                matched.setdefault(lesson['id'], lesson)
        lines.append(f"Frage {question['number']}: {question['title']}")
        for title, chapters in places.items():
            parts = []
            for chapter, pages in chapters.items():
                span = ''
                if pages:
                    low, high = min(pages), max(pages)
                    span = f' (PDF-S. {low})' if low == high else f' (PDF-S. {low}–{high})'
                parts.append(chapter + span)
            lines.append(f'  Nachlesen in {title}: ' + '; '.join(parts))
        if matched:
            lines.append('  Passende Lernseiten: ' + '; '.join(
                f"„{lesson['title']}“ (Einheit {lesson['unit']}" + (f", {lesson['status_label']}" if lesson.get('status_label') else '') + ')'
                for lesson in list(matched.values())[:4]))
        else:
            lines.append('  Passende Lernseiten: keine im Hub – direkt die Nachlesestellen verwenden.')
        if with_statements:
            lines.extend(f"  Aussage {option['id']}: {option['text']}" for option in question['options'])
    return '\n'.join(lines)
