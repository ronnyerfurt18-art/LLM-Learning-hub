"""Upload of study documents into the study folder. The file is the raw request body, counted while it is read."""
import json
import logging
import re
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .documents import SUPPORTED_EXTENSIONS
from .learning_pages import _within

LOG = logging.getLogger('master_learning_hub')
MAX_UPLOAD_BYTES = 300 * 1024 * 1024
MAX_NAME_CHARS = 180
UPLOAD_EXTENSIONS = SUPPORTED_EXTENSIONS | {'.mp4'}
TOO_BIG = 'Die Datei ist zu groß (höchstens 300 MB).'


def clean_filename(value):
    """Plain base name that the document scan will see; anything that could leave the folder is refused."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Dateiname fehlt.')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Der Dateiname enthält Steuerzeichen.')
    if value != value.strip() or '/' in value or '\\' in value or ':' in value or Path(value).name != value:
        raise ValueError('Bitte nur einen Dateinamen ohne Ordner angeben.')
    if value.startswith('.') or value.startswith('~$'):
        raise ValueError('Dateinamen dürfen nicht mit „.“ oder „~$“ beginnen; solche Dateien werden nicht erfasst.')
    if len(value) > MAX_NAME_CHARS:
        raise ValueError(f'Der Dateiname ist zu lang (höchstens {MAX_NAME_CHARS} Zeichen).')
    if Path(value).suffix.lower() not in UPLOAD_EXTENSIONS:
        raise ValueError('Dieser Dateityp wird nicht angenommen. Erlaubt: ' + ', '.join(sorted(UPLOAD_EXTENSIONS)) + '.')
    return value


def clean_unit(value):
    if value is None or value == '':
        return None
    if not re.fullmatch(r'[0-9]{1,3}', value) or not 1 <= int(value) <= 999:
        raise ValueError('Kurseinheit muss zwischen 1 und 999 liegen.')
    return int(value)


def default_directory(module):
    """Folder name for a module that has none: „<Nummer> <Name>“ without anything a file system dislikes."""
    label = ' '.join(part for part in (module.get('number'), module.get('name')) if part)
    label = re.sub(r'\s+', ' ', re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]+', ' ', label)).strip(' .')[:100].rstrip(' .')
    return label or 'Modul'


def register_upload_routes(app, hub, project_root, source_root):
    project, source = Path(project_root).resolve(), Path(source_root).resolve()

    @app.post('/api/documents/upload')
    async def upload(request: Request, module_id: str, filename: str, unit: Optional[str] = None):
        module = hub.module(module_id)
        name, unit_number = clean_filename(filename), clean_unit(unit)
        declared = request.headers.get('content-length', '')
        if declared.isascii() and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, TOO_BIG)
        directory = Path(module.get('directory') or default_directory(module))
        folder = (source / directory / (f'Einheit {unit_number}' if unit_number else '.')).resolve()
        if not _within(folder, source) or _within(folder, project):
            raise HTTPException(403, 'Der Zielordner liegt außerhalb des Studienordners oder im Programmordner.')
        target = folder / name
        if target.exists() or target.is_symlink():
            raise HTTPException(409, f'„{name}“ ist in diesem Ordner schon vorhanden und wird nicht überschrieben.')
        created = [path for path in reversed([folder, *folder.parents]) if _within(path, source) and not path.exists()]
        pending, committed = folder / f'.upload-{secrets.token_hex(6)}.part', False
        try:
            folder.mkdir(parents=True, exist_ok=True)
            size = 0
            with pending.open('xb') as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, TOO_BIG)
                    stream.write(chunk)
            if not size:
                raise HTTPException(400, 'Die Datei ist leer.')

            def place():
                if target.exists() or target.is_symlink():
                    raise HTTPException(409, f'„{name}“ ist in diesem Ordner schon vorhanden und wird nicht überschrieben.')
                pending.replace(target)
                if not module.get('directory'):
                    with app.state.lock:
                        hub.patch_module(module_id, {'directory': directory.as_posix()})
            await run_in_threadpool(place)
            committed = True
        except OSError:
            LOG.exception('Upload konnte nicht gespeichert werden.')
            raise HTTPException(500, 'Die Datei konnte nicht gespeichert werden. Bitte Speicherplatz und Rechte des Studienordners prüfen.')
        finally:
            if not committed:
                pending.unlink(missing_ok=True)
                for path in reversed(created):
                    try:
                        path.rmdir()
                    except OSError:
                        break
        try:
            await run_in_threadpool(app.state.scan)
        except Exception:
            LOG.exception('Dateierkennung nach dem Upload fehlgeschlagen; die Datei wurde gespeichert.')
        relative = target.relative_to(source).as_posix()
        # The scan decides the unit (a number in the file name outranks the folder); report what it found.
        detected = unit_number
        with hub.db() as db:
            row = db.execute('SELECT payload FROM documents WHERE path=?', (relative,)).fetchone()
        if row:
            detected = json.loads(row['payload']).get('unit')
        return {'path': relative, 'module_id': module_id, 'unit': detected, 'requested_unit': unit_number, 'size': size}
