"""Local, read-only word search over curated lessons and indexed study files.

The document scanner already owns text extraction. Search reads its page-aware
snapshot without extracting files again, calling a model, or storing queries.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Query

from .learning_pages import load_learning_pages, module_id_for_package, resolve_study_source


MAX_QUERY_CHARS = 200
MAX_SNIPPET_CHARS = 400
_DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.pptx', '.xlsx', '.txt', '.md', '.markdown'}
_SOURCE_FIELDS = ('path', 'title', 'kind', 'chapter', 'pdf_page', 'pdf_page_end',
                  'printed_page', 'timestamp_seconds', 'timestamp_end_seconds')
_NOTICE = (
    'Die Suche läuft lokal in Lernseiten, Big Pictures und den bereits erfassten '
    'Studienunterlagen. Alle Suchwörter müssen im selben Abschnitt oder auf derselben '
    'Dokumentseite einschließlich ihrer Überschrift vorkommen; Wortteile werden gefunden. '
    'Videos und Bilder werden nicht direkt durchsucht. PDF-Seiten entsprechen der '
    'Seitenzählung der Datei; Word-Dokumente haben hier keine feste Seitenzählung.'
)


def _plain(value):
    text = unicodedata.normalize('NFC', str(value or ''))
    text = text.replace('\u00ad', '')
    # A PDF line ending may split a word without changing its actual spelling.
    text = re.sub(r'(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)', '', text)
    return re.sub(r'\s+', ' ', re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)).strip()


def normalize_search_text(value):
    """Compare spelling variants consistently, including compound separators.

    Query words already ignore punctuation. Normalizing hyphens here also gives
    a spaced or non-breaking-hyphen spelling the same exact-title ranking as
    its ordinary hyphenated counterpart, without adding semantic synonyms.
    """
    text = ''.join(char for char in unicodedata.normalize('NFKD', _plain(value).casefold())
                   if not unicodedata.combining(char))
    return re.sub(r'\s+', ' ', re.sub(r'[-\u2010-\u2015\u2212]+', ' ', text)).strip()


def _query(value):
    if not isinstance(value, str) or len(value) > MAX_QUERY_CHARS:
        raise ValueError(f'Die Suche darf höchstens {MAX_QUERY_CHARS} Zeichen enthalten.')
    if any((ord(char) < 32 and char not in '\t\r\n') or ord(char) == 127 for char in value):
        raise ValueError('Die Suche enthält ungültige Steuerzeichen.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ValueError('Die Suche benötigt gültigen UTF-8-Text.')
    query = _plain(value)
    terms = list(dict.fromkeys(re.findall(r'[^\W_]+', normalize_search_text(query), re.UNICODE)))
    return query, terms


def _sources(refs):
    return [{key: ref[key] for key in _SOURCE_FIELDS if key in ref} for ref in refs]


def _section_text(section):
    parts = list(section.get('paragraphs', [])) + list(section.get('bullets', []))
    table = section.get('table')
    if table:
        parts += [' | '.join(table['headers'])]
        parts += [' | '.join(row) for row in table['rows']]
    if section.get('note'):
        parts.append(section['note'])
    if section.get('image'):
        parts += [section['image'].get('caption', ''), section['image'].get('alt', '')]
    return _plain(' '.join(parts))


def _curated_entries(packages, modules):
    for package in packages:
        mid = module_id_for_package(package, modules)
        if mid is None:
            continue
        module = next(item for item in modules if item['id'] == mid)
        base = {'module_id': mid, 'module_title': module['name'], 'unit_label': module.get('unit_label', 'Einheit')}
        overview = package['overview']
        picture = overview.get('big_picture', {})
        unit_text = [text for unit in overview.get('units', [])
                     for text in [unit['title'], unit['description'], *unit['topics']]]
        yield ({**base, 'id': f'overview:{mid}', 'kind': 'concept',
                'title': overview['title'], 'section_id': 'overview',
                'sources': _sources(overview['sources'])},
               _plain(' '.join(overview['paragraphs'] + overview['learning_path'] +
                               [picture.get(key, '') for key in ('title', 'central_question', 'intro', 'takeaway')] +
                               [connection['label'] for connection in picture.get('connections', [])] + unit_text)))
        for node in picture.get('nodes', []):
            yield ({**base, 'id': f"concept:{mid}:{node['id']}", 'kind': 'concept',
                    'title': node['title'], 'concept_id': node['id'],
                    'sources': _sources(node['sources'])},
                   _plain(' '.join(node.get(key, '') for key in ('summary', 'role', 'scope_note'))))
        for lesson in package['lessons']:
            lesson_base = {**base, 'kind': 'lesson', 'title': lesson['title'],
                           'lesson_id': lesson['id'], 'unit': lesson['unit']}
            refs, seen = [], set()
            for section in lesson['sections']:
                for ref in _sources(section['sources']):
                    key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
                    if key not in seen:
                        refs.append(ref)
                        seen.add(key)
            yield ({**lesson_base, 'id': f"lesson:{mid}:{lesson['id']}", 'sources': refs[:8]},
                   _plain(' '.join([lesson['summary']] + lesson['learning_goals'])))
            for section in lesson['sections']:
                yield ({**lesson_base, 'id': f"section:{mid}:{lesson['id']}:{section['id']}",
                        'section_id': section['id'], 'section_title': section['title'],
                        'sources': _sources(section['sources'])}, _section_text(section))


def _document_entries(rows, modules, source_root, project_root):
    module_by_id = {item['id']: item for item in modules}
    for row in rows:
        try:
            document = json.loads(row['payload'])
            mid = row['module_id']
            if (mid not in module_by_id or document.get('status') in {'missing', 'error'}
                    or document.get('kind') in {'administrative', 'gpt_import'}
                    or row['path'].startswith('@imports/')):
                continue
            path = resolve_study_source(source_root, project_root, row['path'])
            if path.suffix.lower() not in _DOCUMENT_EXTENSIONS:
                continue
            # An obvious stale snapshot must not masquerade as the current file.
            if type(document.get('size')) is int and path.stat().st_size != document['size']:
                continue
            title = _plain(document.get('title') or path.stem)
            extension = path.suffix.lower()
            # A concatenated legacy text has no trustworthy PDF page attribution.
            pages = document.get('page_texts')
            if not isinstance(pages, list):
                if extension == '.pdf':
                    continue
                pages = [{'page': 1, 'label': 'Dokument', 'text': document.get('text', '')}]
            for index, page in enumerate(pages):
                if not isinstance(page, dict) or not isinstance(page.get('text'), str):
                    continue
                number = page.get('page')
                if type(number) is not int or number < 1:
                    continue
                source = {'path': row['path'], 'title': title}
                if extension == '.pdf':
                    source.update(kind='pdf', pdf_page=number)
                    label = f'PDF-Seite {number}'
                elif extension == '.pptx':
                    label = f'Folie {number}'
                    source.update(kind='document', chapter=label)
                elif extension == '.docx':
                    label = 'Word-Dokument · keine feste Seitenzählung'
                    source.update(kind='document', chapter=label)
                else:
                    label = _plain(page.get('label') or f'Abschnitt {number}')
                    source.update(kind='document', chapter=label)
                key = f"{row['path']}\0{number}\0{index}"
                result = {'id': 'document:' + hashlib.sha256(key.encode()).hexdigest()[:24],
                          'kind': 'document', 'module_id': mid,
                          'module_title': module_by_id[mid]['name'], 'unit_label': module_by_id[mid].get('unit_label', 'Einheit'), 'title': title,
                          'section_title': label, 'source': source}
                if type(document.get('unit')) is int and document['unit'] > 0:
                    result['unit'] = document['unit']
                yield result, _plain(page['text'])
        except (OSError, ValueError, RuntimeError, TypeError):
            # A missing source or malformed historical index row cannot expose
            # internals or prevent searching the remaining valid study material.
            continue


def _snippet(text, terms):
    if len(text) <= MAX_SNIPPET_CHARS:
        return text
    folded, positions = [], []
    for index, char in enumerate(text):
        for normalized in unicodedata.normalize('NFKD', char.casefold()):
            if not unicodedata.combining(normalized):
                folded.append(normalized)
                positions.append(index)
    normalized = ''.join(folded)
    matches = []
    for term in terms:
        start = 0
        for _ in range(40):
            start = normalized.find(term, start)
            if start < 0:
                break
            matches.append((positions[start], term))
            start += max(1, len(term))
    if not matches:
        return text[:MAX_SNIPPET_CHARS - 1].rstrip() + '…'
    # Prefer a short visible context containing several different query words.
    candidates = [max(0, position - 70) for position, _ in matches]
    start = min(candidates, key=lambda candidate: (
        -len({term for position, term in matches if candidate <= position < candidate + 360}), candidate))
    start = min(start, len(text) - 360)
    end = min(len(text), start + 360)
    if start:
        boundary = text.find(' ', start, min(start + 25, end))
        if boundary >= 0:
            start = boundary + 1
    if end < len(text):
        boundary = text.rfind(' ', max(start, end - 25), end)
        if boundary >= 0:
            end = boundary
    return ('…' if start else '') + text[start:end].strip() + ('…' if end < len(text) else '')


def search_content(hub, source_root, project_root, q='', module_id=None, limit=30, offset=0):
    """Return deterministic, bounded passages using only SELECTs and file stats."""
    query, terms = _query(q)
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError('Für die Suche werden 1 bis 100 Treffer und ein gültiger Startwert benötigt.')
    # A separate read-only connection enforces that queries cannot modify learning
    # progress, document status, metadata, originals, or examination state.
    with closing(sqlite3.connect(Path(hub.path).resolve().as_uri() + '?mode=ro', uri=True)) as database:
        database.row_factory = sqlite3.Row
        modules = [dict(row) for row in database.execute('SELECT id,name,number FROM modules ORDER BY id')]
        if module_id and module_id not in {module['id'] for module in modules}:
            raise KeyError('Modul nicht gefunden.')
        rows = database.execute(
            'SELECT path,module_id,payload FROM documents' + (' WHERE module_id=?' if module_id else '') + ' ORDER BY path',
            (module_id,) if module_id else ()).fetchall() if terms else []
    result = {'query': query, 'terms': terms, 'total': 0, 'limit': limit, 'offset': offset,
              'results': [], 'notice': _NOTICE}
    if not terms:
        return result
    packages, errors = load_learning_pages(project_root, source_root)
    if module_id:
        modules = [module for module in modules if module['id'] == module_id]
    matches = []
    for entries in (_curated_entries(packages, modules),
                    _document_entries(rows, modules, source_root, project_root)):
        for item, body in entries:
            title = normalize_search_text(item['title'] + ' ' + item.get('section_title', ''))
            normalized = normalize_search_text(body)
            if not all(term in title or term in normalized for term in terms):
                continue
            score = sum(12 if term in title else 0 for term in terms)
            score += sum(min(normalized.count(term), 4) for term in terms)
            score += {'lesson': 12, 'concept': 6, 'document': 0}[item['kind']]
            if normalize_search_text(query) in title:
                score += 20
            item['snippet'] = _snippet(body or item['title'], terms)
            matches.append((score, item))
    matches.sort(key=lambda hit: (-hit[0], hit[1]['module_id'], hit[1]['title'].casefold(), hit[1]['id']))
    result.update(total=len(matches), results=[item for _, item in matches[offset:offset + limit]])
    if errors:
        result['notice'] += ' Einzelne ungültige Lernpakete wurden ausgelassen; bitte die Dokumentenverwaltung prüfen.'
    return result


def register_search_routes(app, hub, source_root, project_root):
    @app.get('/api/search')
    def search(q: str = Query('', max_length=MAX_QUERY_CHARS),
               module_id: Optional[str] = Query(None, max_length=160),
               limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return search_content(hub, source_root, project_root, q, module_id, limit, offset)
        except KeyError as exc:
            raise HTTPException(404, str(exc).strip("'"))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
