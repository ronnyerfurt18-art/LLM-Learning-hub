"""Deterministic answer checks: assignment wording, classification, withheld solutions, plan coverage."""
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.quality import MARKER, annotate, check_plan, check_tutor, mentioned_questions
from backend.tutor import TutorService
import tests.test_assignments as fixtures

OPTIONS = [
    {'id': 'A', 'is_correct': True, 'text': 'Es ist sehr schwierig, eine allgemeine Definition von Diversität zu erstellen, da Diversität sich auf viele verschiedene Bezugsbereiche beziehen kann.'},
    {'id': 'B', 'is_correct': True, 'text': 'Nach Litvin (1997) bezeichnet Ökosystemdiversität die Variation an verschiedenen Habitaten in einem geografischen Gebiet.'},
    {'id': 'C', 'is_correct': False, 'text': 'Diversität wird in Definitionen stets neutral und nicht wertend beschrieben.'},
    {'id': 'D', 'is_correct': True, 'text': 'Subjektives Empfinden hinsichtlich verschiedener Begriffe kann sich mit der Zeit ändern.'},
    {'id': 'E', 'is_correct': False, 'text': 'In den letzten Jahren hat sich ein Konsens über eine Definition der Diversität als wegweisend etabliert.'}]


def question(opened):
    return {'opened': opened, 'options': OPTIONS}


def test_missing_wording_is_named_when_a_question_is_opened():
    answer = ('Der Stoff dreht sich um die Abgrenzung von Diversität.\n- A: Es ist sehr schwierig, eine allgemeine Definition von '
              'Diversi­tät zu erstellen, da Diversität sich auf viele verschiedene Bezugsbereiche beziehen kann [S1].\n'
              '- B: „Nach Litvin (1997) bezeichnet Ökosystemdiversität die Variation an verschiedenen Habitaten in einem geografischen Gebiet.“')
    assert check_tutor(answer, 'Beginne mit Aufgabe 1', question(True)) == [
        'Die Frage wurde neu geöffnet, aber der Wortlaut fehlt für Aussage C, D, E. Schreibe „Nenne alle Aussagen im Wortlaut“ '
        'oder öffne den Reiter „Einsendearbeiten“.']
    # Later turns discuss single statements; the complete wording is not expected again.
    assert check_tutor(answer, 'Ich denke, A ist wahr.', question(False)) == []
    complete = answer + '\n' + '\n'.join(f"- {option['id']}: {option['text']}" for option in OPTIONS[2:])
    assert check_tutor(complete, 'Beginne mit Aufgabe 1', question(True)) == []


def test_classification_is_compared_with_the_derived_solution():
    summary = ('Richtig: Aussage E ist falsch. A (wahr) und B (wahr) betreffen die Definition; C (falsch) und E (falsch) '
               'widerlegen die Annahme; D (wahr) bestätigt den Wandel. Ist Aussage C wahr oder falsch? Begründe kurz.')
    assert check_tutor(summary, 'Nein, es gibt keinen Konsens.', question(False)) == []
    wrong = check_tutor('Ja, genau: Aussage E ist wahr, und C (wahr) ebenfalls.', 'E ist wahr.', question(False))
    assert [finding[:40] for finding in wrong] == ['Die Antwort ordnet Aussage C als wahr ei', 'Die Antwort ordnet Aussage E als wahr ei']
    assert 'im Hub ist sie als falsch hergeleitet' in wrong[0]


def test_withheld_solutions_false_storage_claims_and_truncation_are_reported():
    refusal = 'Ich kann dir nicht die fertigen Lösungen liefern, da du die Aussagen selbst einschätzen sollst.'
    found = check_tutor(refusal, 'wie lauten die Aussagen und die Antworten?', question(False))
    assert len(found) == 1 and found[0].startswith('Du hast nach der Auflösung gefragt')
    assert check_tutor('C ist falsch, weil der Lehrbrief von manchmal wertend spricht [S3].', 'Wie lautet die Lösung zu C?', question(False)) == []
    assert check_tutor(refusal, 'Ich denke, A ist wahr.', question(False)) == []
    assert 'gespeichert oder notiert' in check_tutor('Ich habe die Aufgabe notiert, dich vorzubereiten.')[0]
    assert check_tutor('Der Lernhub merkt sich, welche Fragen geöffnet wurden.') == []
    assert check_tutor('Ein halber Satz und', truncated=True) == ['Die Antwort wurde am Längenlimit abgeschnitten und ist unvollständig.']


def test_plan_must_name_every_question_of_the_assignment():
    plan = 'Block 1 (11.–13.11.): Fragen 1–3. Block 2: Frage 4, 5 und 6. Block 3: Aufgaben 7 bis 10. Probedurchlauf am 28.11.'
    assert mentioned_questions(plan) == set(range(1, 11))
    assert check_plan(plan, range(1, 13)) == ['Der Plan nennt diese Fragen der Einsendearbeit nicht: 11, 12.']
    assert check_plan('Lies zuerst Einheit 2 und wiederhole dann.', range(1, 13)) == [
        'Der Plan nennt keine Fragennummern der Einsendearbeit; die Zuordnung zu den Aufgaben fehlt.']
    assert check_plan(plan + ' Fragen 11 und 12 am 27.11.', range(1, 13)) == []
    assert check_plan('Die Rückmeldung ist am 31.01.2027 fällig.') == []
    # An answer that would no longer fit into the chat history keeps its text; the note stays in the hints.
    long = annotate({'answer': 'x' * 15990, 'notice': ''}, ['Hinweis.'])
    assert long['answer'] == 'x' * 15990 and 'Hinweis.' in long['notice']


class QualityIntegrationTests(fixtures.AssignmentTests):
    def test_findings_are_shown_below_the_answer_and_logged(self):
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            mid = app.state.hub.add_module({'name': 'Digitale Diversität', 'number': '32281'})['id']
            reply = {'message': {'role': 'assistant', 'content': 'Schätze zuerst A und B ein.'}, 'done_reason': 'length'}
            transport = Mock(return_value=reply)
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, transport)
            request = {'module_id': mid, 'message': 'Einsendearbeit 1, beginne mit Aufgabe 1.', 'history': []}
            answer = client.post('/api/tutor/chat', json=request).json()
            assert answer['answer'].startswith('Schätze zuerst A und B ein.' + MARKER)
            assert 'abgeschnitten' in answer['answer'] and 'Wortlaut fehlt für Aussage A, B, C, D, E' in answer['answer']
            assert 'Prüfhinweis des Lernhubs' in answer['notice'] and 'truncated' not in answer and 'check' not in answer

            reply['done_reason'] = 'stop'
            reply['message']['content'] = 'Hier die Aussagen:\n' + '\n'.join(f'{letter}: Eine prüfbare Aussage.' for letter in 'ABCDE')
            clean = client.post('/api/tutor/chat', json={**request, 'message': 'Einsendearbeit 1, Aufgabe 2.'}).json()
            assert MARKER not in clean['answer'] and 'quality' not in clean

            reply['message']['content'] = 'Lies Einheit 1 und 2.'
            plan = client.post('/api/planner/ask', json={'module_id': mid, 'message': 'Lernstrecke für Einsendearbeit 1?'}).json()
            assert 'nennt keine Fragennummern' in plan['answer']

            log = client.get('/api/quality').json()
            assert log['since_start'] == {'tutor': {'checked': 2, 'flagged': 1}, 'planner': {'checked': 1, 'flagged': 1}}
            assert [entry['area'] for entry in log['entries']] == ['planner', 'tutor']
            assert log['entries'][1]['message'] == request['message'] and len(log['entries'][1]['findings']) == 2

    def test_streamed_answers_are_checked_too(self):
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            mid = app.state.hub.add_module({'name': 'Digitale Diversität', 'number': '32281'})['id']
            lines = [json.dumps({'message': {'role': 'assistant', 'content': 'Schätze A ein.'}}).encode() + b'\n',
                     json.dumps({'message': {'role': 'assistant', 'content': ''}, 'done': True, 'done_reason': 'length'}).encode() + b'\n']
            stream = Mock(return_value=Mock(__iter__=lambda self: iter(lines), close=lambda: None))
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, Mock(), stream)
            response = client.post('/api/tutor/chat/stream', json={'module_id': mid, 'message': 'Einsendearbeit 1, Aufgabe 1.', 'history': []})
            events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
            assert [event['type'] for event in events] == ['delta', 'done'], events
            assert events[-1]['answer'].startswith('Schätze A ein.' + MARKER) and 'abgeschnitten' in events[-1]['answer']
            assert 'truncated' not in events[-1]

    def test_model_review_on_request_uses_the_context_of_that_answer(self):
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            mid = app.state.hub.add_module({'name': 'Digitale Diversität', 'number': '32281'})['id']
            reply = {'message': {'role': 'assistant', 'content': 'Schätze zuerst A und B ein.'}}
            transport = Mock(return_value=reply)
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, transport)
            question = 'Einsendearbeit 1, beginne mit Aufgabe 1.'
            shown = client.post('/api/tutor/chat', json={'module_id': mid, 'message': question, 'history': []}).json()['answer']
            assert MARKER in shown

            assert client.post('/api/quality/review', json={'message': question, 'answer': 'etwas anderes'}).status_code == 404
            assert client.post('/api/quality/review', json={'message': question}).status_code == 400
            reply['message']['content'] = '1. „Schätze zuerst A und B ein.“ – der Wortlaut der Aussagen fehlt [S1].'
            checked = client.post('/api/quality/review', json={'message': question, 'answer': shown})
            assert checked.status_code == 200, checked.text
            payload = json.loads(transport.call_args.args[0].data)
            assert payload['messages'][0]['content'].startswith('Du prüfst die Antwort eines Lerntutors.')
            context = payload['messages'][1]['content']
            assert 'ZU PRÜFENDE ANTWORT DES TUTORS:\nSchätze zuerst A und B ein.\n' in context
            assert 'Prüfhinweis des Lernhubs (automatisch' not in context and 'FESTE PRÜFHINWEISE DES HUBS' in context
            assert 'Hergeleitete Einordnung: falsch' in context
            result = checked.json()
            assert result['clean'] is False and result['review'].startswith('1. „Schätze')
            assert len(result['findings']) == 1 and result['follow_up'].startswith('Prüfhinweis-Korrektur:')
            assert client.get('/api/quality').json()['entries'][0]['area'] == 'review'

            # The prepared correction stays on the same question, whatever numbers the findings quote.
            history = [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': shown}]
            reply['message']['content'] = 'Hier die Aussagen:\n' + '\n'.join(f'{letter}: Eine prüfbare Aussage.' for letter in 'ABCDE')
            follow_up = result['follow_up'] + '\n2. Siehe auch Frage 9 und die nächste Aufgabe.'
            repaired = client.post('/api/tutor/chat', json={'module_id': mid, 'message': follow_up, 'history': history})
            assert repaired.status_code == 200, repaired.text
            assert 'Aktuell: Frage 1 von 12' in json.loads(transport.call_args.args[0].data)['messages'][1]['content']

            reply['message']['content'] = 'Keine Beanstandung.'
            fine = client.post('/api/quality/review', json={'message': follow_up, 'answer': repaired.json()['answer']}).json()
            assert fine == {'clean': True, 'review': 'Keine Beanstandung.', 'findings': [], 'model': 'test', 'follow_up': ''}


# The fixture class is reused for its study folder only; its own tests run in test_assignments.
for _name in dir(fixtures.AssignmentTests):
    if _name.startswith('test_') and _name not in QualityIntegrationTests.__dict__:
        setattr(QualityIntegrationTests, _name, None)
