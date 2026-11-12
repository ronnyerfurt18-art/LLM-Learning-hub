"""Publishing adds units to published lessons; the overview per unit shares its rules with the preview."""
import copy
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.module_import import merge_package
from test_module_import import _documents, _setup
from tools.install_demo import install

FILE = 'content/lernen-lernen-learning-pages.json'
DRAFT = 'imports/entwuerfe/10001-learning-pages.json'


def _demo(directory):
    project, study = Path(directory) / 'hub', Path(directory) / 'Studium'
    project.mkdir()
    install(project, study)
    app = create_app(study, project / 'data', project, start_watch=False)
    return project, app


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')


def _only_units(package, units):
    """The demo package reduced to some units, as an earlier partial publication would have left it."""
    result = copy.deepcopy(package)
    result['lessons'] = [lesson for lesson in package['lessons'] if lesson['unit'] in units]
    result['overview']['units'] = [item for item in package['overview']['units'] if item['unit'] in units]
    result['overview']['learning_path'] = ['Kurseinheit 1: Zuerst verstehen.'] if 1 in units else ['Kurseinheit 2: Danach vertiefen.']
    return result


def _big_picture_text(path):
    """The big picture exactly as it stands in the file, byte for byte."""
    text = path.read_text(encoding='utf-8')
    start = text.index('"big_picture": ') + len('"big_picture": ')
    return text[start:start + json.JSONDecoder().raw_decode(text[start:])[1]]


def _prepare(project, published_units):
    """Draft = complete demo package; published file = only `published_units` (or none)."""
    full = json.loads((project / FILE).read_text(encoding='utf-8'))
    _write(project / DRAFT, full)
    (project / FILE).unlink()
    if published_units:
        _write(project / FILE, _only_units(full, published_units))
    return full


def _publish(client):
    return client.post('/api/module-import/publish', json={'module_id': 'M-10001'})


def test_publish_creates_the_file_when_the_module_has_none():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        full = _prepare(project, None)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            answer = _publish(client)
        assert answer.status_code == 200, answer.text
        assert answer.json() == {'published': 'content/lernen-lernen-demo-learning-pages.json', 'lessons': 4,
                                 'added_units': [1, 2], 'skipped_units': []}
        assert json.loads((project / answer.json()['published']).read_text(encoding='utf-8')) == {**full, 'module_id': 'M-10001'}
        assert not (project / 'data' / 'backups').exists()


def test_publish_adds_a_new_unit_and_keeps_everything_published():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        full = _prepare(project, {1})
        before_bytes = (project / FILE).read_bytes()
        before = json.loads(before_bytes)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            answer = _publish(client)
            assert answer.status_code == 200, answer.text
            body = answer.json()
            assert body == {'published': FILE, 'lessons': 2, 'added_units': [2], 'skipped_units': [1]}
            # The learning page API serves the combined package.
            served = client.get('/api/learning-pages/M-10001').json()
        after = json.loads((project / FILE).read_text(encoding='utf-8'))
        assert after['lessons'][:2] == before['lessons'] and after['lessons'][2:] == [l for l in full['lessons'] if l['unit'] == 2]
        assert [item['unit'] for item in after['overview']['units']] == [1, 2]
        assert after['overview']['units'][0] == before['overview']['units'][0]
        assert after['overview']['units'][1] == full['overview']['units'][1]
        assert after['overview']['learning_path'][0] == 'Kurseinheit 1: Zuerst verstehen.'
        assert after['overview']['learning_path'][1].startswith('Kurseinheit 2: ')
        for key in ('title', 'paragraphs', 'sources'):
            assert after['overview'][key] == before['overview'][key]
        assert {key: value for key, value in after.items() if key not in ('lessons', 'overview', 'module_id')} == \
            {key: value for key, value in before.items() if key not in ('lessons', 'overview', 'module_id')}
        assert len(served['lessons']) == 4
        # The previous file is kept as a copy before it is changed.
        copies = list((project / 'data' / 'backups').glob('lernen-lernen-learning-pages-*.json'))
        assert len(copies) == 1 and re.fullmatch(r'lernen-lernen-learning-pages-\d{8}-\d{6}\.json', copies[0].name)
        assert copies[0].read_bytes() == before_bytes


def test_existing_big_picture_stays_byte_for_byte():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        _prepare(project, {1})
        before = _big_picture_text(project / FILE)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            assert _publish(client).status_code == 200
        assert _big_picture_text(project / FILE) == before


def test_lower_unit_is_inserted_in_order_and_colliding_ids_are_not_taken():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        full = _prepare(project, {2})
        # Without a big picture: its links to the dropped lesson would (rightly) make the result invalid.
        published = json.loads((project / FILE).read_text(encoding='utf-8'))
        del published['overview']['big_picture']
        _write(project / FILE, published)
        draft = copy.deepcopy(full)
        taken = next(lesson['id'] for lesson in full['lessons'] if lesson['unit'] == 2)
        # One unit-1 lesson reuses the id of a published unit-2 lesson and must be left out.
        next(lesson for lesson in draft['lessons'] if lesson['unit'] == 1)['id'] = taken
        _write(project / DRAFT, draft)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            answer = _publish(client)
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body['lessons'] == 1 and body['added_units'] == [1] and body['skipped_units'] == [2]
        after = json.loads((project / FILE).read_text(encoding='utf-8'))
        assert [lesson['unit'] for lesson in after['lessons']] == [1, 2, 2]
        assert [item['unit'] for item in after['overview']['units']] == [1, 2]
        # Only the lesson that was taken over appears in the unit entry.
        assert after['overview']['units'][0]['topics'] == [after['lessons'][0]['title']]
        assert after['overview']['learning_path'][0].startswith('Kurseinheit 1: ')


def test_a_unit_that_is_already_published_is_skipped_even_with_new_lesson_ids():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        full = _prepare(project, {1})
        draft = copy.deepcopy(full)
        for lesson in draft['lessons']:
            if lesson['unit'] == 1:
                lesson['id'] += '-neu'
                lesson['title'] += ' (überarbeitet)'
        _write(project / DRAFT, draft)
        before = json.loads((project / FILE).read_text(encoding='utf-8'))
        with TestClient(app, base_url='http://127.0.0.1') as client:
            body = _publish(client).json()
        assert body == {'published': FILE, 'lessons': 2, 'added_units': [2], 'skipped_units': [1]}
        after = json.loads((project / FILE).read_text(encoding='utf-8'))
        assert after['lessons'][:2] == before['lessons'] and all(lesson['unit'] == 2 for lesson in after['lessons'][2:])
        assert not any(lesson['id'].endswith('-neu') for lesson in after['lessons'])


def test_nothing_new_is_reported_and_nothing_is_written():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        _prepare(project, {1, 2})
        before = (project / FILE).read_bytes()
        with TestClient(app, base_url='http://127.0.0.1') as client:
            answer = _publish(client)
        assert answer.status_code == 400 and answer.json()['detail'] == 'Alle Einheiten des Entwurfs sind bereits veröffentlicht.'
        assert (project / FILE).read_bytes() == before and not (project / 'data' / 'backups').exists()


def test_invalid_result_writes_nothing_and_makes_no_backup():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        full = _prepare(project, {1})
        draft = copy.deepcopy(full)
        next(lesson for lesson in draft['lessons'] if lesson['unit'] == 2)['sections'][0]['sources'][0]['path'] = 'gibt/es/nicht.pdf'
        _write(project / DRAFT, draft)
        before = (project / FILE).read_bytes()
        with TestClient(app, base_url='http://127.0.0.1') as client:
            answer = _publish(client)
        assert answer.status_code == 400 and 'nichts geschrieben' in answer.json()['detail'] and 'Quelldatei nicht vorhanden' in answer.json()['detail']
        assert (project / FILE).read_bytes() == before and not (project / 'data' / 'backups').exists()
        assert not list((project / 'content').glob('*.tmp')) and not list((project / 'content').glob('.*.tmp'))


def test_merge_does_not_modify_its_inputs():
    full = json.loads((Path(__file__).resolve().parents[1] / 'demo' / FILE).read_text(encoding='utf-8'))
    existing = _only_units(full, {1})
    snapshot = copy.deepcopy(existing), copy.deepcopy(full)
    merged, added, skipped = merge_package(existing, full)
    assert (existing, full) == snapshot and merged is not existing
    assert added['units'] == [2] and skipped == [1]
    with pytest.raises(ValueError, match='bereits veröffentlicht'):
        merge_package(merged, full)


def test_overview_per_unit_uses_the_rules_of_the_preview():
    with TemporaryDirectory() as directory:
        source, project, app, mid = _setup(directory)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            _documents(app.state.hub, mid)
            answer = client.get('/api/module-import/overview', params={'module_id': mid})
            assert answer.status_code == 200, answer.text
            data = answer.json()
            plan = client.get('/api/module-import/preview', params={'module_id': mid}).json()
        assert (data['module_id'], data['module_number'], data['draft'], data['has_learning_pages']) == (mid, '32711', False, False)
        assert [item['unit'] for item in data['units']] == [1, 2]
        by_name = {doc['name']: {k: v for k, v in doc.items() if k not in ('id', 'manual_kind')} for unit in data['units'] for doc in unit['documents']}
        by_name.update({doc['name']: {k: v for k, v in doc.items() if k not in ('id', 'manual_kind')} for doc in data['unassigned_documents']})
        assert by_name['32711-01-lehrbrief.pdf'] == {
            'path': '32711 BI/32711-01-lehrbrief.pdf', 'name': '32711-01-lehrbrief.pdf', 'kind': 'course_material',
            'pages': 5, 'usable': True, 'reason': None}
        assert by_name['folien1.pdf']['usable'] is False and 'Folien nicht verwendet' in by_name['folien1.pdf']['reason']
        assert by_name['skript.docx']['reason'].startswith('Kein PDF')
        assert [doc['name'] for doc in data['unassigned_documents']] == ['ohne-einheit.pdf'] and 'Kurseinheit' in by_name['ohne-einheit.pdf']['reason']
        # Same decisions as the preview: every usable file is a source, every other file carries the preview's reason.
        assert {doc['path'] for doc in by_name.values() if doc['usable']} == {item['path'] for item in plan['sources']}
        assert {item['path']: item['reason'] for item in plan['skipped']} == \
            {doc['path']: doc['reason'] for doc in by_name.values() if not doc['usable']}


def test_overview_counts_drafts_and_published_lessons_of_the_demo_module():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            data = client.get('/api/module-import/overview', params={'module_id': 'M-10001'}).json()
            assert data['has_learning_pages'] is True and data['draft'] is False
            assert [(item['unit'], item['draft_lessons'], item['published_lessons'], [doc['usable'] for doc in item['documents']])
                    for item in data['units']] == [(1, 0, 2, [True]), (2, 0, 2, [True])]
            assert [(doc['name'], doc['usable']) for doc in data['unassigned_documents']] == [('10001-uebungsarbeit-1-demo.pdf', False)]
            assert data['unassigned_documents'][0]['reason']
            full = json.loads((project / FILE).read_text(encoding='utf-8'))
            draft = copy.deepcopy(full)
            draft['lessons'] = [lesson for lesson in full['lessons'] if lesson['unit'] == 2][:1]
            _write(project / DRAFT, draft)
            data = client.get('/api/module-import/overview', params={'module_id': 'M-10001'}).json()
            assert data['draft'] is True
            assert [(item['unit'], item['draft_lessons'], item['published_lessons']) for item in data['units']] == [(1, 0, 2), (2, 1, 2)]
            assert client.get('/api/module-import/overview', params={'module_id': 'M-99999'}).status_code == 404
