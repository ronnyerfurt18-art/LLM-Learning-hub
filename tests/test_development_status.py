"""Development: where a request stands (outcome) and what happened to it (history)."""
import os
import time
from datetime import datetime, timedelta, timezone

from backend.development import effect_checks, legacy_history, outcome
from tests.test_development import TEXT
from tests.test_development_change import EDIT, STYLES, TUTOR, _ordered, _propose, hub  # noqa: F401  (hub is a fixture)

BUILD = 'Oberfläche noch nicht neu gebaut.'
RESTART = 'Hub noch nicht neu gestartet.'
OWN = {'path': TUTOR, 'search': 'LIMIT = 3', 'replace': 'LIMIT = 5', 'reason': 'Mehr.'}


def _get(client, request_id='E-001'):
    return client.get(f'/api/development/requests/{request_id}').json()


def _post(client, path):
    answer = client.post(f'/api/development/requests/{path}')
    assert answer.status_code in (200, 202), answer.text
    return answer.json()


def _built(client, when):
    """The interface was built at `when`, as the time of dist/index.html says."""
    dist = client.project / 'frontend' / 'dist' / 'index.html'
    dist.parent.mkdir(parents=True, exist_ok=True)
    dist.write_text('<html></html>', encoding='utf-8')
    os.utime(dist, (when.timestamp(), when.timestamp()))


def _at(value):
    return datetime.fromisoformat(value)


def _style_change(client):
    _ordered(client)
    _propose(client, 'E-001', {'edits': [EDIT], 'question': ''})
    return _post(client, 'E-001/proposal/apply')


# --- outcome -------------------------------------------------------------------------------------------------------------

def test_every_stage_of_a_request_has_a_plain_label(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    assert _get(hub)['outcome'] == {'label': 'Noch kein Auftrag', 'tone': 'neutral', 'checks': []}
    _ordered(hub, STYLES)  # E-002
    assert _get(hub, 'E-002')['outcome'] == {'label': 'Auftrag liegt vor, noch nichts geändert', 'tone': 'teal', 'checks': []}
    _propose(hub, 'E-002', {'edits': [], 'question': 'Welcher Farbton?'})
    assert (_get(hub, 'E-002')['outcome']['label'], _get(hub, 'E-002')['outcome']['tone']) == ('Rückfrage des KI-Modells wartet auf dich', 'yellow')
    _propose(hub, 'E-002', {'edits': [EDIT], 'question': ''})
    assert _get(hub, 'E-002')['outcome']['label'] == 'Vorschlag wartet auf deine Freigabe'
    _post(hub, 'E-002/proposal/discard')
    assert _get(hub, 'E-002')['outcome']['label'] == 'Auftrag liegt vor, noch nichts geändert'
    for status, label, tone in (('handed_over', 'An eine externe KI übergeben, Ergebnis nicht geprüft', 'yellow'),
                                ('done', 'Von dir als umgesetzt markiert, vom Hub nicht geprüft', 'neutral'), ('dropped', 'Verworfen', 'red')):
        hub.patch('/api/development/requests/E-002', json={'status': status})
        assert (_get(hub, 'E-002')['outcome']['label'], _get(hub, 'E-002')['outcome']['tone']) == (label, tone)
    # The list carries the same words, so nothing has to be opened to see where a request stands.
    listed = {item['id']: item['outcome']['label'] for item in hub.get('/api/development').json()['requests']}
    assert listed == {'E-002': 'Verworfen', 'E-001': 'Noch kein Auftrag'}


def test_an_applied_interface_change_counts_only_after_a_later_build(hub):
    applied = _style_change(hub)
    assert applied['status'] == 'done'
    assert applied['outcome'] == {'label': 'Übernommen, wirkt aber noch nicht', 'tone': 'yellow', 'checks': [
        {'ok': False, 'text': BUILD, 'hint': 'Oberfläche neu bauen: im Ordner „frontend“ den Befehl „npm run build“ ausführen, danach die Seite im Browser neu laden.'}]}
    when = _at(applied['proposal']['applied_at'])
    _built(hub, when - timedelta(minutes=5))  # a build from before the change does not show it
    assert _get(hub)['outcome']['label'] == 'Übernommen, wirkt aber noch nicht'
    assert hub.get('/api/development').json()['requests'][0]['outcome']['label'] == 'Übernommen, wirkt aber noch nicht'
    _built(hub, when + timedelta(minutes=5))
    assert _get(hub)['outcome'] == {'label': 'Übernommen und wirksam', 'tone': 'green',
                                    'checks': [{'ok': True, 'text': 'Oberfläche seit dem Übernehmen neu gebaut.', 'hint': ''}]}
    assert hub.get('/api/development').json()['requests'][0]['outcome']['label'] == 'Übernommen und wirksam'


def test_changed_server_code_counts_only_after_the_hub_started_again(hub):
    _ordered(hub, TUTOR)
    _propose(hub, 'E-001', {'edits': [OWN], 'question': ''})
    applied = _post(hub, 'E-001/proposal/apply')
    assert [(item['ok'], item['text']) for item in applied['outcome']['checks']] == [(False, RESTART)]
    assert applied['outcome']['checks'][0]['hint'].startswith('Hub beenden und mit „Start.command“ neu starten')
    restarted = _at(applied['proposal']['applied_at']) + timedelta(minutes=1)
    hub.app_.state.development.started = restarted.isoformat()
    assert _get(hub)['outcome']['label'] == 'Übernommen und wirksam'
    assert [item['text'] for item in _get(hub)['outcome']['checks']] == ['Hub seit dem Übernehmen neu gestartet.']


def test_documents_and_tests_need_no_build_and_no_restart(hub):
    _ordered(hub, 'docs/lernchat.md')
    _propose(hub, 'E-001', {'edits': [{'path': 'docs/lernchat.md', 'search': 'Text', 'replace': 'Neuer Text', 'reason': 'Anleitung.'}], 'question': ''})
    outcome_ = _post(hub, 'E-001/proposal/apply')['outcome']
    assert outcome_ == {'label': 'Übernommen', 'tone': 'green', 'checks': []}


def test_taking_a_change_back_asks_for_a_new_build_only_if_the_change_was_built(hub):
    applied = _style_change(hub)
    when = _at(applied['proposal']['applied_at'])
    # Never built: the interface still shows the old state, so there is nothing left to do.
    reverted = _post(hub, 'E-001/proposal/revert')
    assert reverted['outcome'] == {'label': 'Zurückgenommen', 'tone': 'neutral', 'checks': []} and reverted['status'] == 'drafted'
    # Built while the change was in: the built interface still has it.
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    applied = _post(hub, 'E-001/proposal/apply')
    _built(hub, _at(applied['proposal']['applied_at']) + timedelta(microseconds=1))
    time.sleep(0.05)
    reverted = _post(hub, 'E-001/proposal/revert')
    assert reverted['outcome']['label'] == 'Zurückgenommen, wirkt aber noch nicht'
    assert [(item['ok'], item['text']) for item in reverted['outcome']['checks']] == [(False, 'Oberfläche stammt noch aus der Zeit mit der Änderung.')]
    _built(hub, _at(reverted['proposal']['reverted_at']) + timedelta(minutes=1))
    assert _get(hub)['outcome'] == {'label': 'Zurückgenommen', 'tone': 'neutral', 'checks': []}
    assert when < _at(applied['proposal']['applied_at'])


def test_requests_without_a_stored_change_have_no_checks():
    request = {'status': 'done', 'proposal': {'state': 'applied', 'applied_files': []}}
    assert effect_checks(request, '.', '2026-01-01T00:00:00+00:00') == []
    assert effect_checks({'status': 'new'}, '.', '2026-01-01T00:00:00+00:00') == []
    assert outcome({'status': 'new'}, '.', 'x')['label'] == 'Noch kein Auftrag'


# --- history -------------------------------------------------------------------------------------------------------------

def _words(client, request_id='E-001'):
    return [event['text'] for event in _get(client, request_id)['timeline']]


def test_the_history_lists_what_happened_in_order(hub):
    _style_change(hub)
    hub.patch('/api/development/requests/E-001', json={'note': 'Bitte #24555a.'})
    hub.patch('/api/development/requests/E-001', json={'status': 'handed_over'})
    hub.patch('/api/development/requests/E-001', json={'status': 'handed_over'})  # no change, no event
    hub.patch('/api/development/requests/E-001', json={'route': 'external'})
    _post(hub, 'E-001/proposal/revert')
    hub.patch('/api/development/requests/E-001', json={'route': 'local'})
    assert _words(hub) == [
        'Anforderung angelegt',
        'Auftrag ausgearbeitet (Lokales Modell (test:1b)), eingestuft als lokal machbar',
        'Änderung vorgeschlagen: 1 von 1 Ersetzungen übernehmbar',
        'Änderung übernommen: frontend/src/styles.css',
        'Ergänzung geändert',
        'Status geändert: Umgesetzt → Übergeben',
        'Einstufung von dir geändert auf „extern zu übergeben“',
        'Änderung zurückgenommen: frontend/src/styles.css',
        'Einstufung von dir geändert auf „lokal machbar“']
    times = [event['at'] for event in _get(hub)['timeline']]
    assert times == sorted(times) and 'history' not in _get(hub)
    _propose(hub, 'E-001', {'edits': [], 'question': 'Welcher Farbton?'})
    assert _words(hub)[-1] == 'Rückfrage des KI-Modells: Welcher Farbton?'
    _propose(hub, 'E-001', {'edits': [EDIT], 'question': ''})
    _post(hub, 'E-001/proposal/discard')
    assert _words(hub)[-2:] == ['Änderung vorgeschlagen: 1 von 1 Ersetzungen übernehmbar', 'Vorschlag verworfen']


def test_an_older_request_keeps_its_known_events_when_the_history_starts(hub):
    _style_change(hub)
    job = hub.app_.state.development
    job.change('E-001', lambda stored: {key: value for key, value in stored.items() if key != 'history'})  # as stored before the history
    known = [event['text'] for event in legacy_history(job.get('E-001'))]
    assert known == ['Anforderung angelegt', 'Auftrag ausgearbeitet (Lokales Modell (test:1b)), eingestuft als lokal machbar',
                     'Änderung vorgeschlagen', 'Änderung übernommen']
    assert _words(hub) == known
    hub.patch('/api/development/requests/E-001', json={'status': 'dropped'})
    assert _words(hub) == known + ['Status geändert: Umgesetzt → Verworfen']


def test_the_history_is_bounded(hub):
    hub.post('/api/development/requests', json={'text': TEXT})
    for number in range(120):
        hub.patch('/api/development/requests/E-001', json={'note': f'Stand {number}'})
    history = _get(hub)['timeline']
    assert len(history) == 100 and history[-1]['text'] == 'Ergänzung geändert'
