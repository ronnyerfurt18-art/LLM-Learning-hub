"""Visible module metadata is optional; identity, drafts and publishing remain reliable."""
import copy
import json
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from backend.big_picture import draft_path as picture_path
from backend.content_files import find_package
from backend.learning_pages import load_learning_pages, module_id_for_package, validate_learning_page
from backend.module_import import build_package, draft_path
from test_module_import import ANSWER, _documents, _setup
from test_publish_overview import _demo, FILE, _write
from test_big_picture import _answer


@pytest.mark.parametrize('number', ['', 'BIO-1', 'Kurs / Einführung 2026', '../außerhalb'])
def test_optional_freeform_identifier_roundtrip_and_rename(number):
    with TemporaryDirectory() as directory:
        source, project, app, unused = _setup(directory)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            response = client.post('/api/modules', json={'name': 'Freies Thema', 'number': number, 'unit_label': 'Themenblock'})
            assert response.status_code == 200, response.text
            module = response.json()
            mid = module['id']
            assert module['unit_label'] == 'Themenblock'
            assert '/' not in mid
            _documents(app.state.hub, mid)
            job = app.state.module_import
            state = job.run(mid, [1], 'test', lambda *args: copy.deepcopy(ANSWER))
            assert state['state'] == 'done', state
            assert state['outputs']['draft_errors'] == []
            draft = project / state['outputs']['draft']
            assert draft.parent == project / 'imports' / 'entwuerfe'
            assert json.loads(draft.read_text())['module_id'] == mid
            # Editing before publication keeps the same draft, even when both display fields change.
            response = client.patch('/api/modules/' + mid, json={'number': 'Mein Kurs / A', 'name': 'Neuer Titel'})
            assert response.status_code == 200, response.text
            assert draft_path(project, response.json()) == draft
            published = client.post('/api/module-import/publish', json={'module_id': mid})
            assert published.status_code == 200, published.text
            result = client.get('/api/learning-pages/' + mid)
            assert result.status_code == 200, result.text
            assert result.json()['module_number'] == 'Mein Kurs / A'
            assert result.json()['module_title'] == 'Neuer Titel'
            before = result.json()['lessons']
            assert client.patch('/api/modules/' + mid, json={'number': '', 'name': 'Ohne Nummer'}).status_code == 200
            result = client.get('/api/learning-pages/' + mid)
            assert result.status_code == 200, result.text
            assert result.json()['lessons'] == before and result.json()['module_number'] == ''
            assert app.state.big_picture.lessons_of(app.state.hub.module(mid))[1] == before


def test_two_numberless_modules_stay_separate_and_stale_numbers_do_not_reassign_them():
    with TemporaryDirectory() as directory:
        source, project, app, _ = _setup(directory)
        hub = app.state.hub
        modules = [hub.add_module({'name': title}) for title in ['Personal', 'Anderes Fach']]
        for module in modules:
            _documents(hub, module['id'])
            state = app.state.module_import.run(module['id'], [1], 'test', lambda *args: copy.deepcopy(ANSWER))
            assert state['outputs']['draft_errors'] == []
            app.state.module_import.publish(module['id'])
        packages, errors = load_learning_pages(project, source)
        assert not errors and len(packages) == 2
        for module in modules:
            _, package = find_package(project, module)
            assert package['module_id'] == module['id']
            assert module_id_for_package(package, hub.modules()) == module['id']
        assert draft_path(project, modules[0]) != draft_path(project, modules[1])
        assert picture_path(project, modules[0]) != picture_path(project, modules[1])
        # A stable id may not silently fall back to another module's visible number.
        assert module_id_for_package({'module_id': 'deleted', 'module_number': '32711'}, hub.modules()) is None


def test_existing_numberless_personal_draft_publishes_without_regeneration():
    with TemporaryDirectory() as directory:
        source, project, app, _ = _setup(directory)
        hub = app.state.hub
        module = hub.add_module({'name': 'Personal'})
        _documents(hub, module['id'])
        state = app.state.module_import.run(module['id'], [1], 'test', lambda *args: copy.deepcopy(ANSWER))
        current = project / state['outputs']['draft']
        package = json.loads(current.read_text())
        package.pop('module_id')
        package['module_number'] = ''
        current.unlink()
        legacy = project / 'imports/entwuerfe/personal-learning-pages.json'
        _write(legacy, package)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            overview = client.get('/api/module-import/overview', params={'module_id': module['id']}).json()
            assert overview['draft_errors'] == [] and overview['draft']
            result = client.post('/api/module-import/publish', json={'module_id': module['id']})
            assert result.status_code == 200, result.text
            served = client.get('/api/learning-pages/' + module['id']).json()
            assert served['lessons'] == package['lessons']
            assert served['module_number'] == ''


def test_editing_legacy_module_keeps_big_picture_draft_and_publication():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        mid = 'M-10001'
        job = app.state.big_picture
        with TestClient(app, base_url='http://127.0.0.1') as client:
            job.run(mid, 'test', lambda *args: _answer())
            assert job.status()['state'] == 'done', job.status()
            legacy = project / 'imports/entwuerfe/10001-big-picture.json'
            block = json.loads(legacy.read_text())
            block.pop('module_id')
            _write(legacy, block)
            result = client.patch('/api/modules/' + mid, json={'number': '', 'name': 'Freies Lernen'})
            assert result.status_code == 200, result.text
            assert job.read_draft(result.json())['title'] == block['title']
            assert job.publish(mid, replace=True)['replaced']
            result = client.get('/api/learning-pages/' + mid)
            assert result.status_code == 200, result.text
            assert result.json()['module_number'] == ''
            assert result.json()['overview']['big_picture']['title'] == block['title']


def test_absent_metadata_does_not_disable_source_validation():
    with TemporaryDirectory() as directory:
        project, app = _demo(directory)
        package = json.loads((project / FILE).read_text())
        package.pop('module_number')
        package['module_id'] = 'M-10001'
        assert not validate_learning_page(package, app.state.module_import.source, project)
        package['lessons'][0]['sections'][0]['sources'][0]['path'] = '../outside.pdf'
        assert validate_learning_page(package, app.state.module_import.source, project)
