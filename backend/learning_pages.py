"""Read-only local learning pages with concrete, confined study references."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path


SOURCE_MEDIA_TYPES = {
    '.pdf': 'application/pdf',
    '.mp4': 'video/mp4',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xlsm': 'application/vnd.ms-excel.sheet.macroEnabled.12',
    '.doc': 'application/msword', '.ppt': 'application/vnd.ms-powerpoint',
    '.xls': 'application/vnd.ms-excel', '.odt': 'application/vnd.oasis.opendocument.text',
    '.odp': 'application/vnd.oasis.opendocument.presentation',
    '.ods': 'application/vnd.oasis.opendocument.spreadsheet', '.rtf': 'application/rtf',
    '.txt': 'text/plain', '.md': 'text/markdown', '.markdown': 'text/markdown',
    '.csv': 'text/csv', '.tsv': 'text/tab-separated-values',
    '.ics': 'text/calendar', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
}
BIG_PICTURE_NODES = (3, 7)
_PRIVATE_COMPONENTS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.agents', '.codex', '.aws'}


class SourceAccessError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_study_source(source_root, project_root, relative):
    """Resolve an original without exposing application data or external symlinks."""
    if not isinstance(relative, str) or not relative.strip() or '\x00' in relative:
        raise SourceAccessError(403, 'Ein relativer Studienpfad wird benötigt.')
    requested = Path(relative)
    if requested.is_absolute() or '..' in requested.parts or any(part in _PRIVATE_COMPONENTS for part in requested.parts):
        raise SourceAccessError(403, 'Quelldatei liegt außerhalb der erlaubten Studienunterlagen.')
    source, project = Path(source_root).resolve(), Path(project_root).resolve()
    lexical = source / requested
    if _within(lexical, project):
        raise SourceAccessError(403, 'Interne Anwendungsdateien sind keine Studienquellen.')
    try:
        path = lexical.resolve()
    except (OSError, RuntimeError):
        raise SourceAccessError(403, 'Quelldatei kann nicht sicher aufgelöst werden.')
    if not _within(path, source) or _within(path, project):
        raise SourceAccessError(403, 'Quelldatei liegt außerhalb der erlaubten Studienunterlagen.')
    if any(part in _PRIVATE_COMPONENTS for part in path.relative_to(source).parts):
        raise SourceAccessError(403, 'Interne Anwendungsdateien sind keine Studienquellen.')
    if path.is_dir():
        raise SourceAccessError(403, 'Einzelne Quelldatei benötigt; Verzeichnisse sind nicht erlaubt.')
    if path.suffix.lower() not in SOURCE_MEDIA_TYPES:
        raise SourceAccessError(403, 'Dieser Dateityp ist nicht als Studienquelle erlaubt.')
    if not path.is_file():
        raise SourceAccessError(404, 'Quelldatei nicht vorhanden.')
    return path


def validate_learning_page(content, source_root, project_root):
    """Validate the page contract and every reference; report readable errors."""
    errors = []

    def fail(where, message):
        errors.append(f'{where}: {message}')

    def text(value, where):
        if not isinstance(value, str) or not value.strip():
            fail(where, 'nicht leerer Text benötigt.')

    def texts(value, where, nonempty=True):
        if not isinstance(value, list) or (nonempty and not value):
            fail(where, 'Textliste benötigt' + (' (nicht leer).' if nonempty else '.'))
            return
        for i, item in enumerate(value):
            text(item, f'{where}[{i}]')

    def positive(value, where):
        if type(value) is not int or value < 1:
            fail(where, 'positive ganze Zahl benötigt.')

    def seconds(value, where):
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid:
            fail(where, 'endliche Zeitmarke in Sekunden ab 0 benötigt.')
        return valid

    def sources(value, where):
        if not isinstance(value, list) or not value:
            fail(where, 'mindestens ein konkreter Quellnachweis benötigt.')
            return
        for i, ref in enumerate(value):
            label = f'{where}[{i}]'
            if not isinstance(ref, dict):
                fail(label, 'Quellnachweis muss ein Objekt sein.')
                continue
            for field in ('path', 'title'):
                text(ref.get(field), f'{label}.{field}')
            kind = ref.get('kind', 'pdf')
            if kind == 'video':
                start_valid = seconds(ref.get('timestamp_seconds'), f'{label}.timestamp_seconds')
                if 'timestamp_end_seconds' in ref:
                    end_valid = seconds(ref['timestamp_end_seconds'], f'{label}.timestamp_end_seconds')
                    if start_valid and end_valid and ref['timestamp_end_seconds'] < ref['timestamp_seconds']:
                        fail(label, 'Endzeit darf nicht vor der Startzeit liegen.')
                if any(field in ref for field in ('pdf_page', 'pdf_page_end', 'printed_page')):
                    fail(label, 'Videobelege verwenden Zeitmarken, keine PDF-Seiten.')
            else:
                if kind != 'pdf':
                    fail(f'{label}.kind', 'nur pdf oder video erlaubt.')
                positive(ref.get('pdf_page'), f'{label}.pdf_page')
                if 'pdf_page_end' in ref:
                    positive(ref['pdf_page_end'], f'{label}.pdf_page_end')
                    if type(ref.get('pdf_page')) is int and type(ref['pdf_page_end']) is int and ref['pdf_page_end'] < ref['pdf_page']:
                        fail(label, 'Endseite darf nicht vor der Startseite liegen.')
                if 'timestamp_seconds' in ref or 'timestamp_end_seconds' in ref:
                    fail(label, 'Zeitmarken benötigen kind=video.')
            if 'chapter' in ref:
                text(ref['chapter'], f'{label}.chapter')
            if 'printed_page' in ref:
                if type(ref['printed_page']) is int:
                    positive(ref['printed_page'], f'{label}.printed_page')
                else:
                    text(ref['printed_page'], f'{label}.printed_page')
            try:
                resolved = resolve_study_source(source_root, project_root, ref.get('path'))
                if kind == 'video' and (resolved.suffix.lower() != '.mp4' or Path(ref['path']).suffix.lower() != '.mp4'):
                    fail(f'{label}.path', 'Videobeleg benötigt eine MP4-Datei.')
                elif kind != 'video' and resolved.suffix.lower() == '.mp4':
                    fail(label, 'MP4-Quellen benötigen kind=video und eine Zeitmarke.')
            except SourceAccessError as exc:
                fail(f'{label}.path', str(exc))

    if not isinstance(content, dict):
        return ['Lernpaket muss ein JSON-Objekt sein.']
    if type(content.get('schema_version')) is not int or content['schema_version'] != 1:
        fail('schema_version', 'muss 1 sein.')
    number = content.get('module_number')
    if not isinstance(number, str) or not re.fullmatch(r'\d{5}', number):
        fail('module_number', 'fünfstellige Modulnummer als Text benötigt.')
    text(content.get('module_title'), 'module_title')
    overview = content.get('overview')
    picture = overview.get('big_picture') if isinstance(overview, dict) else None
    if not isinstance(overview, dict):
        fail('overview', 'Modulüberblick muss ein Objekt sein.')
    else:
        text(overview.get('title'), 'overview.title')
        texts(overview.get('paragraphs'), 'overview.paragraphs')
        texts(overview.get('learning_path'), 'overview.learning_path')
        sources(overview.get('sources'), 'overview.sources')
        units = overview.get('units')
        if not isinstance(units, list) or (not units and picture is None):
            fail('overview.units', 'Liste der Kurseinheiten benötigt.')
        else:
            unit_ids = set()
            for i, unit in enumerate(units):
                where = f'overview.units[{i}]'
                if not isinstance(unit, dict):
                    fail(where, 'Kurseinheit muss ein Objekt sein.')
                    continue
                positive(unit.get('unit'), f'{where}.unit')
                if type(unit.get('unit')) is int:
                    if unit['unit'] in unit_ids:
                        fail(where, 'doppelte Kurseinheit.')
                    unit_ids.add(unit['unit'])
                for field in ('title', 'description'):
                    text(unit.get(field), f'{where}.{field}')
                texts(unit.get('topics'), f'{where}.topics')
    lessons = content.get('lessons')
    if not isinstance(lessons, list) or (not lessons and picture is None):
        return errors + ['lessons: mindestens eine Lernpage benötigt.']
    lesson_ids = set()
    for i, lesson in enumerate(lessons):
        where = f'lessons[{i}]'
        if not isinstance(lesson, dict):
            fail(where, 'Lernpage muss ein Objekt sein.')
            continue
        for field in ('id', 'title', 'summary'):
            text(lesson.get(field), f'{where}.{field}')
        lid = lesson.get('id')
        if isinstance(lid, str):
            if lid in lesson_ids:
                fail(where, 'doppelte Lernpage-ID.')
            lesson_ids.add(lid)
        positive(lesson.get('unit'), f'{where}.unit')
        texts(lesson.get('learning_goals'), f'{where}.learning_goals')
        texts(lesson.get('exercise_ids'), f'{where}.exercise_ids', nonempty=False)
        sections = lesson.get('sections')
        if not isinstance(sections, list) or not sections:
            fail(f'{where}.sections', 'mindestens ein Lernabschnitt benötigt.')
            continue
        section_ids = set()
        for j, section in enumerate(sections):
            label = f'{where}.sections[{j}]'
            if not isinstance(section, dict):
                fail(label, 'Lernabschnitt muss ein Objekt sein.')
                continue
            for field in ('id', 'title'):
                text(section.get(field), f'{label}.{field}')
            sid = section.get('id')
            if isinstance(sid, str):
                if sid in section_ids:
                    fail(label, 'doppelte Abschnitt-ID.')
                section_ids.add(sid)
            texts(section.get('paragraphs'), f'{label}.paragraphs', nonempty=False)
            if 'bullets' in section:
                texts(section['bullets'], f'{label}.bullets')
            if 'note' in section:
                text(section['note'], f'{label}.note')
            if not section.get('paragraphs') and not section.get('bullets') and not section.get('table') and not section.get('image'):
                fail(label, 'Abschnitt benötigt fachlichen Inhalt.')
            sources(section.get('sources'), f'{label}.sources')
            if 'table' in section:
                table = section['table']
                if not isinstance(table, dict):
                    fail(f'{label}.table', 'Tabelle muss ein Objekt sein.')
                else:
                    headers, rows = table.get('headers'), table.get('rows')
                    texts(headers, f'{label}.table.headers')
                    if not isinstance(rows, list) or not rows:
                        fail(f'{label}.table.rows', 'Tabellenzeilen benötigt.')
                    else:
                        for row_index, row in enumerate(rows):
                            texts(row, f'{label}.table.rows[{row_index}]')
                            if isinstance(headers, list) and isinstance(row, list) and len(row) != len(headers):
                                fail(f'{label}.table.rows[{row_index}]', 'Zellenzahl stimmt nicht mit Kopfzeile überein.')
            if 'image' in section:
                image = section['image']
                if not isinstance(image, dict):
                    fail(f'{label}.image', 'Abbildung muss ein Objekt sein.')
                    continue
                text(image.get('caption'), f'{label}.image.caption')
                positive(image.get('source_page'), f'{label}.image.source_page')
                relative = image.get('path')
                if not isinstance(relative, str) or not relative.strip() or '\x00' in relative:
                    fail(f'{label}.image.path', 'lokaler Abbildungspfad benötigt.')
                    continue
                asset = Path(relative)
                try:
                    imports = (Path(project_root) / 'imports').resolve()
                    base = (imports / 'assets').resolve()
                    resolved = (imports / asset).resolve()
                    safe = not asset.is_absolute() and '..' not in asset.parts and _within(imports, Path(project_root).resolve()) and _within(base, imports) and _within(resolved, base)
                    if not safe or resolved.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'} or not resolved.is_file():
                        fail(f'{label}.image.path', 'lokale Abbildung unter imports/assets nicht vorhanden oder nicht erlaubt.')
                except (OSError, RuntimeError):
                    fail(f'{label}.image.path', 'Abbildung kann nicht sicher aufgelöst werden.')
    if picture is not None:
        where = 'overview.big_picture'
        if not isinstance(picture, dict):
            fail(where, 'Big Picture muss ein Objekt sein.')
        else:
            for field in ('title', 'central_question', 'intro', 'takeaway'):
                text(picture.get(field), f'{where}.{field}')
            if 'generated_by' in picture:
                text(picture['generated_by'], f'{where}.generated_by')
            if 'units' in picture:
                picture_units = picture['units']
                if not isinstance(picture_units, list) or any(type(unit) is not int or unit < 1 for unit in picture_units):
                    fail(f'{where}.units', 'Liste positiver ganzer Zahlen (Kurseinheiten) benötigt.')
            nodes = picture.get('nodes')
            node_ids = set()
            low, high = BIG_PICTURE_NODES
            if not isinstance(nodes, list) or not low <= len(nodes) <= high:
                fail(f'{where}.nodes', 'drei bis sieben Kernkonzepte benötigt.')  # wording follows BIG_PICTURE_NODES
            else:
                for i, node in enumerate(nodes):
                    label = f'{where}.nodes[{i}]'
                    if not isinstance(node, dict):
                        fail(label, 'Kernkonzept muss ein Objekt sein.')
                        continue
                    for field in ('id', 'title', 'summary', 'role'):
                        text(node.get(field), f'{label}.{field}')
                    nid = node.get('id')
                    if isinstance(nid, str):
                        if nid in node_ids:
                            fail(label, 'doppelte Konzept-ID.')
                        node_ids.add(nid)
                    sources(node.get('sources'), f'{label}.sources')
                    if 'scope_note' in node:
                        text(node['scope_note'], f'{label}.scope_note')
                    if 'lesson_ids' in node:
                        texts(node['lesson_ids'], f'{label}.lesson_ids', nonempty=False)
                        if isinstance(node['lesson_ids'], list):
                            for lid in node['lesson_ids']:
                                if not isinstance(lid, str) or lid not in lesson_ids:
                                    fail(f'{label}.lesson_ids', 'verknüpfte Lernseite nicht vorhanden.')
            connections = picture.get('connections')
            if not isinstance(connections, list) or not connections:
                fail(f'{where}.connections', 'mindestens ein erklärter Zusammenhang benötigt.')
            else:
                for i, connection in enumerate(connections):
                    label = f'{where}.connections[{i}]'
                    if not isinstance(connection, dict):
                        fail(label, 'Zusammenhang muss ein Objekt sein.')
                        continue
                    text(connection.get('label'), f'{label}.label')
                    for field in ('from', 'to'):
                        if not isinstance(connection.get(field), str) or connection[field] not in node_ids:
                            fail(f'{label}.{field}', 'verknüpftes Kernkonzept nicht vorhanden.')
                    if connection.get('from') == connection.get('to'):
                        fail(label, 'Zusammenhang benötigt zwei unterschiedliche Konzepte.')
    return errors


def load_learning_pages(project_root, source_root):
    """Read current files per request; invalid packages remain explicit errors."""
    project = Path(project_root).resolve()
    directory = project / 'content'
    packages, errors = [], []
    if not directory.is_dir():
        return packages, errors
    if not _within(directory.resolve(), project):
        return [], [{'file': 'content', 'module_number': None, 'errors': ['Lerninhalte liegen außerhalb der Anwendung.']}]
    numbers = set()
    for file in sorted(directory.glob('*.json')):
        content = None
        try:
            if not _within(file.resolve(), directory.resolve()):
                raise ValueError('Lernpaket liegt außerhalb des Inhaltsverzeichnisses.')
            content = json.loads(file.read_text(encoding='utf-8'))
            problems = validate_learning_page(content, source_root, project)
            if isinstance(content, dict) and isinstance(content.get('module_number'), str):
                number = content['module_number']
                if number in numbers:
                    problems.append('Mehr als ein Lernpaket für dieselbe Modulnummer.')
                numbers.add(number)
            if problems:
                number = content.get('module_number') if isinstance(content, dict) else None
                errors.append({'file': file.name, 'module_number': number if isinstance(number, str) else None, 'errors': problems})
            else:
                packages.append(content)
        except (ValueError, OSError, RuntimeError) as exc:
            errors.append({'file': file.name, 'module_number': None, 'errors': [str(exc)]})
    return packages, errors


def module_id_for_package(package, modules):
    """Follow existing module numbers, including modules with a manually assigned ID."""
    number = package.get('module_number')
    if not isinstance(number, str):
        return None
    matches = [module for module in modules if module.get('number') == number]
    if len(matches) == 1:
        return matches[0]['id']
    if not matches:
        fallback = next((module for module in modules if module['id'] == 'M-' + number and not module.get('number')), None)
        if fallback:
            return fallback['id']
    return None
