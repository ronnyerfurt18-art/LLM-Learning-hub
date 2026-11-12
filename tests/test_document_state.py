"""The documents page tells which files already became learning pages."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.content_files import cited_source_paths
from tests.test_module_import import _setup


def test_documents_know_whether_they_are_cited_by_published_learning_pages(tmp_path):
    source, project, app, mid = _setup(tmp_path)
    assert cited_source_paths(project) == set()
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/scan', json={}).status_code == 200
        rows = client.get('/api/documents').json()
        row = next(item for item in rows if item['name'] == '32711-01-lehrbrief.pdf')
        assert row['in_learning_pages'] is False
        package = {'schema_version': 1, 'module_number': '32711', 'module_title': 'BI', 'overview': {},
                   'lessons': [{'id': 'l1', 'unit': 1, 'title': 'Einstieg', 'summary': '', 'learning_goals': [], 'exercise_ids': [],
                                'sections': [{'id': 's1', 'title': 'A', 'paragraphs': [],
                                              'sources': [{'kind': 'pdf', 'path': row['path'], 'pdf_page': 1}]}]}]}
        (Path(project) / 'content' / 'bi-learning-pages.json').write_text(json.dumps(package), encoding='utf-8')
        (Path(project) / 'content' / 'kaputt.json').write_text('{', encoding='utf-8')  # Unreadable files are skipped.
        assert cited_source_paths(project) == {row['path']}
        rows = client.get('/api/documents').json()
        assert next(item for item in rows if item['path'] == row['path'])['in_learning_pages'] is True
