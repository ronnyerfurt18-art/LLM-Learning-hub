"""Development branch: the model drafts a work order, the hub proves files, decides the route and writes the handover prompt."""
import copy
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend import development
from backend.development import (
    DEFAULT_RULES, INSTRUCTIONS, SCHEMA, architecture_excerpt, build_order, decide_route, file_index, handover_prompt,
    index_text, messages_for, project_rules, related_tests,
)
from backend.main import create_app
from backend.tutor import TutorService

TEXT = 'Im Lernchat soll unter jeder Antwort stehen, wie lange das KI-Modell dafür gebraucht hat.'
SECRET = 'GEHEIMER-LERNINHALT-4711'


def _project(root):
    """A small program folder with the kinds of files the index must show and must leave out."""
    files = {
        'backend/tutor.py': '"""Tutor service: one bounded model call per turn."""\nSECRET_IN_CODE = 1\n',
        'backend/planner.py': 'from __future__ import annotations\n"""Planner facts."""\n',
        'backend/plain.py': 'x = 1\n',
        'backend/tutor 2.py': '"""Cloud duplicate."""\n',
        'backend/.hidden.py': '"""Hidden."""\n',
        'backend/notes.txt': 'kein Programm',
        'frontend/src/LearningTutor.tsx': 'export function LearningTutor() {}\nexport default function Other() {}\n',
        'frontend/src/api.ts': 'export async function api() {}\n',
        'frontend/src/styles.css': 'a{}\n',
        'tests/test_tutor.py': '"""Tutor tests."""\n',
        'tests/test_other.py': '',
        'tools/bench.py': '"""Messskript."""\n',
        'docs/lernchat.md': '# Lernchat\n\nText\n',
        'launcher.py': '"""Launcher."""\n',
        'README.md': '# Learning Hub\n',
        'content/lernseiten.json': '{"text": "' + SECRET + '"}',
        'imports/fragen.json': '{"text": "' + SECRET + '"}',
        'data/notiz.md': SECRET,
        'tutor.local.json': '{"model": "' + SECRET + '"}',
        'logs/Architekturlog.md': '# Architekturlog\n\nVorwort\n\n## 1. Stränge\n\nEins\n\n## 2. Grundsätze\n\n1. Das Modell schreibt keinen Zustand.\n\n'
                                  '## 3. Aufbau in Schichten\n\nBrowser, Server, SQLite\n\n## 4. Entscheidungen\n\nViele Einträge\n',
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _raw(**changes):
    value = {'title': 'Antwortzeit im Lernchat zeigen', 'goal': 'Unter jeder Antwort steht die Dauer. Das hilft beim Vergleich von KI-Modellen.',
             'files': [{'path': 'backend/tutor.py', 'change': 'Dauer messen und mitliefern.', 'new': False}],
             'steps': ['Dauer im Server messen.', 'Dauer in der Antwort mitliefern.'],
             'acceptance': ['Steht unter jeder Antwort eine Dauer in Sekunden?'],
             'risks': ['Die Messung verfälscht das Streaming.'], 'questions': [], 'size': 'klein', 'reason': 'Eine Datei.'}
    value.update(changes)
    return value


def _request(**changes):
    value = {'id': 'E-001', 'title': 'Antwortzeit', 'text': TEXT, 'note': '', 'status': 'new', 'order': None, 'error': ''}
    value.update(changes)
    return value


# --- file index ---------------------------------------------------------------------------------------------------------

def test_index_lists_the_program_and_nothing_else(tmp_path):
    index = file_index(_project(tmp_path))
    assert [entry['path'] for entry in index] == [
        'backend/plain.py', 'backend/planner.py', 'backend/tutor.py', 'frontend/src/LearningTutor.tsx', 'frontend/src/api.ts',
        'frontend/src/styles.css', 'tools/bench.py', 'tests/test_other.py', 'tests/test_tutor.py', 'docs/lernchat.md',
        'launcher.py', 'README.md']
    about = {entry['path']: entry['about'] for entry in index}
    assert about['backend/tutor.py'] == 'Tutor service: one bounded model call per turn.'
    assert about['backend/planner.py'] == 'Planner facts.'  # a __future__ import may precede the docstring
    assert about['backend/plain.py'] == '' and about['frontend/src/styles.css'] == ''
    assert about['frontend/src/LearningTutor.tsx'] == 'exportiert LearningTutor, Other'
    assert about['docs/lernchat.md'] == 'Lernchat' and about['README.md'] == 'Learning Hub'
    assert {entry['area'] for entry in index} == {'backend', 'frontend', 'tools', 'tests', 'docs', 'root'}


def test_index_skips_links_and_survives_missing_folders(tmp_path):
    project = _project(tmp_path / 'hub')
    outside = tmp_path / 'outside.py'
    outside.write_text('"""Outside."""\n', encoding='utf-8')
    os.symlink(outside, project / 'backend' / 'linked.py')
    assert 'backend/linked.py' not in [entry['path'] for entry in file_index(project)]
    assert file_index(tmp_path / 'leer') == []


def test_index_text_leaves_tests_out_and_shortens_descriptions_before_files(tmp_path):
    index = file_index(_project(tmp_path))
    full = index_text(index)
    assert 'tests/' not in full and 'backend/tutor.py – Tutor service: one bounded model call per turn.' in full
    assert 'docs/lernchat.md – Lernchat' in full
    tight = index_text(index, 190)
    assert len(tight) <= 190 and ' – ' not in tight
    assert [line for line in tight.splitlines()] == [entry['path'] for entry in index if entry['area'] != 'tests']
    many = [{'path': f'backend/modul_{number:03d}.py', 'area': 'backend', 'about': 'x' * 100} for number in range(300)]
    cut = index_text(many, 2000)
    assert len(cut) <= 2000 and cut.splitlines()[0] == 'backend/modul_000.py' and 'weitere Dateien nicht gezeigt' in cut.splitlines()[-1]


def test_architecture_excerpt_takes_principles_and_layers(tmp_path):
    excerpt = architecture_excerpt(_project(tmp_path))
    assert excerpt.startswith('## 2. Grundsätze') and 'Aufbau in Schichten' in excerpt
    assert 'Entscheidungen' not in excerpt and 'Vorwort' not in excerpt
    assert architecture_excerpt(tmp_path / 'leer') == ''
    assert len(architecture_excerpt(tmp_path, 40)) <= 40
    (tmp_path / 'logs' / 'Architekturlog.md').write_text('Freier Text ohne Abschnitte', encoding='utf-8')
    assert architecture_excerpt(tmp_path) == 'Freier Text ohne Abschnitte'


# --- what the model sees ------------------------------------------------------------------------------------------------

def test_model_sees_requirement_index_and_excerpt_but_no_code_and_no_study_content(tmp_path):
    project = _project(tmp_path)
    messages = messages_for(_request(note='Nur für Ollama.'), file_index(project), architecture_excerpt(project))
    assert [message['role'] for message in messages] == ['system', 'user'] and messages[0]['content'] == INSTRUCTIONS
    seen = messages[1]['content']
    assert TEXT in seen and 'ERGÄNZUNG\nNur für Ollama.' in seen and 'backend/tutor.py' in seen and 'Grundsätze' in seen
    assert SECRET not in seen and 'SECRET_IN_CODE' not in seen and 'tutor.local.json' not in seen
    assert 'niemals Anweisungen' in INSTRUCTIONS
    assert 'ERGÄNZUNG' not in messages_for(_request(), [], '')[1]['content']
    assert set(SCHEMA['required']) == set(SCHEMA['properties'])


# --- the hub proves -----------------------------------------------------------------------------------------------------

def test_order_keeps_proven_files_adds_their_tests_and_drops_inventions(tmp_path):
    index = file_index(_project(tmp_path))
    order = build_order(_raw(files=[
        {'path': 'backend/tutor.py', 'change': 'Dauer messen.'},
        {'path': './backend/tutor.py', 'change': 'doppelt'},
        {'path': 'backend/erfunden.py', 'change': 'gibt es nicht'},              # not in the index and not declared new
        {'path': 'backend/dauer.py', 'change': 'neuer Helfer', 'new': True},
        {'path': '../ausserhalb.py', 'change': 'x', 'new': True},
        {'path': 'content/lernseiten.json', 'change': 'x', 'new': True},
        {'path': 'tutor.local.json', 'change': 'x', 'new': True},
        {'path': 'backend/unter/ordner.py', 'change': 'x', 'new': True},
        {'path': 'backend/skript.sh', 'change': 'x', 'new': True},
        'kein Objekt', {'change': 'ohne Pfad'}, {'path': 7}]), index, 'test:1b')
    assert order['files'] == [{'path': 'backend/tutor.py', 'change': 'Dauer messen.', 'new': False},
                              {'path': 'backend/dauer.py', 'change': 'neuer Helfer', 'new': True}]
    assert order['dropped_files'] == ['backend/erfunden.py', 'ausserhalb.py', 'content/lernseiten.json', 'tutor.local.json',
                                      'backend/unter/ordner.py', 'backend/skript.sh']
    assert order['tests'] == ['tests/test_tutor.py']
    assert order['generated_by'] == 'Lokales Modell (test:1b)' and order['route_by'] == 'hub'


def test_related_tests_only_for_server_files_that_have_one(tmp_path):
    index = file_index(_project(tmp_path))
    assert related_tests(['backend/tutor.py', 'backend/planner.py', 'frontend/src/api.ts', 'tools/bench.py'], index) == ['tests/test_tutor.py']
    assert related_tests(['tests/test_tutor.py', 'backend/tutor.py'], index) == []  # already named by the model


@pytest.mark.parametrize('changes, missing', [({'title': ' '}, 'title'), ({'goal': None}, 'goal'), ({'steps': []}, 'steps'),
                                              ({'acceptance': ['', 3]}, 'acceptance'), ({'steps': 'ein Text'}, 'steps')])
def test_order_without_required_content_is_refused(tmp_path, changes, missing):
    with pytest.raises(ValueError, match=missing):
        build_order(_raw(**changes), file_index(_project(tmp_path)), 'test')


def test_order_is_bounded_and_cleaned(tmp_path):
    order = build_order(_raw(steps=[f'Schritt {number}' for number in range(40)] + ['Schritt 1'], risks=['a\x00b', 'a\x00b', 'x' * 900],
                             questions='keine Liste', size='riesig', title='T' * 300, reason=5), file_index(_project(tmp_path)), 'test')
    assert len(order['steps']) == 12 and len(order['title']) == development.TITLE_CHARS
    assert order['risks'][0] == 'ab' and len(order['risks']) == 2 and len(order['risks'][1]) == development.ITEM_CHARS
    assert order['questions'] == [] and order['size'] == 'mittel' and order['reason'] == ''
    assert order['route'] == 'external'  # an unknown size never counts as small


def test_route_is_local_only_for_a_small_change_in_one_place():
    one = [{'path': 'backend/tutor.py', 'change': '', 'new': False}]
    assert decide_route('klein', one) == ('local', ['Kleine, abgegrenzte Änderung an 1 Datei in einem Bereich.'])
    with_test = one + [{'path': 'backend/quality.py', 'change': '', 'new': False}, {'path': 'tests/test_tutor.py', 'change': '', 'new': False},
                       {'path': 'docs/lernchat.md', 'change': '', 'new': False}]
    assert decide_route('klein', with_test)[0] == 'local'  # tests and documents do not count as program files
    cases = {
        'mittel': (one, 'schätzt den Umfang als „mittel“'), 'gross': (one, 'schätzt den Umfang als „groß“'),
        'klein-viele': ([{'path': f'backend/{name}.py', 'change': '', 'new': False} for name in 'abc'], '3 Programmdateien'),
        'klein-beide': (one + [{'path': 'frontend/src/api.ts', 'change': '', 'new': False}], 'Server und Oberfläche zugleich'),
        'klein-neu': ([{'path': 'backend/neu.py', 'change': '', 'new': True}], 'neue Dateien'),
        'klein-leer': ([], 'Keine der genannten Dateien'),
    }
    for size, (files, reason) in cases.items():
        route, reasons = decide_route(size.split('-')[0], files)
        assert route == 'external' and any(reason in item for item in reasons), size
    route, reasons = decide_route('gross', cases['klein-beide'][0] + cases['klein-neu'][0] + cases['klein-viele'][0])
    assert route == 'external' and len(reasons) == 4  # every reason against the local way is named


# --- handover prompt ----------------------------------------------------------------------------------------------------

def test_prompt_carries_request_order_and_rules_and_no_study_content(tmp_path):
    project = _project(tmp_path)
    order = build_order(_raw(questions=['Soll die Dauer auch bei Bonsai erscheinen?']), file_index(project), 'test')
    prompt = handover_prompt(_request(order=order, note='Nur Sekunden, keine Millisekunden.'), project)
    for expected in (f'Projektordner auf diesem Rechner: `{project}`', '## Auftrag E-001: Antwortzeit', TEXT, '### Ergänzung\nNur Sekunden',
                     '### Ziel\nUnter jeder Antwort steht die Dauer.', '- `backend/tutor.py`: Dauer messen und mitliefern.',
                     '### Zugehörige Tests\n- `tests/test_tutor.py`', '1. Dauer im Server messen.\n2. Dauer in der Antwort mitliefern.',
                     '### Abnahmekriterien\n- Steht unter jeder Antwort', '### Risiken\n- Die Messung',
                     'Kläre diese Punkte mit mir, bevor du etwas änderst:\n- Soll die Dauer auch bei Bonsai',
                     'Prüfe sie am Quelltext', '### Regeln des Projekts\n' + DEFAULT_RULES, 'pytest -q', 'gehören in keinen Commit'):
        assert expected in prompt, expected
    assert SECRET not in prompt and 'SECRET_IN_CODE' not in prompt
    assert '### Offene Fragen' not in handover_prompt(_request(order=build_order(_raw(), file_index(project), 'test')), project)


def test_prompt_without_order_asks_for_a_plan_first(tmp_path):
    prompt = handover_prompt(_request(), _project(tmp_path))
    assert TEXT in prompt and 'noch keinen ausgearbeiteten Auftrag' in prompt and 'warte auf meine Zustimmung' in prompt
    assert '### Ziel' not in prompt and '### Schritte' not in prompt and '### Regeln des Projekts' in prompt


def test_rules_come_from_the_project_file_when_it_has_content(tmp_path):
    assert project_rules(tmp_path) == (DEFAULT_RULES, 'Standardregeln des Hubs')
    rules = tmp_path / 'docs' / 'entwicklungsregeln.md'
    rules.parent.mkdir()
    rules.write_text('# Regeln\n\n', encoding='utf-8')
    assert project_rules(tmp_path)[1] == 'Standardregeln des Hubs'  # a heading alone is no rule
    rules.write_text('# Regeln\n\n- Keine neuen Abhängigkeiten.\n- Erst fragen.\n', encoding='utf-8')
    assert project_rules(tmp_path) == ('- Keine neuen Abhängigkeiten.\n- Erst fragen.', 'docs/entwicklungsregeln.md')
    assert '- Keine neuen Abhängigkeiten.' in handover_prompt(_request(), tmp_path) and DEFAULT_RULES not in handover_prompt(_request(), tmp_path)
    rules.write_text('# Regeln\n\n' + '- Regel\n' * 2000, encoding='utf-8')
    assert len(project_rules(tmp_path)[0]) <= development.RULES_CHARS


# --- API ----------------------------------------------------------------------------------------------------------------

@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.delenv('MLH_FEATURES', raising=False)
    study, project = tmp_path / 'Studium', _project(tmp_path / 'hub')
    study.mkdir()
    app = create_app(study, project / 'data', project, start_watch=False)
    app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test:1b'}, lambda request: {})
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.app_, client.project, client.study = app, project, study
        yield client


def _finish(client):
    for _ in range(400):
        job = client.get('/api/development').json()['job']
        if job['state'] != 'running':
            return job
        time.sleep(0.02)
    raise AssertionError('Der Auftrag wurde nicht fertig.')


def _draft(client, request_id, answer):
    seen = []

    def generate(messages, structured=True):
        seen.append((messages, structured))
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)
    client.app_.state.development_generate = generate
    started = client.post(f'/api/development/requests/{request_id}/order')
    assert started.status_code == 202, started.text
    return _finish(client), seen


def test_request_is_stored_listed_and_comes_with_a_prompt(hub):
    empty = hub.get('/api/development').json()
    assert empty == {'requests': [], 'job': {'state': 'idle', 'message': ''}, 'model_available': True, 'model_message': '',
                     'rules_source': 'Standardregeln des Hubs'}
    created = hub.post('/api/development/requests', json={'text': '  ' + TEXT + '\n\nZweiter Absatz.  '})
    assert created.status_code == 201, created.text
    first = created.json()
    assert (first['id'], first['status'], first['order'], first['error'], first['note']) == ('E-001', 'new', None, '', '')
    assert first['text'] == TEXT + '\n\nZweiter Absatz.' and first['title'] == TEXT[:69].rstrip() + '…' and first['title_auto'] is True
    assert TEXT in first['prompt'] and 'noch keinen ausgearbeiteten Auftrag' in first['prompt']
    second = hub.post('/api/development/requests', json={'text': TEXT, 'title': 'Antwortzeit', 'note': 'eilt nicht'}).json()
    assert (second['id'], second['title'], second['title_auto'], second['note']) == ('E-002', 'Antwortzeit', False, 'eilt nicht')
    listed = hub.get('/api/development').json()['requests']
    assert [(item['id'], item['status'], item['has_order'], item['route']) for item in listed] == [('E-002', 'new', False, None), ('E-001', 'new', False, None)]
    assert hub.get('/api/development/requests/E-001').json() == first
    assert hub.get('/api/development/requests/E-999').status_code == 404
    # Stored in the database: a hub started later on the same data sees the same requests.
    again = create_app(hub.study, hub.project / 'data', hub.project, start_watch=False)
    with TestClient(again, base_url='http://127.0.0.1') as other:
        assert [item['id'] for item in other.get('/api/development').json()['requests']] == ['E-002', 'E-001']


@pytest.mark.parametrize('body', [{}, {'text': 'zu kurz'}, {'text': 'x' * 4001}, {'text': 5}, {'text': TEXT, 'status': 'done'},
                                  {'text': TEXT, 'title': 'T' * 121}, {'text': TEXT, 'title': 3}, {'text': TEXT, 'note': 'n' * 2001},
                                  {'text': '\x00\x01 \x02' * 20}])
def test_malformed_request_is_refused_and_nothing_is_stored(hub, body):
    answer = hub.post('/api/development/requests', json=body)
    assert answer.status_code == 400 and isinstance(answer.json()['detail'], str)
    assert hub.get('/api/development').json()['requests'] == []


def test_title_note_and_status_can_change_but_not_the_requirement(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    patched = hub.patch('/api/development/requests/E-001', json={'title': 'Dauer zeigen', 'note': 'Nur Ollama.', 'status': 'handed_over'}).json()
    assert (patched['title'], patched['title_auto'], patched['note'], patched['status'], patched['text']) == ('Dauer zeigen', False, 'Nur Ollama.', 'handed_over', TEXT)
    assert '### Ergänzung\nNur Ollama.' in patched['prompt'] and 'E-001: Dauer zeigen' in patched['prompt']
    assert hub.get('/api/development').json()['requests'][0]['status'] == 'handed_over'
    for bad in ({}, {'text': TEXT + ' anders'}, {'status': 'fertig'}, {'title': ''}, {'title': 'T' * 121}, {'note': 4}, {'note': 'n' * 2001},
                {'route': 'local'}, {'route': 'cloud'}):
        answer = hub.patch('/api/development/requests/E-001', json=bad)
        assert answer.status_code == 400, bad
    assert hub.patch('/api/development/requests/E-404', json={'status': 'done'}).status_code == 404
    assert hub.get('/api/development/requests/E-001').json() == patched


def test_model_drafts_the_order_and_the_hub_files_it(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    job, seen = _draft(hub, 'E-001', _raw(files=[{'path': 'backend/tutor.py', 'change': 'Dauer messen.'}, {'path': 'backend/erfunden.py', 'change': 'x'}]))
    assert job['state'] == 'done' and job['request_id'] == 'E-001' and job['model'] == 'test:1b'
    assert job['message'] == 'Auftrag ausgearbeitet: 1 Dateien, 2 Schritte, eingestuft als lokal machbar.'
    assert len(seen) == 1 and seen[0][1] is True and TEXT in seen[0][0][1]['content'] and SECRET not in seen[0][0][1]['content']
    detail = hub.get('/api/development/requests/E-001').json()
    assert detail['status'] == 'drafted' and detail['title'] == 'Antwortzeit im Lernchat zeigen' and detail['error'] == ''
    order = detail['order']
    assert [item['path'] for item in order['files']] == ['backend/tutor.py'] and order['dropped_files'] == ['backend/erfunden.py']
    assert (order['route'], order['route_by'], order['tests']) == ('local', 'hub', ['tests/test_tutor.py'])
    assert '### Ziel' in detail['prompt'] and 'backend/erfunden.py' not in detail['prompt']
    assert hub.get('/api/development').json()['requests'][0] | {'updated_at': ''} == {
        'id': 'E-001', 'title': 'Antwortzeit im Lernchat zeigen', 'status': 'drafted', 'created_at': detail['created_at'],
        'updated_at': '', 'has_order': True, 'route': 'local'}
    # The person may overrule the hub's route; the order itself stays.
    moved = hub.patch('/api/development/requests/E-001', json={'route': 'external'}).json()['order']
    assert (moved['route'], moved['route_by'], moved['steps']) == ('external', 'user', order['steps'])


def test_a_title_the_person_wrote_and_a_later_status_survive_a_new_draft(hub):
    hub.post('/api/development/requests', json={'text': TEXT, 'title': 'Mein Titel'})
    _draft(hub, 'E-001', _raw())
    hub.patch('/api/development/requests/E-001', json={'status': 'handed_over'})
    job, _ = _draft(hub, 'E-001', _raw(goal='Neues Ziel.', size='gross'))
    detail = hub.get('/api/development/requests/E-001').json()
    assert job['state'] == 'done' and (detail['title'], detail['status']) == ('Mein Titel', 'handed_over')
    assert detail['order']['goal'] == 'Neues Ziel.' and detail['order']['route'] == 'external'


def test_failed_draft_is_reported_and_keeps_the_earlier_order(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    job, seen = _draft(hub, 'E-001', _raw(steps=[]))
    assert job['state'] == 'error' and 'Pflichtfelder nicht geliefert: steps' in job['message']
    detail = hub.get('/api/development/requests/E-001').json()
    assert detail['order'] is None and detail['status'] == 'new' and detail['error'] == job['message']
    _draft(hub, 'E-001', _raw())
    job, seen = _draft(hub, 'E-001', ValueError('Kein JSON-Objekt in der Antwort.'))
    assert job['state'] == 'error' and job['message'] == 'Keine verwertbare Antwort des KI-Modells: Kein JSON-Objekt in der Antwort.'
    assert [structured for _, structured in seen] == [True, False]  # one more try without the schema
    detail = hub.get('/api/development/requests/E-001').json()
    assert detail['order']['title'] == 'Antwortzeit im Lernchat zeigen' and detail['status'] == 'drafted' and detail['error'] == job['message']
    job, _ = _draft(hub, 'E-001', OSError('weg'))
    assert job['message'] == 'Ollama ist nicht erreichbar oder hat nicht rechtzeitig geantwortet.'
    job, _ = _draft(hub, 'E-001', _raw())
    assert job['state'] == 'done' and hub.get('/api/development/requests/E-001').json()['error'] == ''


def test_schema_refusal_falls_back_to_the_plain_prompt(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    calls = []

    def generate(messages, structured=True):
        calls.append(structured)
        if structured:
            raise ValueError('Schema nicht unterstützt')
        return _raw()
    hub.app_.state.development_generate = generate
    assert hub.post('/api/development/requests/E-001/order').status_code == 202
    assert _finish(hub)['state'] == 'done' and calls == [True, False]


def test_only_one_draft_at_a_time_and_it_waits_for_the_model(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    hub.post('/api/development/requests', json={'text': TEXT + ' Zweite Anforderung.'})
    entered, release = threading.Event(), threading.Event()

    def generate(messages, structured=True):
        entered.set()
        assert release.wait(10)
        return _raw()
    hub.app_.state.development_generate = generate
    gate = hub.app_.state.tutor._generation
    gate.acquire()  # the learning chat is answering
    try:
        assert hub.post('/api/development/requests/E-001/order').json()['state'] == 'running'
        busy = hub.post('/api/development/requests/E-002/order')
        assert busy.status_code == 409 and 'bereits ein Auftrag' in busy.json()['detail']
        assert not entered.wait(0.3)  # no model call while the chat holds the model
    finally:
        gate.release()
    assert entered.wait(10)
    assert not gate.acquire(blocking=False)  # now the draft holds it
    release.set()
    assert _finish(hub)['state'] == 'done'
    assert gate.acquire(blocking=False)
    gate.release()
    assert hub.get('/api/development/requests/E-002').json()['order'] is None


def test_without_local_ollama_requests_and_prompt_still_work(hub):
    hub.app_.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'none'}, lambda request: {})
    overview = hub.get('/api/development').json()
    assert overview['model_available'] is False and 'Übergabe-Prompt kannst du auch ohne Auftrag' in overview['model_message']
    created = hub.post('/api/development/requests', json={'text': TEXT})
    assert created.status_code == 201 and TEXT in created.json()['prompt']
    refused = hub.post('/api/development/requests/E-001/order')
    assert refused.status_code == 503 and refused.json()['detail'] == overview['model_message']
    assert hub.post('/api/development/requests/E-404/order').status_code == 404
    assert hub.get('/api/development').json()['job']['state'] == 'idle'


def test_nothing_in_the_project_or_study_folder_is_written(hub):
    def tree(root):
        return sorted((path.relative_to(root).as_posix(), path.stat().st_size) for path in root.rglob('*')
                      if path.is_file() and 'data' not in path.relative_to(root).parts[:1])
    before = tree(hub.project), tree(hub.study)
    hub.post('/api/development/requests', json={'text': TEXT})
    _draft(hub, 'E-001', _raw(files=[{'path': 'backend/neu.py', 'change': 'neu', 'new': True}]))
    hub.patch('/api/development/requests/E-001', json={'status': 'done', 'note': 'erledigt'})
    assert (tree(hub.project), tree(hub.study)) == before
