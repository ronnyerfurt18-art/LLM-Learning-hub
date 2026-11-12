"""Removing a document from the index without destroying the file.

A wrong or unreadable upload would otherwise stay in the list forever. Removing
moves the file into the hub's own waste folder (``<Datenordner>/papierkorb/<Zeitstempel>/…``)
and drops the index row; nothing is deleted for good, moving the file back and
scanning again restores it. Questions already taken over from the file stay.
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

LOG = logging.getLogger(__name__)
TRASH = 'papierkorb'
_UNIT_FOLDER = re.compile(r'^Einheit \d+$')


def source_file(doc, project, source):
    """(base, absolute path) of a document's file; the base is the study folder or the hub's imports folder."""
    imported = doc['path'].startswith('@imports/')
    base = (project / 'imports' if imported else source).resolve()
    path = (base / (doc['path'][9:] if imported else doc['path'])).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise HTTPException(403, 'Quelldatei liegt außerhalb des Studienordners.')
    return base, path


def remove_document(hub, project, source, data_dir, did, lock):
    """Move the file into the waste folder and drop the index row. Returns what happened."""
    doc = hub.document(did)
    base, path = source_file(doc, Path(project), Path(source))
    moved = None
    if path.is_symlink():
        raise HTTPException(403, 'Verknüpfungen werden nicht entfernt.')
    if path.is_file():
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        target = Path(data_dir) / TRASH / stamp / path.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(path), str(target))
        except OSError as exc:
            LOG.exception('Datei konnte nicht in den Papierkorb verschoben werden.')
            raise HTTPException(500, f'Die Datei konnte nicht verschoben werden: {exc}')
        moved = str(target)
        parent = path.parent
        # An "Einheit n" folder the upload created is removed again once it is empty.
        if _UNIT_FOLDER.match(parent.name) and parent != base and not any(parent.iterdir()):
            try:
                parent.rmdir()
            except OSError:
                pass
    kept = sum(1 for question in hub.questions() if question.get('source') == doc['path'])
    with lock, hub.db() as db:
        db.execute('DELETE FROM documents WHERE id=?', (did,))
    return {'id': did, 'path': doc['path'], 'moved_to': moved, 'file_was_missing': moved is None, 'questions_kept': kept}


def register_document_trash_routes(app, hub, project_root, source_root, data_dir):
    @app.delete('/api/documents/{did}')
    def delete_document(did: int):
        return remove_document(hub, project_root, source_root, data_dir, did, app.state.lock)
