"""Published learning-page files in content/: find, back up and rewrite them safely."""
import json
import os
import re
import shutil
import threading
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


def find_package(project, number):
    """(path, content) of the published learning-page file of a module number, or (None, None)."""
    found = []
    for path in sorted((Path(project) / 'content').glob('*.json')):
        try:
            content = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(content, dict) and content.get('module_number') == number:
            found.append((path, content))
    if len(found) > 1:
        raise ValueError('Für dieses Modul gibt es mehrere Lernseiten-Dateien (' + ', '.join(path.name for path, _ in found)
                         + '). Bitte zuerst aufräumen.')
    return found[0] if found else (None, None)


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
