"""Local change: the model proposes replacements, the hub proves them, and nothing is written before the person accepts."""
import copy
import hashlib
import threading

import pytest
from fastapi.testclient import TestClient

from backend import development_change
from backend.development_change import (
    INSTRUCTIONS, build_proposal, change_files, change_messages, check_edits, excerpts, file_budget, log_entry, read_sources,
    search_terms,
)
from backend.main import create_app
from backend.tutor import TutorService

from tests.test_development import SECRET, TEXT, _draft, _finish, _project, _raw

CSS = ':root{--bg:#fff;--nav:#183a3e}\n:root[data-theme=dark]{--nav:#171717}\n.sidebar{background:var(--nav)}\n'
CODE = '"""Tutor service: one bounded model call per turn."""\nLIMIT = 3\n\n\ndef limit():\n    return LIMIT\n'
EDIT = {'path': 'frontend/src/styles.css', 'search': '--nav:#183a3e', 'replace': '--nav:#24555a', 'reason': 'Hellerer Grünton im Hellmodus.'}
LOG = '# Änderungslog\n\nNeueste Einträge oben.\n\n---\n\n## 01.01.2026 – Alter Eintrag\n\nText\n'


def _order(*paths, route='local', new=()):
    return {'goal': 'Die Seitenleiste ist im Hellmodus heller.', 'steps': ['Farbwert anpassen.'], 'acceptance': ['Ist die Seitenleiste heller?'],
            'files': [{'path': path, 'change': 'Farbwert ändern.', 'new': path in new} for path in paths], 'route': route}


def _sources(**files):
    return [{'path': path, 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'shown': 'whole', 'pieces': [(0, text)]}
            for path, text in files.items()]


# --- which files, and how much of them ----------------------------------------------------------------------------------

def test_only_existing_program_files_of_a_local_order_may_change(tmp_path):
    index = development_change.file_index(_project(tmp_path))
    assert change_files(_order('frontend/src/styles.css', 'backend/tutor.py'), index) == ['frontend/src/styles.css', 'backend/tutor.py']
    # Tests and documents ride along only when no program file is named; files outside the index never do.
    assert change_files(_order('backend/tutor.py', 'docs/lernchat.md', 'tests/test_tutor.py'), index) == ['backend/tutor.py']
    assert change_files(_order('docs/lernchat.md'), index) == ['docs/lernchat.md']
    for order, reason in ((None, 'erst vorschlagen, wenn ein Auftrag vorliegt'),
                          (_order('backend/tutor.py', route='external'), 'nur für Aufträge vor, die als „lokal machbar“'),
                          (_order('backend/neu.py', new=('backend/neu.py',)), 'verlangt neue Dateien'),
                          (_order('backend/tutor.py', 'backend/planner.py', 'backend/plain.py'), 'höchstens 2'),
                          (_order('tutor.local.json', 'content/lernseiten.json', 'data/notiz.md', 'README.md', 'launcher.py'), 'keine Datei')):
        with pytest.raises(ValueError, match=reason):
            change_files(order, index)


def test_model_reads_whole_files_while_they_fit_and_excerpts_otherwise(tmp_path):
    project = _project(tmp_path)
    big = 'a{color:red}' * 400 + '.sidebar{background:var(--nav)}' + 'b{color:blue}' * 400
    (project / 'frontend/src/styles.css').write_text(big, encoding='utf-8')
    request = {'text': 'Das Menü soll heller werden.', 'note': 'Gemeint ist .sidebar', 'order': _order('frontend/src/styles.css', 'backend/tutor.py')}
    whole = read_sources(project, ['frontend/src/styles.css', 'backend/tutor.py'], search_terms(request), 20000)
    assert [source['shown'] for source in whole] == ['whole', 'whole'] and whole[0]['sha256'] == hashlib.sha256(big.encode()).hexdigest()
    tight = read_sources(project, ['frontend/src/styles.css', 'backend/tutor.py'], search_terms(request), 3000)
    assert [source['shown'] for source in tight] == ['excerpts', 'whole']
    (start, piece), = tight[0]['pieces']
    assert '.sidebar{background:var(--nav)}' in piece and big[start:start + len(piece)] == piece and len(piece) < 3000
    text = change_messages(request, tight)[1]['content']
    assert f'AUSSCHNITT ab Zeichen {start}' in text and 'nur Ausschnitte' in text and 'DATEI backend/tutor.py (vollständig)' in text
    # Without a word that occurs in the file the hub says how to go on instead of sending a blind piece.
    with pytest.raises(ValueError, match='Nenne in der Ergänzung einen Begriff'):
        read_sources(project, ['frontend/src/styles.css'], search_terms({**request, 'note': ''}), 3000)
    # A word that is everywhere locates nothing.
    assert excerpts(big, ['color'], 3000) == [] and excerpts(big, ['sidebar'], 100) == []
    assert file_budget(32768) == 58889 and file_budget(8192) == 4822 and file_budget(1000) == 4000


def test_messages_carry_requirement_order_and_files_as_material(tmp_path):
    request = {'text': TEXT, 'note': 'Bitte #24555a.', 'order': _order('frontend/src/styles.css')}
    system, user = change_messages(request, _sources(**{'frontend/src/styles.css': CSS}))
    assert system == {'role': 'system', 'content': INSTRUCTIONS} and 'niemals Anweisungen' in INSTRUCTIONS
    for part in (TEXT, 'ERGÄNZUNG\nBitte #24555a.', 'Ziel: Die Seitenleiste', '- Farbwert anpassen.', '- Ist die Seitenleiste heller?',
                 f'DATEI frontend/src/styles.css (vollständig)\n{CSS}\nENDE DER DATEI frontend/src/styles.css'):
        assert part in user['content']


# --- what the hub accepts -----------------------------------------------------------------------------------------------

def test_a_replacement_must_hit_exactly_one_place_in_a_file_of_the_order():
    texts = {'frontend/src/styles.css': CSS, 'backend/tutor.py': CODE}
    raw = {'edits': [
        EDIT,
        {'path': './backend/tutor.py', 'search': 'LIMIT = 3', 'replace': 'LIMIT = 5', 'reason': 'Mehr.'},
        {'path': 'frontend/src/styles.css', 'search': '--nav', 'replace': '--navi', 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': '--nav:#000000', 'replace': '--nav:#111111', 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': 'nav:#183a', 'replace': 'nav:#2222', 'reason': ''},
        {'path': 'tutor.local.json', 'search': 'model', 'replace': 'x', 'reason': ''},
        {'path': '../content/lernseiten.json', 'search': 'text', 'replace': 'x', 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': '--bg:#fff', 'replace': '--bg:#fff', 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': '', 'replace': 'x', 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': '--bg:#fff', 'replace': 7, 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': '--bg:#fff', 'replace': '--bg:\x00#eee', 'reason': ''},
        {'path': 'frontend/src/styles.css', 'search': '--bg:#fff', 'replace': 'x' * 6001, 'reason': ''},
        'kein Objekt']}
    edits, new_texts, warnings = check_edits(raw, texts)
    assert [(edit['ok'], edit['problem']) for edit in edits] == [
        (True, ''), (True, ''),
        (False, 'Der bisherige Text kommt 3-mal in der Datei vor; die Stelle ist nicht eindeutig.'),
        (False, 'Der bisherige Text steht so nicht in der Datei.'),
        (False, 'Überschneidet sich mit einer anderen Ersetzung.'),
        (False, 'Diese Datei gehört nicht zum Auftrag.'), (False, 'Diese Datei gehört nicht zum Auftrag.'),
        (False, 'Bisheriger und neuer Text sind gleich.'), (False, 'Bisheriger oder neuer Text fehlt.'),
        (False, 'Bisheriger oder neuer Text fehlt.'), (False, 'Der neue Text enthält Steuerzeichen.'),
        (False, 'Die Ersetzung ist zu lang für eine kleine Änderung.')]
    assert new_texts == {'frontend/src/styles.css': CSS.replace('#183a3e', '#24555a'), 'backend/tutor.py': CODE.replace('= 3', '= 5')}
    assert warnings == [] and all('start' not in edit for edit in edits)
    assert (edits[0]['lead'], edits[0]['tail']) == (':root{--bg:#fff;', '}\n:root[data-theme=dark]{--nav:#171717}\n.sidebar{background:var(--nav)}\n')
    assert len(edits[-1]['replace']) == development_change.SHOWN_CHARS
    assert check_edits({'edits': [EDIT] * 20}, texts)[0].__len__() == development_change.MAX_EDITS
    assert check_edits({'edits': 'nichts'}, texts) == ([], {}, []) and check_edits({}, texts) == ([], {}, [])


def test_several_replacements_in_one_file_apply_together_and_broken_python_is_refused():
    two = {'edits': [{'path': 'backend/tutor.py', 'search': 'return LIMIT', 'replace': 'return LIMIT + 1', 'reason': ''},
                     {'path': 'backend/tutor.py', 'search': 'LIMIT = 3', 'replace': 'LIMIT = 30', 'reason': ''}]}
    edits, new_texts, _ = check_edits(two, {'backend/tutor.py': CODE})
    assert all(edit['ok'] for edit in edits) and new_texts == {'backend/tutor.py': CODE.replace('= 3', '= 30').replace('return LIMIT', 'return LIMIT + 1')}
    broken = {'edits': [{'path': 'backend/tutor.py', 'search': 'def limit():', 'replace': 'def limit(:', 'reason': ''}]}
    edits, new_texts, _ = check_edits(broken, {'backend/tutor.py': CODE})
    assert new_texts == {} and edits[0]['ok'] is False and edits[0]['problem'] == 'Mit dieser Änderung wäre backend/tutor.py kein gültiges Python mehr (Zeile 5).'
    # Styles and scripts cannot be parsed here; a changed bracket count is shown as a warning and left to the person.
    edits, new_texts, warnings = check_edits({'edits': [{'path': 'a.css', 'search': '#183a3e}', 'replace': '#24555a', 'reason': ''}]}, {'a.css': CSS})
    assert edits[0]['ok'] and warnings == ['In a.css ändert sich die Zahl der offenen und geschlossenen Klammern. Sieh dir die Stelle genau an.']


def test_proposal_needs_a_replacement_or_a_question():
    sources = _sources(**{'frontend/src/styles.css': CSS})
    proposal = build_proposal({'edits': [EDIT], 'question': ''}, sources, 'test:1b')
    assert (proposal['state'], proposal['question'], proposal['generated_by']) == ('open', '', 'Lokales Modell (test:1b)')
    assert proposal['files'] == [{'path': 'frontend/src/styles.css', 'sha256': sources[0]['sha256'], 'chars': len(CSS), 'shown': 'whole'}]
    asked = build_proposal({'edits': [], 'question': 'Welcher Farbton?'}, sources, 'test:1b')
    assert asked['edits'] == [] and asked['question'] == 'Welcher Farbton?'
    for empty in ({}, {'edits': [], 'question': ' '}, {'edits': ['x'], 'question': 3}):
        with pytest.raises(ValueError, match='weder eine Ersetzung noch eine Rückfrage'):
            build_proposal(empty, sources, 'test:1b')


def test_log_entry_goes_on_top_and_a_missing_log_is_not_created(tmp_path):
    assert log_entry(tmp_path, 'Titel', ['Text']) is False and not (tmp_path / 'logs').exists()
    log = tmp_path / 'logs' / 'Aenderungslog.md'
    log.parent.mkdir()
    log.write_text(LOG, encoding='utf-8')
    assert log_entry(tmp_path, 'E-001 im Hub umgesetzt: Titel', ['**Anlass:** A', '**Änderung:** B']) is True
    text = log.read_text(encoding='utf-8')
    head, entry, old = text.partition('## ')
    assert head == '# Änderungslog\n\nNeueste Einträge oben.\n\n---\n\n' and old.endswith('## 01.01.2026 – Alter Eintrag\n\nText\n')
    assert ' – E-001 im Hub umgesetzt: Titel\n\n**Anlass:** A\n\n**Änderung:** B\n\n---\n\n' in old
    log.write_text('# Leer\n', encoding='utf-8')
    assert log_entry(tmp_path, 'T', ['x']) and log.read_text(encoding='utf-8').startswith('# Leer\n\n## ')


# --- API ----------------------------------------------------------------------------------------------------------------

STYLES, TUTOR = 'frontend/src/styles.css', 'backend/tutor.py'


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.delenv('MLH_FEATURES', raising=False)
    study, project = tmp_path / 'Studium', _project(tmp_path / 'hub')
    study.mkdir()
    (project / STYLES).write_bytes(CSS.encode())
    (project / TUTOR).write_bytes(CODE.encode())
    (project / 'logs/Aenderungslog.md').write_bytes(LOG.encode())
    app = create_app(study, project / 'data', project, start_watch=False)
    app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test:1b'}, lambda request: {})
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.app_, client.project, client.study = app, project, study
        yield client


def _tree(root):
    return sorted((path.relative_to(root).as_posix(), path.read_bytes()) for path in root.rglob('*')
                  if path.is_file() and 'data' not in path.relative_to(root).parts[:1])


def _ordered(client, *paths):
    """A stored request with an order that names `paths`."""
    number = len(client.get('/api/development').json()['requests']) + 1
    client.post('/api/development/requests', json={'text': TEXT})
    _draft(client, f'E-{number:03d}', _raw(files=[{'path': path, 'change': 'Wert ändern.'} for path in paths or (STYLES,)]))
    return f'E-{number:03d}'


def _propose(client, request_id, answer):
    seen = []

    def generate(messages, structured=True):
        seen.append((messages, structured))
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)
    client.app_.state.development_change_generate = generate
    started = client.post(f'/api/development/requests/{request_id}/proposal')
    assert started.status_code == 202, started.text
    assert (started.json()['state'], started.json()['kind']) == ('running', 'proposal')
    return _finish(client), seen


def test_model_reads_the_named_files_and_nothing_is_written_before_approval(hub):
    request_id = _ordered(hub)
    before = _tree(hub.project)
    job, seen = _propose(hub, request_id, {'edits': [EDIT], 'question': ''})
    assert (job['state'], job['kind'], job['request_id'], job['model']) == ('done', 'proposal', 'E-001', 'test:1b')
    assert job['message'] == 'Vorschlag liegt vor: 1 von 1 Ersetzungen lassen sich übernehmen.'
    (messages, structured), = seen
    assert structured is True and CSS in messages[1]['content'] and TEXT in messages[1]['content']
    assert SECRET not in messages[1]['content'] and CODE not in messages[1]['content']  # only the files of the order
    detail = hub.get('/api/development/requests/E-001').json()
    proposal = detail['proposal']
    assert (detail['status'], detail['change_error'], proposal['state'], proposal['question']) == ('drafted', '', 'open', '')
    assert proposal['edits'] == [{**EDIT, 'ok': True, 'problem': '', 'lead': ':root{--bg:#fff;', 'tail': CSS.split('#183a3e', 1)[1]}]
    assert _tree(hub.project) == before and not (hub.project / 'data' / 'backups' / 'development').exists()
    # Discarding leaves the files alone as well and closes the proposal.
    assert hub.post('/api/development/requests/E-001/proposal/discard').json()['proposal']['state'] == 'discarded'
    assert hub.post('/api/development/requests/E-001/proposal/apply').status_code == 409
    assert _tree(hub.project) == before


def test_accepting_writes_backs_up_logs_and_can_be_taken_back_exactly(hub):
    _ordered(hub)
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    applied = hub.post('/api/development/requests/E-001/proposal/apply')
    assert applied.status_code == 200, applied.text
    detail = applied.json()
    proposal = detail['proposal']
    assert (detail['status'], proposal['state'], proposal['logged']) == ('done', 'applied', True)
    assert (hub.project / STYLES).read_bytes() == CSS.replace('#183a3e', '#24555a').encode()
    assert proposal['backup'].startswith('data/backups/development/E-001-') and proposal['effect'] == [
        'Oberfläche neu bauen: im Ordner „frontend“ den Befehl „npm run build“ ausführen, danach die Seite im Browser neu laden.']
    assert (hub.project / proposal['backup'] / STYLES).read_bytes() == CSS.encode()
    assert [(item['path'], item['before']) for item in proposal['applied_files']] == [(STYLES, hashlib.sha256(CSS.encode()).hexdigest())]
    log = (hub.project / 'logs/Aenderungslog.md').read_text(encoding='utf-8')
    assert '– E-001 im Hub umgesetzt: Antwortzeit im Lernchat zeigen\n' in log and f'`{STYLES}`: Hellerer Grünton im Hellmodus.' in log
    assert f"`{proposal['backup']}/`" in log and log.index('E-001 im Hub umgesetzt') < log.index('Alter Eintrag') and log.endswith(LOG.split('## ', 1)[1])
    assert hub.get('/api/development').json()['requests'][0]['status'] == 'done'
    # Applied once: no second write, and no new proposal on top of it.
    assert hub.post('/api/development/requests/E-001/proposal/apply').status_code == 409
    again = hub.post('/api/development/requests/E-001/proposal')
    assert again.status_code == 409 and 'schon eine Änderung übernommen' in again.json()['detail']
    assert hub.post('/api/development/requests/E-001/proposal/discard').status_code == 409
    reverted = hub.post('/api/development/requests/E-001/proposal/revert')
    assert reverted.status_code == 200, reverted.text
    assert (hub.project / STYLES).read_bytes() == CSS.encode()
    assert (reverted.json()['status'], reverted.json()['proposal']['state']) == ('drafted', 'reverted')
    assert '– E-001 zurückgenommen: ' in (hub.project / 'logs/Aenderungslog.md').read_text(encoding='utf-8')
    assert (hub.project / proposal['backup'] / STYLES).read_bytes() == CSS.encode()  # the copy stays
    assert hub.post('/api/development/requests/E-001/proposal/revert').status_code == 409
    assert _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})[0]['state'] == 'done'  # and a new attempt is possible


def test_server_code_is_changed_only_into_valid_python_and_names_the_restart(hub):
    _ordered(hub, TUTOR)
    job, _ = _propose(hub, 'E-001', {'edits': [{'path': TUTOR, 'search': 'def limit():', 'replace': 'def limit(:', 'reason': 'kaputt'}], 'question': ''})
    assert job['message'] == 'Vorschlag liegt vor: 0 von 1 Ersetzungen lassen sich übernehmen.'
    refused = hub.post('/api/development/requests/E-001/proposal/apply')
    assert refused.status_code == 409 and 'keine Ersetzung' in refused.json()['detail'] and (hub.project / TUTOR).read_bytes() == CODE.encode()
    _propose(hub, 'E-001', {'edits': [{'path': TUTOR, 'search': 'LIMIT = 3', 'replace': 'LIMIT = 5', 'reason': 'Mehr.'}], 'question': ''})
    proposal = hub.post('/api/development/requests/E-001/proposal/apply').json()['proposal']
    assert (hub.project / TUTOR).read_bytes() == CODE.replace('= 3', '= 5').encode()
    assert proposal['effect'] == ['Hub beenden und mit „Start.command“ neu starten; geänderter Servercode wirkt erst danach.']


def test_replacements_outside_the_order_are_shown_and_never_written(hub):
    _ordered(hub)
    before = _tree(hub.project), (hub.project / 'tutor.local.json').read_bytes(), (hub.project / 'content/lernseiten.json').read_bytes()
    job, _ = _propose(hub, 'E-001', {'edits': [
        {'path': 'tutor.local.json', 'search': 'model', 'replace': 'x', 'reason': ''},
        {'path': 'content/lernseiten.json', 'search': 'text', 'replace': 'x', 'reason': ''},
        {'path': TUTOR, 'search': 'LIMIT = 3', 'replace': 'LIMIT = 5', 'reason': 'Nicht im Auftrag.'},
        {'path': STYLES, 'search': '--nav', 'replace': '--navi', 'reason': ''}], 'question': ''})
    assert job['message'] == 'Vorschlag liegt vor: 0 von 4 Ersetzungen lassen sich übernehmen.'
    edits = hub.get('/api/development/requests/E-001').json()['proposal']['edits']
    assert [edit['problem'] for edit in edits] == ['Diese Datei gehört nicht zum Auftrag.'] * 3 + [
        'Der bisherige Text kommt 3-mal in der Datei vor; die Stelle ist nicht eindeutig.']
    assert hub.post('/api/development/requests/E-001/proposal/apply').status_code == 409
    assert (_tree(hub.project), (hub.project / 'tutor.local.json').read_bytes(), (hub.project / 'content/lernseiten.json').read_bytes()) == before


def test_a_file_changed_in_between_stops_accepting_and_taking_back(hub):
    _ordered(hub)
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    edited = CSS + '.neu{}\n'
    (hub.project / STYLES).write_bytes(edited.encode())
    stale = hub.post('/api/development/requests/E-001/proposal/apply')
    assert stale.status_code == 409 and stale.json()['detail'] == f'{STYLES} hat sich seit dem Vorschlag geändert. Lass die Änderung neu vorschlagen.'
    assert (hub.project / STYLES).read_bytes() == edited.encode() and hub.get('/api/development/requests/E-001').json()['status'] == 'drafted'
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    assert hub.post('/api/development/requests/E-001/proposal/apply').status_code == 200
    later = (hub.project / STYLES).read_bytes() + b'.spaeter{}\n'
    (hub.project / STYLES).write_bytes(later)
    kept = hub.post('/api/development/requests/E-001/proposal/revert')
    assert kept.status_code == 409 and 'seit dem Übernehmen weiter geändert' in kept.json()['detail'] and 'data/backups/development/E-001-' in kept.json()['detail']
    assert (hub.project / STYLES).read_bytes() == later and hub.get('/api/development/requests/E-001').json()['proposal']['state'] == 'applied'


def test_a_question_or_a_failed_attempt_changes_nothing_and_keeps_the_earlier_proposal(hub):
    _ordered(hub)
    job, _ = _propose(hub, 'E-001', {'edits': [], 'question': 'Welcher Farbton genau?'})
    assert job['message'] == 'Das KI-Modell hat eine Rückfrage gestellt.'
    asked = hub.get('/api/development/requests/E-001').json()['proposal']
    assert (asked['question'], asked['edits']) == ('Welcher Farbton genau?', []) and hub.post('/api/development/requests/E-001/proposal/apply').status_code == 409
    for answer, reason in ((OSError('aus'), 'Ollama ist nicht erreichbar oder hat nicht rechtzeitig geantwortet.'),
                           (KeyError('message'), 'Keine verwertbare Antwort des KI-Modells: message'),
                           ({'edits': [], 'question': ''}, 'Das KI-Modell hat weder eine Ersetzung noch eine Rückfrage geliefert.')):
        job, seen = _propose(hub, 'E-001', answer)
        assert (job['state'], job['message']) == ('error', reason)
        detail = hub.get('/api/development/requests/E-001').json()
        assert detail['change_error'] == reason and detail['proposal'] == asked and detail['error'] == ''
    assert len(seen) == 1  # an answer without content is not asked for a second time
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    assert hub.get('/api/development/requests/E-001').json()['change_error'] == ''


def test_a_new_order_drops_a_waiting_proposal_but_not_an_applied_change(hub):
    _ordered(hub)
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    _draft(hub, 'E-001', _raw(files=[{'path': STYLES, 'change': 'Anders.'}]))
    assert hub.get('/api/development/requests/E-001').json()['proposal'] is None
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    hub.post('/api/development/requests/E-001/proposal/apply')
    _draft(hub, 'E-001', _raw(files=[{'path': STYLES, 'change': 'Noch anders.'}]))
    detail = hub.get('/api/development/requests/E-001').json()
    assert (detail['proposal']['state'], detail['status']) == ('applied', 'done')
    assert hub.post('/api/development/requests/E-001/proposal/revert').status_code == 200


def test_proposals_need_a_local_order_a_model_and_a_free_job(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    for action in ('apply', 'discard', 'revert'):
        assert hub.post(f'/api/development/requests/E-001/proposal/{action}').status_code == 409
        assert hub.post(f'/api/development/requests/E-404/proposal/{action}').status_code == 404
    missing = hub.post('/api/development/requests/E-001/proposal')
    assert missing.status_code == 400 and 'erst vorschlagen, wenn ein Auftrag vorliegt' in missing.json()['detail']
    assert hub.post('/api/development/requests/E-404/proposal').status_code == 404
    _draft(hub, 'E-001', _raw(files=[{'path': STYLES, 'change': 'Farbe.'}]))
    hub.patch('/api/development/requests/E-001', json={'route': 'external'})
    external = hub.post('/api/development/requests/E-001/proposal')
    assert external.status_code == 400 and 'lokal machbar' in external.json()['detail']
    hub.patch('/api/development/requests/E-001', json={'route': 'local'})
    tutor = hub.app_.state.tutor
    hub.app_.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'none'}, lambda request: {})
    assert hub.post('/api/development/requests/E-001/proposal').status_code == 503
    hub.app_.state.tutor = tutor
    entered, release = threading.Event(), threading.Event()

    def generate(messages, structured=True):
        entered.set()
        assert release.wait(10)
        return {'edits': [EDIT], 'question': ''}
    hub.app_.state.development_change_generate = generate
    assert hub.post('/api/development/requests/E-001/proposal').status_code == 202
    assert entered.wait(10)
    busy = hub.post('/api/development/requests/E-001/order')
    assert busy.status_code == 409 and busy.json()['detail'] == 'Das KI-Modell schlägt gerade eine Änderung vor. Bitte warte, bis es fertig ist.'
    for action in ('apply', 'discard', 'revert'):
        waiting = hub.post(f'/api/development/requests/E-001/proposal/{action}')
        assert waiting.status_code == 409 and 'arbeitet gerade an dieser Anforderung' in waiting.json()['detail']
    release.set()
    assert _finish(hub)['state'] == 'done'


def test_switched_off_development_has_no_change_routes(tmp_path, monkeypatch):
    monkeypatch.setenv('MLH_FEATURES', 'voice')
    study, project = tmp_path / 'Studium', _project(tmp_path / 'hub')
    study.mkdir()
    with TestClient(create_app(study, project / 'data', project, start_watch=False), base_url='http://127.0.0.1') as client:
        for action in ('', '/apply', '/discard', '/revert'):
            answer = client.post(f'/api/development/requests/E-001/proposal{action}')
            assert answer.status_code == 404 and answer.json() == {'detail': 'Not Found'}
