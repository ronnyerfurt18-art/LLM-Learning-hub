"""Loopback-only FastAPI application, same-origin UI, read-only study scanner."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sqlite3
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from starlette.background import BackgroundTask

from .ai import DisabledProvider
from .core import Hub, iso, norm, validate_import
from .documents import generate_proposals, scan_documents
from .planning import register_planning_routes
from .planner import register_planner_routes
from .big_picture import register_big_picture_routes
from .module_import import register_module_import_routes
from .upload import register_upload_routes
from .quality import register_quality_routes
from .learning_memory import register_memory_routes
from .tutor import register_tutor_routes
from .voice import register_voice_routes
from .lernwiki import register_wiki_routes
from .search import register_search_routes
from .assignments import assignment_module_numbers, assignments_for_module
from .local_model import active_features, study_folder
from .practice import register_practice_routes
from .learning_pages import (
    SOURCE_MEDIA_TYPES, SourceAccessError, load_learning_pages,
    module_id_for_package, resolve_study_source,
)

LOG = logging.getLogger('master_learning_hub')
PROJECT = Path(__file__).resolve().parent.parent


# Opening window from the cited page onward (scrolling forward works in every viewer).
MAX_PAGE_EXTRACT = 40


def seed_packages(project):
    """File names in imports/ that load at start; a missing or invalid list means none."""
    try:
        names = json.loads((Path(project) / 'imports' / 'seed.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return []
    except (ValueError, OSError):
        LOG.exception('imports/seed.json kann nicht gelesen werden; es wird kein Lernpaket automatisch geladen.')
        return []
    if not isinstance(names, list):
        LOG.error('imports/seed.json muss eine Liste von Dateinamen sein.')
        return []
    return [name for name in names if isinstance(name, str) and name.endswith('.json') and name != 'seed.json'
            and Path(name).name == name]


def create_app(source_root=None, data_dir=None, project_root=None, start_watch=True):
    project = Path(project_root or PROJECT).resolve()
    source = Path(source_root or study_folder(project)).resolve()
    data = Path(data_dir or os.environ.get('MLH_DATA_DIR', str(project / 'data'))).resolve()
    hub = Hub(data / 'learning.sqlite3')
    features = active_features()
    ai = DisabledProvider()
    lock, scan_lock, stop = threading.RLock(), threading.Lock(), threading.Event()
    interval = max(10, int(os.environ.get('MLH_SCAN_INTERVAL', '30')))

    def safe_directory(value):
        if not value:
            return ''
        if not isinstance(value, str):
            raise ValueError('Dokumentenverzeichnis muss ein Textpfad sein.')
        path = Path(value)
        resolved = (path if path.is_absolute() else source / path).resolve()
        try:
            return resolved.relative_to(source).as_posix()
        except ValueError:
            raise ValueError('Dokumentenverzeichnis muss innerhalb des Studienordners liegen.')

    def scan():
        if not source.is_dir():
            raise ValueError(f'Studienordner nicht erreichbar: {source}')
        with scan_lock:
            with hub.db() as db:
                previous = {r['path']: {**json.loads(r['payload']), 'id': r['id']} for r in db.execute('SELECT * FROM documents')}
            hashes = {p: row.get('sha256') for p, row in previous.items() if row.get('sha256') and row.get('status') not in {'error', 'missing'}}
            found = scan_documents(source, project, hashes)
            manual_modules = hub.modules()
            for doc in found:
                if doc['status'] == 'unchanged':
                    continue
                manual = previous.get(doc['path'], {}).get('manual_assignment')
                if manual:
                    m = hub.module(manual['module_id'])
                    doc.update(module_id=m['id'], module_name=m['name'], module_number=m['number'] or None, unit=manual['unit'], manual_assignment=manual)
                    doc['proposals'] = generate_proposals(doc)
                if not doc.get('module_id') and not doc.get('module_number'):
                    matches = [m for m in manual_modules if m.get('directory') and (doc['path'].startswith(m['directory'].rstrip('/') + '/'))]
                    if matches:
                        m = max(matches, key=lambda m: len(m['directory']))
                        doc.update(module_name=m['name'], module_number=m['number'] or m['id'], module_directory=m['directory'], module_id=m['id'])
                        doc['proposals'] = generate_proposals(doc)
                if doc.get('module_number') and not doc.get('module_id'):
                    m = hub.add_module({'name': doc['module_name'], 'number': doc['module_number'], 'directory': doc.get('module_directory'), 'unit_count': max(1, doc.get('unit') or 1)})
                    doc['module_id'] = m['id']
                    if (doc.get('unit') or 1) > m['unit_count']:
                        hub.patch_module(m['id'], {'unit_count': doc['unit']})
                doc.setdefault('module_id', None)
                doc['updated_at'] = iso()
                doc['proposal_count'] = len(doc.get('proposals', []))
                # Source updates are always pending and retain previous hashes only for audit.
                if doc['path'] in previous:
                    doc['previous_sha256'] = previous[doc['path']].get('sha256')
                with hub.db() as db:
                    db.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET module_id=excluded.module_id,payload=excluded.payload', (doc['path'], doc.get('module_id'), json.dumps(doc, ensure_ascii=False)))
            present = {doc['path'] for doc in found}
            for path, doc in previous.items():
                if path not in present and not path.startswith('@imports/') and doc.get('status') != 'missing':
                    doc.update(status='missing', error='Quelldatei nicht mehr vorhanden.', updated_at=iso())
                    with hub.db() as db:
                        db.execute('UPDATE documents SET payload=? WHERE path=?', (json.dumps(doc, ensure_ascii=False), path))
            # Future GPT Work JSON imports are proposed, never silently applied.
            imports = project / 'imports'
            if imports.is_dir():
                for path in sorted(imports.glob('*.json')):
                    if path.name == 'seed.json':  # the start list itself is not a learning package
                        continue
                    key = '@imports/' + path.name
                    try:
                        raw = path.read_bytes()
                        digest = hashlib.sha256(raw).hexdigest()
                        if previous.get(key, {}).get('sha256') == digest:
                            continue
                        content = json.loads(raw)
                        errors = validate_import(content)
                        m = content.get('module', {})
                        existing_module = next((module for module in hub.modules() if (m.get('number') and str(m['number']) == module['number']) or m.get('name') == module['name']), None)
                        seeded = hub.get_meta('seed:' + path.name) == digest
                        doc = {'path': key, 'title': path.stem, 'name': path.name, 'kind': 'gpt_import', 'module_name': m.get('name'), 'module_id': existing_module['id'] if existing_module else None, 'unit': None, 'sha256': digest, 'size': len(raw), 'pages': 0, 'status': 'imported' if seeded else 'error' if errors else 'pending', 'error': '\n'.join(errors) if errors else None, 'text': raw.decode('utf-8'), 'proposals': content.get('questions', []), 'proposal_count': len(content.get('questions', [])), 'updated_at': iso(), 'import_content': content}
                    except Exception as e:
                        doc = {'path': key, 'title': path.stem, 'kind': 'gpt_import', 'module_id': None, 'status': 'error', 'error': str(e), 'size': path.stat().st_size, 'pages': 0, 'proposal_count': 0, 'updated_at': iso()}
                    with hub.db() as db:
                        db.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET module_id=excluded.module_id,payload=excluded.payload', (key, doc.get('module_id'), json.dumps(doc, ensure_ascii=False)))
            indexed = hub.documents()
            module_units = {}
            for doc in indexed:
                if doc.get('module_id') and type(doc.get('unit')) is int:
                    module_units[doc['module_id']] = max(module_units.get(doc['module_id'], 1), doc['unit'])
            for m in hub.modules():
                if module_units.get(m['id'], 1) > m['unit_count']:
                    hub.patch_module(m['id'], {'unit_count': module_units[m['id']]})
            return {'new': sum(d.get('change') == 'new' for d in found), 'changed': sum(d.get('change') == 'changed' for d in found), 'errors': sum(d['status'] == 'error' for d in indexed), 'total': len(indexed)}

    def worker():
        while not stop.wait(interval):
            try:
                scan()
            except Exception:
                LOG.exception('Dateierkennung fehlgeschlagen; bestehende Lerninhalte bleiben verfügbar.')

    @asynccontextmanager
    async def lifespan(app):
        app.state.tutor.start()
        source_hashes = hub.get_meta('seed_sources') or {}
        # Only packages listed in imports/seed.json auto-load (a JSON list of file names).
        # Other imports continue to require an explicit confirmation.
        for filename in seed_packages(project):
            seed = project / 'imports' / filename
            if not seed.exists():
                continue
            try:
                raw = seed.read_bytes()
                content = json.loads(raw)
                errors = validate_import(content)
                if errors:
                    raise ValueError('\n'.join(errors[:30]))
                digest = hashlib.sha256(raw).hexdigest()
                if hub.get_meta('seed:' + seed.name) != digest:
                    hub.import_content(content, update_existing=True)
                    hub.set_meta('seed:' + seed.name, digest)
            except (ValueError, OSError):
                LOG.exception('Freigegebenes Lernpaket %s konnte nicht geladen werden.', filename)
                continue
            for relative in {q['source'] for q in content['questions']}:
                if relative in source_hashes:
                    continue
                path = (source / relative).resolve()
                # This marker tracks document-scanner confirmations. Videos are
                # not indexed there and must not be loaded into memory at startup.
                if path.suffix.lower() == '.mp4':
                    continue
                try:
                    path.relative_to(source)
                    if path.is_file():
                        source_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                except ValueError:
                    pass
        if source_hashes:
            hub.set_meta('seed_sources', source_hashes)
        try:
            scan()
        except Exception:
            LOG.exception('Initialer Scan fehlgeschlagen.')
        seeded_sources = hub.get_meta('seed_sources') or {}
        with hub.db() as db:
            for row in db.execute('SELECT * FROM documents').fetchall():
                doc = json.loads(row['payload'])
                source_imported = seeded_sources.get(doc['path']) == doc.get('sha256')
                package_imported = doc['path'].startswith('@imports/') and hub.get_meta('seed:' + doc['path'][9:]) == doc.get('sha256')
                if doc.get('status') == 'pending' and doc.get('sha256') and (source_imported or package_imported):
                    doc['status'] = 'imported'
                    db.execute('UPDATE documents SET payload=? WHERE id=?', (json.dumps(doc, ensure_ascii=False), row['id']))
        thread = None
        if start_watch:
            thread = threading.Thread(target=worker, name='study-folder-watcher', daemon=True)
            thread.start()
        yield
        app.state.tutor.stop()
        stop.set()
        if thread:
            thread.join(timeout=2)

    app = FastAPI(title='Master Learning Hub', version='1.0.0', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json')
    app.state.hub, app.state.scan, app.state.lock = hub, scan, lock

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        hostname = request.url.hostname
        if hostname not in {'localhost', '127.0.0.1', '[::1]', '::1'}:
            return JSONResponse({'detail': 'Nur lokaler Zugriff erlaubt.'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail': 'Zugriff muss aus der lokalen Anwendung erfolgen.'}, status_code=403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Fremde Webseiten dürfen lokale Daten nicht ändern.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': str(exc).strip("'")}, status_code=404)

    @app.get('/api/health')
    def health():
        with hub.db() as db:
            return {'status': 'ok', 'application': 'master-learning-hub',
                    'project_id': hashlib.sha256(str(project).encode()).hexdigest()[:24],
                    'launcher_version': int(os.environ.get('MLH_LAUNCHER_VERSION', '0')), 'database_version': db.execute('SELECT max(version) FROM migrations').fetchone()[0], 'question_count': db.execute('SELECT count(*) FROM questions').fetchone()[0]}

    @app.get('/api/settings')
    def settings():
        return {'source_root': str(source), 'scan_interval_seconds': interval, 'database_path': str(hub.path), 'ai': {'enabled': ai.enabled, 'provider': ai.name}, 'tutor': app.state.tutor.status(), 'features': features}

    @app.get('/api/assets/{asset_path:path}')
    def source_asset(asset_path: str):
        imports_base = (project / 'imports').resolve()
        base = (imports_base / 'assets').resolve()
        path = (imports_base / asset_path).resolve()
        try:
            imports_base.relative_to(project)
            base.relative_to(imports_base)
            path.relative_to(base)
        except ValueError:
            raise HTTPException(403, 'Abbildung liegt außerhalb der lokalen Lerninhalte.')
        if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
            raise HTTPException(403, 'Nur lokale Bilddateien sind erlaubt.')
        if not path.is_file():
            raise HTTPException(404, 'Quellabbildung nicht vorhanden.')
        return FileResponse(path)

    @app.get('/api/source')
    def original_source(path: str):
        try:
            original = resolve_study_source(source, project, path)
        except SourceAccessError as exc:
            raise HTTPException(exc.status, str(exc))
        return FileResponse(original, filename=original.name,
                            media_type=SOURCE_MEDIA_TYPES[original.suffix.lower()],
                            content_disposition_type='inline')

    @app.get('/api/source/pages')
    def original_pages(path: str, start: int, end: Optional[int] = None):
        """Serve the PDF from the cited page onward (up to MAX_PAGE_EXTRACT pages): it opens
        exactly there in every browser, independent of #page= support (Safari has none)."""
        try:
            original = resolve_study_source(source, project, path)
        except SourceAccessError as exc:
            raise HTTPException(exc.status, str(exc))
        if original.suffix.lower() != '.pdf':
            raise HTTPException(400, 'Seitenauszüge gibt es nur für PDF-Dateien.')
        if start < 1 or (end is not None and (end < start or end - start >= MAX_PAGE_EXTRACT)):
            raise HTTPException(400, f'Bitte einen Bereich von höchstens {MAX_PAGE_EXTRACT} Seiten wählen.')
        try:
            reader = PdfReader(str(original))
            total = len(reader.pages)
            if reader.is_encrypted or start > total or (end is not None and end > total):
                raise HTTPException(404, 'Diese Seite ist in der Quelldatei nicht vorhanden.')
            last = end if end is not None else min(total, start + MAX_PAGE_EXTRACT - 1)
            writer = PdfWriter()
            for number in range(start, last + 1):
                writer.add_page(reader.pages[number - 1])
            buffer = io.BytesIO()
            writer.write(buffer)
        except HTTPException:
            raise
        except (OSError, ValueError, KeyError, IndexError, NotImplementedError, PyPdfError):
            raise HTTPException(422, 'Die Seite konnte nicht aus der Quelldatei gelesen werden.')
        name = f"{original.stem}-ab-S{start}.pdf"
        return Response(buffer.getvalue(), media_type='application/pdf',
                        headers={'Content-Disposition': f"inline; filename*=UTF-8''{quote(name)}",
                                 'Cache-Control': 'no-store'})

    def learning_page_errors(errors):
        details = '\n'.join(f"{error['file']}: {'; '.join(error['errors'][:20])}" for error in errors)
        raise HTTPException(422, 'Lokale Lerninhalte müssen korrigiert werden:\n' + details)

    @app.get('/api/learning-pages')
    def learning_pages():
        packages, errors = load_learning_pages(project, source)
        existing = hub.modules()
        summaries = []
        for package in packages:
            module_id = module_id_for_package(package, existing)
            if not module_id:
                errors.append({'file': package['module_number'], 'errors': ['Kein eindeutig zugeordnetes Modul für dieses Lernpaket vorhanden.']})
                continue
            summary = {'module_id': module_id, 'module_number': package['module_number'],
                       'module_title': package['module_title'], 'lesson_count': len(package['lessons'])}
            if package['overview'].get('big_picture'):
                summary['has_big_picture'] = True
            summaries.append(summary)
        if errors:
            learning_page_errors(errors)
        return summaries

    @app.get('/api/learning-pages/{module_id}')
    def module_learning_pages(module_id: str):
        hub.module(module_id)
        packages, errors = load_learning_pages(project, source)
        existing = hub.modules()
        matching_errors = [error for error in errors if error.get('module_number') and module_id_for_package(error, existing) == module_id]
        if matching_errors:
            learning_page_errors(matching_errors)
        package = next((package for package in packages if module_id_for_package(package, existing) == module_id), None)
        if package:
            module = hub.module(module_id)
            return {**package, 'module_id': module_id, 'unit_label': module['unit_label'],
                    'has_assignments': (module.get('number') or '') in assignment_module_numbers(project)}
        unassigned_errors = [error for error in errors if not error.get('module_number')]
        if unassigned_errors:
            learning_page_errors(unassigned_errors)
        raise HTTPException(404, 'Für dieses Modul ist noch keine Lernpage vorhanden.')

    @app.get('/api/assignments/{module_id}')
    def module_assignments(module_id: str):
        module = hub.module(module_id)
        try:
            assignments = assignments_for_module(module, project, source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not assignments:
            raise HTTPException(404, 'Für dieses Modul sind keine Einsendearbeiten aufbereitet.')
        return {'module_id': module_id, 'assignments': assignments}

    @app.get('/api/dashboard')
    def dashboard():
        with lock:
            return hub.dashboard()

    @app.get('/api/modules')
    def modules():
        numbers = assignment_module_numbers(project)
        return [{**module, 'has_assignments': (module.get('number') or '') in numbers} for module in hub.modules()]

    @app.post('/api/modules')
    def add_module(value: dict):
        value['directory'] = safe_directory(value.get('directory'))
        with lock:
            result = hub.add_module(value)
        # Newly associated folders are re-extracted on next scan.
        if result.get('directory'):
            with hub.db() as db:
                for r in db.execute('SELECT * FROM documents').fetchall():
                    d = json.loads(r['payload'])
                    if d['path'].startswith(result['directory'].rstrip('/') + '/') and not d.get('module_id'):
                        d['sha256'] = None
                        db.execute('UPDATE documents SET payload=? WHERE id=?', (json.dumps(d, ensure_ascii=False), r['id']))
        return result

    @app.patch('/api/modules/{mid}')
    def patch_module(mid: str, value: dict):
        if 'directory' in value:
            value['directory'] = safe_directory(value['directory'])
        with lock:
            result = hub.patch_module(mid, value)
        if 'directory' in value and result.get('directory'):
            with hub.db() as db:
                for r in db.execute('SELECT * FROM documents').fetchall():
                    d = json.loads(r['payload'])
                    if d['path'].startswith(result['directory'].rstrip('/') + '/'):
                        d['sha256'] = None
                        db.execute('UPDATE documents SET payload=? WHERE id=?', (json.dumps(d, ensure_ascii=False), r['id']))
        return result

    @app.get('/api/questions')
    def questions(module_id: Optional[str] = None, unit: Optional[int] = None, type: Optional[str] = None, difficulty: Optional[int] = None, due: bool = False):
        return hub.questions(module_id, unit, type, difficulty, due)

    @app.post('/api/attempts')
    def attempt(value: dict):
        with lock:
            return hub.attempt(value['question_id'], value.get('answer'), value.get('rating'), value.get('manual_score'))

    @app.patch('/api/attempts/{aid}')
    def correct_attempt(aid: str, value: dict):
        with lock:
            return hub.correct_attempt(aid, value['manual_score'], value.get('rating'))

    @app.get('/api/stats')
    def stats():
        with lock:
            return hub.stats()

    @app.get('/api/exams')
    def exams():
        with lock:
            return hub.exams()

    @app.post('/api/exams')
    def create_exam(value: dict):
        with lock:
            return hub.create_exam(value)

    @app.get('/api/exams/{eid}')
    def exam(eid: str):
        with lock:
            return hub.exam(eid)

    @app.patch('/api/exams/{eid}')
    def save_exam(eid: str, value: dict):
        with lock:
            return hub.update_exam(eid, value.get('answers'), value.get('current_index'))

    @app.post('/api/exams/{eid}/submit')
    def submit_exam(eid: str, value: dict):
        with lock:
            return hub.submit_exam(eid, value.get('answers'))

    @app.patch('/api/exams/{eid}/grade')
    def grade_exam(eid: str, value: dict):
        with lock:
            return hub.grade_exam(eid, value['question_id'], value['manual_score'], value.get('rating'))

    @app.get('/api/documents')
    def documents():
        return hub.documents()

    @app.post('/api/scan')
    def scan_now(value: dict):
        return scan()

    @app.get('/api/documents/{did}')
    def document(did: int):
        return hub.document(did)

    @app.patch('/api/documents/{did}')
    def assign_document(did: int, value: dict):
        d = hub.document(did)
        m = hub.module(value['module_id'])
        unit = value.get('unit', d.get('unit') or 1)
        if type(unit) is not int or not 1 <= unit <= 999:
            raise ValueError('Kurseinheit muss zwischen 1 und 999 liegen.')
        d.update(module_id=m['id'], module_name=m['name'], unit=unit, updated_at=iso(), manual_assignment={'module_id': m['id'], 'unit': unit})
        d['proposals'] = [{**q, 'unit': unit} for q in d.get('proposals', [])]
        with hub.db() as db:
            db.execute('UPDATE documents SET module_id=?,payload=? WHERE id=?', (m['id'], json.dumps(d, ensure_ascii=False), did))
        if unit > m['unit_count']:
            hub.patch_module(m['id'], {'unit_count': unit})
        return {**d, 'id': did}

    @app.get('/api/documents/{did}/source')
    def document_source(did: int):
        doc = hub.document(did)
        base = project / 'imports' if doc['path'].startswith('@imports/') else source
        path = (base / (doc['path'][9:] if doc['path'].startswith('@imports/') else doc['path'])).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError:
            raise HTTPException(403, 'Quelldatei liegt außerhalb des Studienordners.')
        if not path.is_file():
            raise HTTPException(404, 'Quelldatei nicht vorhanden.')
        return FileResponse(path, filename=path.name)

    @app.post('/api/documents/{did}/confirm')
    def confirm_document(did: int, value: dict):
        d = hub.document(did)
        if d.get('kind') == 'gpt_import' and d.get('import_content'):
            content = {**d['import_content']}
            chosen = value.get('module_id')
            if chosen and chosen != '__import_module__':
                content['module'] = hub.module(chosen)
            if 'questions' in value:
                content['questions'] = value['questions']
            if value.get('unit'):
                content['questions'] = [{**q, 'unit': value['unit']} for q in content['questions']]
        else:
            m = hub.module(value.get('module_id') or d.get('module_id'))
            content = {'schema_version': 1, 'module': m, 'questions': value.get('questions', d.get('proposals', []))}
            if value.get('unit'):
                content['questions'] = [{**q, 'unit': value['unit']} for q in content['questions']]
        with lock:
            result = hub.import_content(content)
        d.update(status='imported', module_id=result['module_id'], updated_at=iso())
        with hub.db() as db:
            db.execute('UPDATE documents SET module_id=?,payload=? WHERE id=?', (result['module_id'], json.dumps(d, ensure_ascii=False), did))
        return result

    @app.post('/api/import/preview')
    def preview_import(value: dict):
        content = value.get('content')
        errors = validate_import(content)
        return {'valid': not errors, 'errors': errors, 'questions': content.get('questions', []) if isinstance(content, dict) else [], 'module': content.get('module', {}) if isinstance(content, dict) else {}, 'coverage': content.get('coverage', []) if isinstance(content, dict) else [], 'originals': content.get('originals', []) if isinstance(content, dict) else []}

    @app.post('/api/import/confirm')
    def confirm_import(value: dict):
        with lock:
            result = hub.import_content(value.get('content'))
        return result

    @app.get('/api/coverage')
    def coverage(module_id: Optional[str] = None, unit: Optional[int] = None):
        return hub.coverage(module_id, unit)

    @app.post('/api/coverage/analyze')
    def coverage_hints(value: dict):
        mid = value['module_id']
        hub.module(mid)
        requested_unit = value.get('unit')
        if requested_unit is not None and (type(requested_unit) is not int or not 1 <= requested_unit <= 999):
            raise ValueError('Kurseinheit muss zwischen 1 und 999 liegen.')
        summaries = [hub.document(d['id']) for d in hub.documents() if d.get('module_id') == mid and d.get('kind') == 'summary' and d['status'] not in {'error', 'missing'}]
        topics = {}
        for q in hub.questions(mid, unit=requested_unit):
            topics.setdefault((q['unit'], q['topic']), set()).update(q.get('keywords', []))
        with hub.db() as db:
            for (unit, topic), terms in topics.items():
                unit_summaries = [d for d in summaries if d.get('unit') == unit]
                text = norm('\n'.join(d.get('text', '') for d in unit_summaries))
                terms = sorted(terms) or [topic]
                found = [t for t in terms if norm(t) in text]
                level = 'partial' if found else 'missing'  # A keyword never proves complete coverage.
                row = {'unit': unit, 'topic': topic, 'coverage': level, 'method': 'keyword', 'keywords': terms, 'notes': f'{len(found)} von {len(terms)} Begriffen gefunden. Dies ist ein Suchhinweis, keine Prüfung der vollständigen inhaltlichen Abdeckung.', 'source': f'Übungsfragen aus Session {unit}', 'summary_source': ', '.join(d['path'] for d in unit_summaries) or f'Keine zugeordnete Zusammenfassung für Session {unit} vorhanden.'}
                cid = f'{mid}:{unit}:{topic}:keyword'
                db.execute('INSERT OR REPLACE INTO coverage VALUES(?,?,?)', (cid, mid, json.dumps(row, ensure_ascii=False)))
        return hub.coverage(mid, requested_unit)

    @app.patch('/api/coverage/{cid:path}')
    def confirm_coverage(cid: str, value: dict):
        return hub.confirm_coverage(cid, value)

    @app.get('/api/export')
    def export():
        return Response(json.dumps(hub.export(), ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="master-learning-hub-export.json"'})

    @app.get('/api/backup')
    def backup():
        fd, filename = tempfile.mkstemp(prefix='mlh-backup-', suffix='.sqlite3')
        os.close(fd)
        with hub.db() as db, sqlite3.connect(filename) as target:
            db.backup(target)
        return FileResponse(filename, filename='master-learning-hub-backup.sqlite3', media_type='application/vnd.sqlite3', background=BackgroundTask(Path(filename).unlink, missing_ok=True))

    register_planning_routes(app, hub, project, source)
    register_memory_routes(app, hub, project)
    register_tutor_routes(app, hub, project, source)
    register_planner_routes(app, hub, project, source)
    # A switched-off feature has no routes at all: they answer 404 like any unknown address.
    if 'module_import' in features:
        register_module_import_routes(app, hub, project, source, data)
        register_upload_routes(app, hub, project, source)
    if 'big_picture' in features:
        register_big_picture_routes(app, hub, project, source, data)
    register_quality_routes(app, hub)
    if 'voice' in features:
        register_voice_routes(app)
    register_wiki_routes(app, hub, project, source)
    register_search_routes(app, hub, source, project)
    register_practice_routes(app, hub, lock)

    dist = project / 'frontend' / 'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    else:
        @app.get('/')
        def not_built():
            return {'message': 'Bitte einmal Installation.command ausführen, um die Oberfläche zu bauen.'}
    return app


app = create_app()
