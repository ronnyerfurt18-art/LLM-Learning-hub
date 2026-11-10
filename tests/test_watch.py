"""Real background worker integration; source data stays in a disposable folder."""
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.main import create_app


def test_background_worker_detects_new_module_without_manual_scan():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'MLH_SCAN_INTERVAL': '10'}):
        source = Path(directory) / 'study'
        project = source / 'master-learning-hub'
        project.mkdir(parents=True)
        app = create_app(source, project / 'data', project, start_watch=True)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            folder = source / '99998 Automatisch erkannt'
            folder.mkdir()
            original = folder / 'Session2.md'
            text = '## Neue Unterlage\nEin noch ungeprüfter Text ohne sichere Lernfrage.\n'
            original.write_text(text, encoding='utf-8')
            deadline = time.monotonic() + 15
            documents = []
            while time.monotonic() < deadline:
                documents = client.get('/api/documents').json()
                if documents:
                    break
                time.sleep(.1)
            assert len(documents) == 1
            assert documents[0]['status'] == 'pending'
            assert documents[0]['unit'] == 2
            assert client.get('/api/modules').json()[0]['number'] == '99998'
            assert client.get('/api/health').json()['question_count'] == 0
            assert original.read_text(encoding='utf-8') == text
