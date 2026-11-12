"""Development as a conversation: ask once, get the order, the rating, the proposal; after approval the hub builds and tests."""
import time

from tests.test_development import TEXT, _raw
from tests.test_development_change import EDIT, STYLES, TUTOR, hub  # noqa: F401  (hub is a fixture)

OWN = {'path': TUTOR, 'search': 'LIMIT = 3', 'replace': 'LIMIT = 5', 'reason': 'Mehr.'}


def _wait(client, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        job = client.get('/api/development').json()['job']
        if job['state'] != 'running':
            return job
        time.sleep(0.02)
    raise AssertionError('job did not finish')


def _ask(client, order, proposal, runner=None):
    client.app_.state.development_generate = lambda messages, structured=True: order
    client.app_.state.development_change_generate = lambda messages, structured=True: proposal
    if runner is not None:
        client.app_.state.development_run = runner
    answer = client.post('/api/development/ask', json={'text': TEXT})
    assert answer.status_code == 202, answer.text
    return answer.json()['id']


def _runner(results):
    calls = []

    def run(command, cwd, timeout=170):
        calls.append((command[:2], str(cwd).rsplit('/', 1)[-1]))
        return results.pop(0) if results else (0, '')
    run.calls = calls
    return run


def test_asking_carries_a_local_task_to_a_proposal_that_waits_for_approval(hub):
    request_id = _ask(hub, _raw(files=[{'path': STYLES, 'change': 'Wert ändern.'}]), {'edits': [EDIT], 'question': ''})
    assert _wait(hub)['state'] == 'done'
    request = hub.get(f'/api/development/requests/{request_id}').json()
    assert request['order']['route'] == 'local' and request['proposal']['state'] == 'open'
    assert request['outcome']['label'] == 'Vorschlag wartet auf deine Freigabe'
    assert [event['text'] for event in request['timeline']][-2:] == [
        'Auftrag ausgearbeitet (Lokales Modell (test:1b)), eingestuft als lokal machbar', 'Änderung vorgeschlagen: 1 von 1 Ersetzungen übernehmbar']


def test_a_task_that_is_not_local_stops_at_the_handover_prompt(hub):
    files = [{'path': STYLES, 'change': 'x'}, {'path': TUTOR, 'change': 'y'}, {'path': 'backend/main.py', 'change': 'z'}]
    request_id = _ask(hub, _raw(files=files, size='gross'), {'edits': [EDIT], 'question': ''})
    job = _wait(hub)
    assert job['state'] == 'done' and job['message'].startswith('Das lässt sich nicht lokal lösen')
    request = hub.get(f'/api/development/requests/{request_id}').json()
    assert request['order']['route'] == 'external' and request.get('proposal') is None


def test_a_failing_model_ends_in_an_error_not_a_hanging_job(hub):
    def broken(messages, structured=True):
        raise ValueError('kaputt')
    hub.app_.state.development_generate = broken
    hub.app_.state.development_change_generate = broken
    assert hub.post('/api/development/ask', json={'text': TEXT}).status_code == 202
    job = _wait(hub)
    assert job['state'] == 'error' and 'kaputt' in job['message']


def test_asking_while_the_hub_is_busy_is_refused(hub):
    hub.app_.state.development_generate = lambda messages, structured=True: (time.sleep(0.5), _raw())[1]
    hub.app_.state.development_change_generate = lambda messages, structured=True: {'edits': [], 'question': 'x'}
    assert hub.post('/api/development/ask', json={'text': TEXT}).status_code == 202
    assert hub.post('/api/development/ask', json={'text': TEXT}).status_code == 409
    _wait(hub)


def test_after_approval_the_hub_builds_and_reports_done(hub):
    runner = _runner([(0, 'built')])
    request_id = _ask(hub, _raw(files=[{'path': STYLES, 'change': 'Wert ändern.'}]), {'edits': [EDIT], 'question': ''}, runner)
    _wait(hub)
    assert hub.post(f'/api/development/requests/{request_id}/proposal/apply').status_code == 200
    assert hub.post(f'/api/development/requests/{request_id}/verify').status_code == 202
    assert _wait(hub)['state'] == 'done'
    assert runner.calls == [(['npm', 'run'], 'frontend')]
    request = hub.get(f'/api/development/requests/{request_id}').json()
    assert request['proposal']['verify']['steps'] == [{'name': 'Oberfläche bauen', 'ok': True, 'detail': ''}]
    assert request['timeline'][-1]['text'] == 'Prüfung: Oberfläche bauen bestanden'


def test_a_failed_build_is_reported_as_not_done_with_the_reason(hub):
    runner = _runner([(1, 'error TS2304: Cannot find name x')])
    request_id = _ask(hub, _raw(files=[{'path': STYLES, 'change': 'Wert ändern.'}]), {'edits': [EDIT], 'question': ''}, runner)
    _wait(hub)
    hub.post(f'/api/development/requests/{request_id}/proposal/apply')
    hub.post(f'/api/development/requests/{request_id}/verify')
    assert _wait(hub)['state'] == 'error'
    outcome = hub.get(f'/api/development/requests/{request_id}').json()['outcome']
    assert (outcome['label'], outcome['tone']) == ('Übernommen, aber die Prüfung ist fehlgeschlagen', 'red')
    assert outcome['checks'][0] == {'ok': False, 'text': 'Oberfläche bauen fehlgeschlagen.', 'hint': 'error TS2304: Cannot find name x'}
    # The change can still be taken back.
    assert hub.post(f'/api/development/requests/{request_id}/proposal/revert').status_code == 200


def test_changed_server_code_runs_the_tests_of_the_order(hub):
    runner = _runner([(0, '5 passed')])
    request_id = _ask(hub, _raw(files=[{'path': TUTOR, 'change': 'Grenze'}]), {'edits': [OWN], 'question': ''}, runner)
    _wait(hub)
    hub.post(f'/api/development/requests/{request_id}/proposal/apply')
    hub.post(f'/api/development/requests/{request_id}/verify')
    _wait(hub)
    assert [call[0][1] for call in runner.calls] == ['-m']
    assert hub.get(f'/api/development/requests/{request_id}').json()['timeline'][-1]['text'] == 'Prüfung: Tests bestanden'


def test_verify_needs_an_applied_change(hub):
    request_id = _ask(hub, _raw(files=[{'path': STYLES, 'change': 'x'}]), {'edits': [EDIT], 'question': ''})
    _wait(hub)
    assert hub.post(f'/api/development/requests/{request_id}/verify').status_code == 409
