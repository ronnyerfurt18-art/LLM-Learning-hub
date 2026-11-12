"""Local module import: grounding, pending outputs and explicit publishing."""
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.core import validate_import
from backend.learning_pages import load_learning_pages
from backend.main import create_app
from backend.module_import import locate_quote, page_windows, parse_json, source_kind, _norm
from backend.tutor import TutorService

PAGE_ONE = ('Metadaten beschreiben die Bedeutung und Herkunft von Daten im Data Warehouse. Sie machen '
            'Kennzahlen für Fachanwender verständlich und sind die Grundlage für jede nachvollzieh-\nbare '
            'Auswertung. Technische Metadaten beschreiben Strukturen, fachliche Metadaten beschreiben Bedeutung. ') * 2
PAGE_TWO = ('Das Metadatenmanagement umfasst vier Hauptprozesse, die Erfassung, Pflege, Bereitstellung und '
            'Nutzung der Metadaten organisieren. Ohne gepflegte Historie lassen sich Änderungen fachlicher '
            'Bedeutung später nicht mehr nachvollziehen. ') * 2
ANSWER = {
    'title': 'Metadaten im Data Warehouse', 'summary': 'Was Metadaten sind und wie sie gepflegt werden.',
    'learning_goals': ['Technische und fachliche Metadaten abgrenzen.'],
    'sections': [
        {'title': 'Begriff', 'paragraphs': ['Metadaten erklären Daten.'], 'bullets': [],
         'quote': 'Grundlage für jede nachvollziehbare Auswertung'},
        {'title': 'Ohne Beleg', 'paragraphs': ['Frei formuliert.'], 'bullets': [], 'quote': 'steht so nirgends im Text der Quelle'}],
    'questions': [
        {'type': 'single_choice', 'topic': 'Metadaten', 'question': 'Was beschreiben fachliche Metadaten?',
         'options': ['Strukturen', 'Bedeutung', 'Hardware', 'Lizenzen'], 'correct_answers': [1], 'model_answer': '',
         'explanation': 'Fachliche Metadaten beschreiben Bedeutung.', 'keywords': ['Bedeutung'], 'difficulty': 1,
         'quote': 'Technische Metadaten beschreiben Strukturen, fachliche Metadaten beschreiben Bedeutung.'},
        {'type': 'free_text', 'topic': 'Prozesse', 'question': 'Welche Hauptprozesse umfasst das Metadatenmanagement?',
         'options': [], 'correct_answers': [], 'model_answer': 'Erfassung, Pflege, Bereitstellung und Nutzung.',
         'explanation': 'Die vier Hauptprozesse organisieren den Umgang mit Metadaten.', 'keywords': ['Pflege', 'Nutzung'],
         'difficulty': 9, 'quote': 'umfasst vier Hauptprozesse, die Erfassung, Pflege, Bereitstellung und Nutzung'},
        {'type': 'flashcard', 'topic': 'Erfunden', 'question': 'Wer erfand Metadaten?', 'options': [], 'correct_answers': [],
         'model_answer': 'Niemand Bestimmtes.', 'explanation': 'Nicht belegt.', 'keywords': [], 'difficulty': 1,
         'quote': 'Metadaten wurden im Jahr 1970 von einer Forschergruppe erfunden'},
        {'type': 'single_choice', 'topic': 'Kaputt', 'question': 'Zwei richtige bei Einfachauswahl?',
         'options': ['A', 'B'], 'correct_answers': [0, 1], 'model_answer': '', 'explanation': 'Ungültig.', 'keywords': [],
         'difficulty': 1, 'quote': 'Metadaten beschreiben die Bedeutung und Herkunft von Daten im Data Warehouse'}]}


def test_quotes_are_located_by_the_hub_and_listings_are_skipped():
    pages = [(4, _norm(PAGE_ONE)), (5, _norm(PAGE_TWO))]
    assert locate_quote('Grundlage für jede nachvollziehbare Auswertung', pages) == 4
    # A slightly altered copy still finds its place through six consecutive words.
    assert locate_quote('Es gilt: umfasst vier Hauptprozesse, die Erfassung, Pflege und mehr', pages) == 5
    assert locate_quote('frei erfundene Aussage ohne jede Entsprechung im Text', pages) is None
    assert locate_quote('zu kurz', pages) is None
    listing = 'Inhaltsverzeichnis\n' + '\n'.join(f'{n} Kapitel ........ {n}' for n in range(1, 30))
    windows = page_windows([{'page': 1, 'text': 'Titel'}, {'page': 2, 'text': listing},
                            {'page': 3, 'text': 'x' * 8000}, {'page': 4, 'text': 'y' * 8000}])
    assert [[page['page'] for page in window] for window in windows] == [[3], [4]]
    assert parse_json('```json\n{"title": "T"}\n```') == {'title': 'T'}
    # A course letter filed under „Lernunterlagen“ is indexed as a summary but remains course material.
    assert source_kind({'path': 'Lernunterlagen/31311-01-S#1-S002667002-V1.0.pdf', 'kind': 'summary'}) == 'course_material'
    assert source_kind({'path': 'Lernunterlagen/zusammenfassung.pdf', 'kind': 'summary'}) == 'summary'


def _setup(directory):
    source = Path(directory)
    project = source / 'hub'
    (project / 'content').mkdir(parents=True)
    folder = source / '32711 BI'
    folder.mkdir()
    pdf = PdfWriter()
    for _ in range(5):
        pdf.add_blank_page(width=100, height=100)
    pdf.write(folder / '32711-01-lehrbrief.pdf')
    app = create_app(source, project / 'data', project, start_watch=False)
    hub = app.state.hub
    mid = hub.add_module({'name': 'Business Intelligence', 'number': '32711', 'directory': '32711 BI'})['id']
    return source, project, app, mid


def _documents(hub, mid):
    # Inserted after the start-up scan, which only accepts readable files on disk.
    documents = [
        ('32711 BI/32711-01-lehrbrief.pdf', 'course_material', '.pdf', 1),
        ('32711 BI/folien1.pdf', 'lecture', '.pdf', 1),
        ('32711 BI/skript.docx', 'course_material', '.docx', 2),
        ('32711 BI/ohne-einheit.pdf', 'course_material', '.pdf', None)]
    with hub.db() as db:
        for path, kind, extension, unit in documents:
            doc = {'path': path, 'name': Path(path).name, 'title': Path(path).stem, 'extension': extension, 'kind': kind,
                   'unit': unit, 'module_id': mid, 'status': 'pending', 'sha256': 'abc', 'pages': 5,
                   'page_texts': [{'page': 1, 'label': 'Seite 1', 'text': 'Deckblatt'},
                                  {'page': 4, 'label': 'Seite 4', 'text': PAGE_ONE},
                                  {'page': 5, 'label': 'Seite 5', 'text': PAGE_TWO}]}
            db.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET '
                       'module_id=excluded.module_id,payload=excluded.payload', (path, mid, json.dumps(doc)))


def _wait(client):
    for _ in range(200):
        state = client.get('/api/module-import').json()
        if state['state'] != 'running':
            return state
        time.sleep(0.02)
    raise AssertionError('Import wurde nicht fertig.')


def test_import_writes_pending_questions_and_a_draft_that_is_published_explicitly():
    with TemporaryDirectory() as directory:
        source, project, app, mid = _setup(directory)
        calls = []

        def generate(messages, structured=True):
            calls.append(messages)
            return json.loads(json.dumps(ANSWER))

        with TestClient(app, base_url='http://127.0.0.1') as client:
            _documents(app.state.hub, mid)
            plan = client.get('/api/module-import/preview', params={'module_id': mid}).json()
            assert plan['windows'] == 1 and plan['sources'][0]['path'].endswith('lehrbrief.pdf')
            assert {item['path'].split('/')[-1] for item in plan['skipped']} == {'folien1.pdf', 'skript.docx', 'ohne-einheit.pdf'}

            # Without the local Ollama tutor nothing is started.
            assert client.post('/api/module-import', json={'module_id': mid}).status_code == 503
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, lambda request: {})
            app.state.module_import_generate = generate
            assert client.post('/api/module-import', json={'module_id': mid, 'units': ['1']}).status_code == 400
            started = client.post('/api/module-import', json={'module_id': mid})
            assert started.status_code == 202, started.text
            state = _wait(client)
            assert state['state'] == 'done', state
            assert '[PDF-Seite 4]' in calls[0][1]['content'] and 'Deckblatt' not in calls[0][1]['content']
            assert state['counts'] == {'rejected_questions': 2, 'unproven_sections': 1, 'failed_windows': 0, 'reused_windows': 0}

            questions = json.loads((project / 'imports' / 'business_intelligence_einheit1_lokal.json').read_text(encoding='utf-8'))
            assert validate_import(questions) == []
            first, second = questions['questions']
            assert first['source_page'] == 4 and first['model_answer'] == 'Bedeutung' and first['verified'] is False
            assert first['generated_by'] == 'Lokales Modell (test)' and 'Beleg (PDF-S. 4)' in first['explanation']
            assert second['source_page'] == 5 and second['difficulty'] == 2 and second['checklist']
            assert first['theory_sources'][0]['pdf_page'] == 4

            # Nothing is imported or published by the run itself.
            assert app.state.hub.module(mid)['question_count'] == 0
            assert load_learning_pages(project, source) == ([], [])
            assert state['outputs']['draft'] == 'imports/entwuerfe/32711-learning-pages.json'
            assert state['outputs']['draft_errors'] == []
            draft = json.loads((project / state['outputs']['draft']).read_text(encoding='utf-8'))
            lesson = draft['lessons'][0]
            assert lesson['id'] == '32711-KE1-L01' and lesson['exercise_ids'] == [first['id'], second['id']]
            assert lesson['sections'][0]['sources'][0]['pdf_page'] == 4
            assert lesson['sections'][1]['sources'][0] == {'kind': 'pdf', 'path': '32711 BI/32711-01-lehrbrief.pdf',
                                                           'title': 'Business Intelligence · Kurseinheit 1 · Lehrbrief',
                                                           'pdf_page': 4, 'pdf_page_end': 5}
            assert 'nicht wörtlich gefunden' in lesson['sections'][1]['note']

            # A second run reuses the stored window instead of asking the model again.
            client.post('/api/module-import', json={'module_id': mid, 'units': [1]})
            assert _wait(client)['counts']['reused_windows'] == 1 and len(calls) == 1

            published = client.post('/api/module-import/publish', json={'module_id': mid})
            assert published.status_code == 200, published.text
            assert published.json() == {'published': 'content/business-intelligence-learning-pages.json', 'lessons': 1,
                                        'added_units': [1], 'skipped_units': []}
            assert client.get(f'/api/learning-pages/{mid}').json()['lessons'][0]['title'] == 'Metadaten im Data Warehouse'
            again = client.post('/api/module-import/publish', json={'module_id': mid})
            assert again.status_code == 400 and 'bereits veröffentlicht' in again.json()['detail']

            # The pending file appears in the existing document review.
            client.post('/api/scan', json={})
            pending = [doc for doc in client.get('/api/documents').json() if doc['path'].startswith('@imports/')]
            assert [(doc['status'], doc['proposal_count']) for doc in pending] == [('pending', 2)]


def test_failed_model_answers_are_reported_and_do_not_stop_the_run():
    with TemporaryDirectory() as directory:
        source, project, app, mid = _setup(directory)

        def generate(messages, structured=True):
            raise ValueError('kein JSON')

        _documents(app.state.hub, mid)
        state = app.state.module_import.run(mid, None, 'test', generate)
        assert state['state'] == 'done' and state['counts']['failed_windows'] == 1
        assert state['outputs'] == {'question_files': [], 'questions': 0, 'lessons': 0}
        other = app.state.hub.add_module({'name': 'Leeres Modul', 'number': '31311'})['id']
        empty = app.state.module_import.run(other, None, 'test', generate)
        assert empty['state'] == 'error' and 'keine verwertbaren PDF-Kursunterlagen' in empty['messages'][-1]


def test_unclassified_pdfs_are_used_only_when_a_unit_has_nothing_better(tmp_path):
    from backend.module_import import plan_sources
    source, project, app, mid = _setup(tmp_path)
    hub = app.state.hub
    _documents(hub, mid)
    extra = [('32711 BI/Einheit 1/kapitel-a.pdf', 'other', 1), ('32711 BI/Einheit 3/kapitel-b.pdf', 'other', 3),
             ('32711 BI/Einheit 3/altklausur.pdf', 'exam', 3)]
    with hub.db() as db:
        for path, kind, unit in extra:
            doc = {'path': path, 'name': Path(path).name, 'title': Path(path).stem, 'extension': '.pdf', 'kind': kind,
                   'unit': unit, 'module_id': mid, 'status': 'pending', 'sha256': 'abc', 'pages': 5,
                   'page_texts': [{'page': 4, 'label': 'Seite 4', 'text': PAGE_ONE}, {'page': 5, 'label': 'Seite 5', 'text': PAGE_TWO}]}
            db.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?)', (path, mid, json.dumps(doc)))
    usable, skipped, ignored = plan_sources(hub, mid)
    assert [(item['unit'], Path(item['path']).name, item['kind']) for item in usable] == [
        (1, '32711-01-lehrbrief.pdf', 'course_material'), (3, 'kapitel-b.pdf', 'other'), (3, 'altklausur.pdf', 'exam')]
    reasons = {Path(item['path']).name: item['reason'] for item in skipped + ignored}
    assert reasons['kapitel-a.pdf'] == 'Nicht verwendet, weil für die Kurseinheit ein Lehrbrief oder Folien vorliegen.'
    assert reasons['folien1.pdf'] == 'Folien nicht verwendet, weil für die Kurseinheit ein Lehrbrief vorliegt.'
    assert 'altklausur.pdf' not in reasons


def test_document_kind_can_be_set_by_hand(tmp_path):
    from backend.module_import import plan_sources
    source, project, app, mid = _setup(tmp_path)
    hub = app.state.hub
    path = '32711 BI/Einheit 2/verwaltung.pdf'
    doc = {'path': path, 'name': 'verwaltung.pdf', 'title': 'verwaltung', 'extension': '.pdf', 'kind': 'administrative',
           'unit': 2, 'module_id': mid, 'status': 'pending', 'sha256': 'abc', 'pages': 2,
           'page_texts': [{'page': 1, 'label': 'Seite 1', 'text': PAGE_ONE}]}
    with hub.db() as db:
        did = db.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?)', (path, mid, json.dumps(doc))).lastrowid
    _, _, ignored = plan_sources(hub, mid)
    assert path in [item['path'] for item in ignored]
    client = TestClient(app, base_url='http://127.0.0.1')
    kinds = client.get('/api/module-import/kinds').json()
    assert {'kind': 'exam', 'label': 'Altklausur / Klausurfragen', 'prepared': True} in kinds
    assert client.patch(f'/api/documents/{did}/kind', json={'kind': 'nonsense'}).status_code == 422
    answer = client.patch(f'/api/documents/{did}/kind', json={'kind': 'exam'}).json()
    assert answer['kind'] == 'exam' and answer['manual_kind'] == 'exam'
    usable, _, _ = plan_sources(hub, mid)
    assert (2, path, 'exam') in [(item['unit'], item['path'], item['kind']) for item in usable]
    units = client.get(f'/api/module-import/overview?module_id={mid}').json()['units']
    item = next(d for u in units for d in u['documents'] if d['path'] == path)
    assert item['usable'] and item['manual_kind'] == 'exam' and item['id'] == did
    assert client.patch(f'/api/documents/{did}/kind', json={'kind': None}).json()['kind'] == 'administrative'
