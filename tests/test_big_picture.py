"""Big picture: the model drafts, the hub proves; draft, publishing and staleness."""
import copy
import json
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from backend import big_picture
from backend.big_picture import SCHEMA, build_block, lesson_digest, block_errors
from backend.learning_pages import validate_learning_page
from backend.local_generation import ollama_generator
from backend.tutor import TutorService
from test_publish_overview import DRAFT, FILE, _demo, _write

IDS = ['ll-abrufuebung', 'll-verteilt', 'll-techniken', 'll-lernplan']
BLOCK = 'imports/entwuerfe/10001-big-picture.json'


def _answer(**changes):
    value = {
        'title': 'Vom Lesen zum Plan', 'central_question': 'Wie bleibt Gelerntes haften?',
        'intro': 'Drei Bausteine greifen ineinander.', 'takeaway': 'Abrufen, verteilen, planen.',
        'nodes': [{'title': 'Aktiv abrufen', 'summary': 'Wissen aus dem Gedächtnis holen.', 'role': 'Wirksamste Technik.', 'lesson_ids': [IDS[0]]},
                  {'title': 'Abstände nutzen', 'summary': 'Wiederholen mit wachsendem Abstand.', 'role': 'Hält Wissen.', 'lesson_ids': [IDS[1], IDS[0]]},
                  {'title': 'Plan aufstellen', 'summary': 'Termine festlegen.', 'role': 'Sorgt für Regelmäßigkeit.', 'lesson_ids': [IDS[3]]}],
        'connections': [{'from': 1, 'to': 2, 'label': 'wird mit Abstand wiederholt'}, {'from': 2, 'to': 3, 'label': 'gibt Termine vor'}]}
    value.update(changes)
    return value


def _setup(directory, picture=False):
    """Demo module with online tutor; the published pages carry a big picture only if asked."""
    project, app = _demo(directory)
    published = json.loads((project / FILE).read_text(encoding='utf-8'))
    if not picture:
        del published['overview']['big_picture']
        _write(project / FILE, published)
    app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, lambda request: {})
    return project, app, published


def _client(app):
    return TestClient(app, base_url='http://127.0.0.1')


def _finish(client, module='M-10001'):
    for _ in range(300):
        info = client.get('/api/big-picture', params={'module_id': module}).json()
        if info['state'] != 'running':
            return info
        time.sleep(0.02)
    raise AssertionError('Big Picture wurde nicht fertig.')


def _run(client, app, answer):
    seen = []

    def generate(messages, structured=True):
        seen.append(messages)
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)
    app.state.big_picture_generate = generate
    started = client.post('/api/big-picture', json={'module_id': 'M-10001'})
    assert started.status_code == 202, started.text
    return _finish(client), seen


def test_valid_draft_is_built_proved_and_never_published_by_itself():
    with TemporaryDirectory() as directory:
        project, app, published = _setup(directory)
        before = (project / FILE).read_bytes()
        with _client(app) as client:
            empty = client.get('/api/big-picture', params={'module_id': 'M-10001'}).json()
            assert empty == {'state': 'idle', 'message': '', 'draft': None,
                             'published': {'exists': False, 'generated_by': None, 'units': [], 'stale_units': []}}
            info, seen = _run(client, app, _answer())
        assert info['state'] == 'done' and '3 Bausteine, 2 Zusammenhänge' in info['message'], info
        block = info['draft']
        assert json.loads((project / BLOCK).read_text(encoding='utf-8')) == block
        assert [node['id'] for node in block['nodes']] == ['aktiv-abrufen', 'abstaende-nutzen', 'plan-aufstellen']
        assert block['connections'] == [{'from': 'aktiv-abrufen', 'to': 'abstaende-nutzen', 'label': 'wird mit Abstand wiederholt'},
                                        {'from': 'abstaende-nutzen', 'to': 'plan-aufstellen', 'label': 'gibt Termine vor'}]
        assert block['units'] == [1, 2] and block['generated_by'] == 'Lokales Modell (test)'
        # Sources come from the sections of the node's lessons, without duplicates, at most three.
        lessons = {lesson['id']: lesson for lesson in published['lessons']}
        node = block['nodes'][1]
        assert node['lesson_ids'] == [IDS[1], IDS[0]] and len(node['sources']) == 3
        pool = [source for lid in node['lesson_ids'] for section in lessons[lid]['sections'] for source in section['sources']]
        assert all(source in pool for source in node['sources']) and len({json.dumps(s, sort_keys=True) for s in node['sources']}) == 3
        # Nothing was published, and the draft is valid inside the published package.
        assert (project / FILE).read_bytes() == before
        merged = copy.deepcopy(published)
        merged['overview']['big_picture'] = block
        assert validate_learning_page(merged, app.state.big_picture.source, project) == []


def test_the_model_sees_only_ids_titles_summaries_and_goals():
    with TemporaryDirectory() as directory:
        project, app, published = _setup(directory)
        with _client(app) as client:
            _, seen = _run(client, app, _answer())
        assert len(seen) == 1
        user = seen[0][1]['content']
        listing = json.loads(user[user.index('LERNSEITEN (JSON)\n') + len('LERNSEITEN (JSON)\n'):user.index('\nENDE DER LERNSEITEN')])
        assert [set(item) for item in listing] == [{'id', 'unit', 'title', 'summary', 'learning_goals'}] * 4
        assert [item['id'] for item in listing] == IDS
        everything = json.dumps(seen, ensure_ascii=False)
        for forbidden in ('pdf_page', '10001-01-S#1-demo.pdf', 'printed_page', '"sources"', '"chapter"', 'Beleg'):
            assert forbidden not in everything, forbidden
        # Section text is not part of the input either.
        assert published['lessons'][0]['sections'][0]['paragraphs'][0][:60] not in everything


def test_unknown_lessons_self_links_duplicates_and_dangling_links_are_cleaned():
    package = {'lessons': [{'id': 'a', 'unit': 1, 'sections': [{'sources': [{'path': 'x.pdf', 'pdf_page': 1}]}]},
                           {'id': 'b', 'unit': 2, 'sections': [{'sources': [{'path': 'x.pdf', 'pdf_page': 1}, {'path': 'y.pdf', 'pdf_page': 2},
                                                                              {'path': 'z.pdf', 'pdf_page': 3}, {'path': 'w.pdf', 'pdf_page': 4}]}]}]}

    def node(title, ids):
        return {'title': title, 'summary': 's', 'role': 'r', 'lesson_ids': ids}
    raw = _answer(nodes=[node('Erster', ['a', 'a', 'nirgends']), node('Verwaist', ['nirgends']), node('Dritter', ['b']),
                         node('Erster', ['a', 'b']), {'title': 'Ohne Rolle', 'summary': 's', 'role': '', 'lesson_ids': ['a']}, 'kein Objekt'],
                   connections=[{'from': 1, 'to': 1, 'label': 'selbst'}, {'from': 2, 'to': 3, 'label': 'zu verworfenem'},
                                {'from': 3, 'to': 4, 'label': 'gut'}, {'from': 3, 'to': 4, 'label': 'doppelt'},
                                {'from': 4, 'to': 3, 'label': 'Gegenrichtung'}, {'from': 1, 'to': 99, 'label': 'unbekannt'},
                                {'from': '1', 'to': 3, 'label': 'Text statt Zahl'}, {'from': 1, 'to': 3, 'label': '  '},
                                {'from': True, 'to': 3, 'label': 'Wahrheitswert'}, {'from': 1, 'to': 3, 'label': 'ok'}, 7])
    block = build_block(raw, package, 'm')
    assert [(n['id'], n['lesson_ids']) for n in block['nodes']] == [('erster', ['a']), ('dritter', ['b']), ('erster-2', ['a', 'b'])]
    assert block['connections'] == [{'from': 'dritter', 'to': 'erster-2', 'label': 'gut'},
                                    {'from': 'erster-2', 'to': 'dritter', 'label': 'Gegenrichtung'},
                                    {'from': 'erster', 'to': 'dritter', 'label': 'ok'}]
    assert len(block['nodes'][1]['sources']) == 3 and block['nodes'][0]['sources'] == [{'path': 'x.pdf', 'pdf_page': 1}]
    # a (x.pdf p.1) is shared between lessons a and b: listed once.
    assert block['nodes'][2]['sources'][0] == {'path': 'x.pdf', 'pdf_page': 1} and len(block['nodes'][2]['sources']) == 3
    assert block['units'] == [1, 2]


@pytest.mark.parametrize('answer,message', [
    (_answer(nodes=_answer()['nodes'][:2]), 'nur 2 verwertbare Bausteine'),
    (_answer(nodes=[{'title': f'B{n}', 'summary': 's', 'role': 'r', 'lesson_ids': [IDS[0]]} for n in range(8)]), 'höchstens 7'),
    (_answer(nodes=_answer()['nodes'][:2] + [{'title': 'Leer', 'summary': 's', 'role': 'r', 'lesson_ids': ['x']}]), 'nur 2 verwertbare Bausteine'),
    (_answer(connections=[{'from': 1, 'to': 1, 'label': 'selbst'}]), 'Zusammenhang'),
    (_answer(intro=' '), 'Pflichtfelder nicht geliefert: intro'),
    (_answer(nodes='keine Liste'), 'nur 0 verwertbare Bausteine'),
])
def test_unusable_answers_become_a_readable_error_and_no_draft(answer, message):
    with TemporaryDirectory() as directory:
        project, app, _ = _setup(directory)
        with _client(app) as client:
            info, _ = _run(client, app, answer)
        assert info['state'] == 'error' and message in info['message'], info
        assert info['draft'] is None and not (project / BLOCK).exists()


def test_answer_without_json_is_an_error_state_not_a_crash():
    def request(path, body=None, timeout=3):
        if path == '/api/tags':
            return {'models': [{'name': 'test'}]}
        if path == '/api/show':
            return {'capabilities': ['completion']}
        sent.append(body)
        return {'message': {'content': 'Das kann ich leider nicht in JSON ausgeben.'}}
    sent = []
    with TemporaryDirectory() as directory:
        project, app, _ = _setup(directory)
        app.state.big_picture_generate = ollama_generator('test', request, SCHEMA, big_picture.OUTPUT_TOKENS)
        with _client(app) as client:
            assert client.post('/api/big-picture', json={'module_id': 'M-10001'}).status_code == 202
            info = _finish(client)
        assert info['state'] == 'error' and info['message'].startswith('Keine verwertbare Modellantwort: Kein JSON-Objekt')
        assert not (project / BLOCK).exists()
        # Asked with the schema first, then once more with the prompt alone.
        assert [body.get('format') == SCHEMA for body in sent] == [True, False]
        assert sent[0]['options']['num_predict'] == big_picture.OUTPUT_TOKENS


def test_failing_model_and_missing_ollama_are_reported():
    with TemporaryDirectory() as directory:
        project, app, _ = _setup(directory)
        with _client(app) as client:
            info, _ = _run(client, app, ConnectionRefusedError('nope'))
            assert info['state'] == 'error' and 'nicht erreichbar' in info['message']
            info, _ = _run(client, app, RuntimeError('intern'))
            assert info['state'] == 'error' and info['message'] == 'Unerwarteter Fehler: RuntimeError'


def test_start_needs_published_lessons_a_local_model_and_only_one_job():
    with TemporaryDirectory() as directory:
        project, app, _ = _setup(directory)
        other = app.state.hub.add_module({'name': 'Leer', 'number': '31311'})['id']
        gate, release = threading.Event(), threading.Event()

        def slow(messages, structured=True):
            gate.set()
            release.wait(5)
            return _answer()
        with _client(app) as client:
            assert client.post('/api/big-picture', json={'module_id': other}).status_code == 400
            assert 'noch keine Lernseiten veröffentlicht' in client.post('/api/big-picture', json={'module_id': other}).json()['detail']
            assert client.post('/api/big-picture', json={}).status_code == 400
            assert client.post('/api/big-picture', json={'module_id': 'M-00000'}).status_code == 404
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'none'}, lambda request: {})
            assert client.post('/api/big-picture', json={'module_id': 'M-10001'}).status_code == 503
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, lambda request: {})
            app.state.big_picture_generate = slow
            assert client.post('/api/big-picture', json={'module_id': 'M-10001'}).status_code == 202
            assert gate.wait(5)
            busy = client.post('/api/big-picture', json={'module_id': 'M-10001'})
            assert busy.status_code == 409 and 'bereits' in busy.json()['detail']
            # Another module sees no foreign progress.
            assert client.get('/api/big-picture', params={'module_id': other}).json()['state'] == 'idle'
            assert client.get('/api/big-picture', params={'module_id': 'M-10001'}).json()['state'] == 'running'
            release.set()
            assert _finish(client)['state'] == 'done'


def test_job_waits_for_the_model_that_chat_or_import_is_using(monkeypatch):
    with TemporaryDirectory() as directory:
        project, app, _ = _setup(directory)
        monkeypatch.setattr(big_picture, 'GATE_POLL_SECONDS', 0.01)
        monkeypatch.setattr(big_picture, 'GATE_WAIT_SECONDS', 0.05)
        called = []
        app.state.big_picture_generate = lambda messages, structured=True: called.append(1) or _answer()
        with _client(app) as client:
            app.state.tutor._generation.acquire()
            client.post('/api/big-picture', json={'module_id': 'M-10001'})
            info = _finish(client)
            assert info['state'] == 'error' and 'zu lange belegt' in info['message'] and not called
            app.state.tutor._generation.release()
            assert client.post('/api/big-picture', json={'module_id': 'M-10001'}).status_code == 202
            assert _finish(client)['state'] == 'done' and called
            # The model lock is free again afterwards.
            assert app.state.tutor._generation.acquire(blocking=False)


def test_publish_without_and_with_replace():
    with TemporaryDirectory() as directory:
        project, app, published = _setup(directory)
        with _client(app) as client:
            assert client.post('/api/big-picture/publish', json={'module_id': 'M-10001'}).status_code == 404
            _run(client, app, _answer())
            first = client.post('/api/big-picture/publish', json={'module_id': 'M-10001'})
            assert first.status_code == 200, first.text
            assert first.json() == {'published': FILE, 'replaced': False, 'nodes': 3, 'units': [1, 2]}
            after = json.loads((project / FILE).read_text(encoding='utf-8'))
            assert after['overview']['big_picture']['title'] == 'Vom Lesen zum Plan'
            assert {k: v for k, v in after['overview'].items() if k != 'big_picture'} == published['overview']
            assert after['lessons'] == published['lessons']
            info = client.get('/api/big-picture', params={'module_id': 'M-10001'}).json()
            assert info['published'] == {'exists': True, 'generated_by': 'Lokales Modell (test)', 'units': [1, 2], 'stale_units': []}
            # A second draft does not replace the published picture unless asked.
            _run(client, app, _answer(title='Zweite Fassung'))
            kept, backups = (project / FILE).read_bytes(), sorted((project / 'data' / 'backups').glob('*'))
            refused = client.post('/api/big-picture/publish', json={'module_id': 'M-10001'})
            assert refused.status_code == 409 and 'replace' in refused.json()['detail']
            assert client.post('/api/big-picture/publish', json={'module_id': 'M-10001', 'replace': False}).status_code == 409
            assert client.post('/api/big-picture/publish', json={'module_id': 'M-10001', 'replace': 'ja'}).status_code == 400
            assert (project / FILE).read_bytes() == kept and sorted((project / 'data' / 'backups').glob('*')) == backups
            replaced = client.post('/api/big-picture/publish', json={'module_id': 'M-10001', 'replace': True})
            assert replaced.status_code == 200 and replaced.json()['replaced'] is True
            assert json.loads((project / FILE).read_text(encoding='utf-8'))['overview']['big_picture']['title'] == 'Zweite Fassung'
            # Every published state is kept: the file without picture, the file with the first picture, the first draft.
            names = sorted(path.name for path in (project / 'data' / 'backups').glob('*.json'))
            pages = [json.loads(path.read_text(encoding='utf-8')) for path in sorted((project / 'data' / 'backups').glob('lernen-lernen-*.json'))]
            assert len(names) == 3 and len(pages) == 2 and sum(name.startswith('10001-big-picture-') for name in names) == 1
            assert sorted((page['overview'].get('big_picture') or {}).get('title', '') for page in pages) == ['', 'Vom Lesen zum Plan']


def test_publish_checks_the_combined_package_before_writing():
    with TemporaryDirectory() as directory:
        project, app, _ = _setup(directory)
        with _client(app) as client:
            _run(client, app, _answer())
            block = json.loads((project / BLOCK).read_text(encoding='utf-8'))
            block['nodes'][0]['lesson_ids'] = ['gibt-es-nicht']
            _write(project / BLOCK, block)
            before = (project / FILE).read_bytes()
            refused = client.post('/api/big-picture/publish', json={'module_id': 'M-10001'})
            assert refused.status_code == 400 and 'nichts geschrieben' in refused.json()['detail'] and 'Lernseite nicht vorhanden' in refused.json()['detail']
            assert (project / FILE).read_bytes() == before and not (project / 'data' / 'backups').exists()


def test_stale_units_show_units_published_after_the_big_picture():
    with TemporaryDirectory() as directory:
        project, app, published = _setup(directory)
        # Only unit 1 is published; the big picture is made from it.
        partial = copy.deepcopy(published)
        partial['lessons'] = [lesson for lesson in published['lessons'] if lesson['unit'] == 1]
        partial['overview']['units'] = [unit for unit in published['overview']['units'] if unit['unit'] == 1]
        _write(project / FILE, partial)
        _write(project / DRAFT, published)
        with _client(app) as client:
            only_one = _answer(nodes=[{'title': f'B{n}', 'summary': 's', 'role': 'r', 'lesson_ids': [IDS[n % 2]]} for n in range(3)],
                               connections=[{'from': 1, 'to': 2, 'label': 'a'}])
            _run(client, app, only_one)
            assert client.post('/api/big-picture/publish', json={'module_id': 'M-10001'}).status_code == 200
            assert client.get('/api/big-picture', params={'module_id': 'M-10001'}).json()['published']['stale_units'] == []
            assert client.post('/api/module-import/publish', json={'module_id': 'M-10001'}).json()['added_units'] == [2]
            info = client.get('/api/big-picture', params={'module_id': 'M-10001'}).json()
            assert info['published']['units'] == [1] and info['published']['stale_units'] == [2]
        # A hand-built big picture without `units` is never reported as stale.
        _write(project / FILE, json.loads((Path(__file__).resolve().parents[1] / 'demo' / FILE).read_text(encoding='utf-8')))
        with _client(app) as client:
            info = client.get('/api/big-picture', params={'module_id': 'M-10001'}).json()
            assert info['published'] == {'exists': True, 'generated_by': None, 'units': [], 'stale_units': []}


def test_units_and_generated_by_are_optional_but_checked(tmp_path):
    with TemporaryDirectory() as directory:
        project, app, published = _setup(directory, picture=True)
        source = app.state.big_picture.source
        assert validate_learning_page(published, source, project) == []
        for field, value, text in (('units', [1, 'x'], 'Kurseinheiten'), ('units', 'eins', 'Kurseinheiten'), ('units', [0], 'Kurseinheiten'),
                                   ('generated_by', ' ', 'generated_by'), ('generated_by', 3, 'generated_by')):
            broken = copy.deepcopy(published)
            broken['overview']['big_picture'][field] = value
            errors = validate_learning_page(broken, source, project)
            assert len(errors) == 1 and text in errors[0] and f'big_picture.{field}' in errors[0], (field, value, errors)
        good = copy.deepcopy(published)
        good['overview']['big_picture'].update(units=[1, 2], generated_by='Lokales Modell (x)')
        assert validate_learning_page(good, source, project) == []


def test_digest_stays_within_the_budget_by_shortening_goals():
    lessons = [{'id': f'l{n}', 'unit': 1 + n % 3, 'title': f'Titel {n}', 'summary': 'Zusammenfassung. ' * 6,
                'learning_goals': [f'Lernziel {k} ' + 'sehr ausführlich ' * 15 for k in range(5)]} for n in range(30)]
    full = len(json.dumps(lessons, ensure_ascii=False))
    assert full > big_picture.INPUT_CHARS
    text = lesson_digest(lessons)
    items = json.loads(text)
    assert len(text) <= big_picture.INPUT_CHARS and [item['id'] for item in items] == [f'l{n}' for n in range(30)]
    assert all(item['title'] and item['summary'] and item['learning_goals'] for item in items)
    assert max(len(item['learning_goals']) for item in items) < 5
    small = lessons[:2]
    assert json.loads(lesson_digest(small))[0]['learning_goals'] == [goal.strip() for goal in small[0]['learning_goals']]
    with pytest.raises(ValueError, match='Zu viele Lernseiten'):
        lesson_digest(lessons * 20)
    with pytest.raises(ValueError, match='Zu viele'):
        lesson_digest(lessons, limit=100)
