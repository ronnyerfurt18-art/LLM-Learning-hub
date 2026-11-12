"""Published learning-page files in content/: find, back up and rewrite them safely."""
import json
import os
import re
import shutil
import threading
import hashlib
from datetime import datetime
from pathlib import Path

# Publishing lessons and publishing a big picture both read, change and rewrite the same file.
PACKAGE_LOCK = threading.RLock()


def module_number(module):
    """Number under which a module's learning pages are filed (a bare `M-12345` id counts as its number)."""
    number = module.get('number') or ''
    if number:
        return number
    return module['id'][2:] if re.fullmatch(r'M-\d{5}', module.get('id', '')) else ''


def module_key(module):
    """Stable URL-safe key, independent of user-editable metadata."""
    mid = module['id']
    if re.fullmatch(r'M-\d{5}', mid):
        return mid[2:]
    return mid if re.fullmatch(r'[A-Za-z0-9_-]+', mid) else 'modul-' + hashlib.sha256(mid.encode()).hexdigest()[:20]


def matches_module(content, module):
    """Explicit identity wins; only older packages fall back to a nonempty number."""
    if content.get('module_id'):
        return content['module_id'] == module['id']
    number = module_number(module)
    if number:
        return content.get('module_number') == number
    return bool(module.get('name')) and not content.get('module_number') and content.get('module_title') == module['name']


def find_package(project, module):
    """Find one package by stable module identity, with legacy number compatibility."""
    if isinstance(module, str):
        module = {'id': 'M-' + module, 'number': module}
    found = []
    for path in sorted((Path(project) / 'content').glob('*.json')):
        try:
            content = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(content, dict) and matches_module(content, module):
            found.append((path, content))
    if len(found) > 1:
        raise ValueError('Für dieses Modul gibt es mehrere Lernseiten-Dateien (' + ', '.join(path.name for path, _ in found)
                         + '). Bitte zuerst aufräumen.')
    return found[0] if found else (None, None)


def draft_file(project, module, kind, legacy_slug=None):
    """Find drafts after metadata edits; arbitrary labels never become filesystem paths."""
    folder = Path(project) / 'imports' / 'entwuerfe'
    owned = []
    for path in sorted(folder.glob(f'*-{kind}.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(value, dict) and value.get('module_id') == module['id']:
            owned.append(path)
    if len(owned) > 1:
        raise ValueError('Mehrere Entwürfe für dieses Modul vorhanden. Bitte zuerst zusammenführen.')
    if owned:
        return owned[0]
    number = module_number(module)
    # Existing numbered drafts and the earlier title-based drafts remain readable.
    names = [number] if re.fullmatch(r'\d{5}', number) else []
    if legacy_slug and not number:
        names.append(legacy_slug)
    for name in names:
        path = folder / f'{name}-{kind}.json'
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                return path  # Let the caller report the malformed draft.
            if isinstance(value, dict) and (value.get('module_id') == module['id'] or
                    (not value.get('module_id') and (kind == 'big-picture' or
                     matches_module(value, module) or value.get('module_title') == module['name']))):
                return path
    key = number if re.fullmatch(r'\d{5}', number) else 'modul-' + hashlib.sha256(module['id'].encode()).hexdigest()[:20]
    target = folder / f'{key}-{kind}.json'
    if target.exists():
        target = folder / f"modul-{hashlib.sha256(module['id'].encode()).hexdigest()[:20]}-{kind}.json"
    return target


def backup_file(path, data_dir):
    """Copy of an existing file at <data>/backups/<name>-<YYYYMMDD-HHMMSS>.json; an earlier copy is never replaced."""
    folder = Path(data_dir) / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target, count = folder / f'{path.stem}-{stamp}.json', 1
    while target.exists():
        count += 1
        target = folder / f'{path.stem}-{stamp}-{count}.json'
    pending = target.with_name(f'.{target.name}.tmp')
    try:
        shutil.copyfile(path, pending)
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    return target


def write_json(path, value):
    """Write through a temporary file in the same folder, so a crash never leaves half a file."""
    pending = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def cited_source_paths(project):
    """Study-folder paths every published learning page cites: which documents already became lessons."""
    paths = set()

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str):
                paths.add(value['path'])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for path in sorted((Path(project) / 'content').glob('*.json')):
        try:
            content = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(content, dict) and content.get('lessons'):
            walk(content['lessons'])
    return paths
