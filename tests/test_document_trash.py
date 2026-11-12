"""Removing an uploaded document: file into the waste folder, row out of the index, questions stay."""
from pathlib import Path

from tests.test_upload import _send, _tree, hub  # noqa: F401  (fixture)


def test_removed_document_moves_to_the_waste_folder_and_leaves_the_index(hub):
    assert _send(hub, 'falsch.md', unit=3).status_code == 200
    row = next(item for item in hub.get('/api/documents').json() if item['name'] == 'falsch.md')
    assert (hub.study / row['path']).is_file()
    answer = hub.delete(f"/api/documents/{row['id']}")
    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result['path'] == row['path'] and result['questions_kept'] == 0 and result['file_was_missing'] is False
    moved = Path(result['moved_to'])
    assert moved.is_file() and moved.read_text(encoding='utf-8').startswith('Die Stichprobe')
    assert (hub.project / 'data' / 'papierkorb') in moved.parents
    assert 'falsch.md' not in [item['name'] for item in hub.get('/api/documents').json()]
    assert not (hub.study / row['path']).exists()
    assert 'Einheit 3' not in {part for path in _tree(hub.study) for part in path.split('/')}
    # Scanning again does not bring the file back.
    hub.post('/api/scan', json={})
    assert 'falsch.md' not in [item['name'] for item in hub.get('/api/documents').json()]
    assert hub.delete(f"/api/documents/{row['id']}").status_code == 404


def test_a_document_whose_file_is_gone_is_simply_dropped(hub):
    assert _send(hub, 'weg.md', unit=1).status_code == 200
    row = next(item for item in hub.get('/api/documents').json() if item['name'] == 'weg.md')
    (hub.study / row['path']).unlink()
    result = hub.delete(f"/api/documents/{row['id']}").json()
    assert result['file_was_missing'] is True and result['moved_to'] is None
    assert 'weg.md' not in [item['name'] for item in hub.get('/api/documents').json()]
