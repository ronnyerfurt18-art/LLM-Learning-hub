"""Assignment completeness, source bounds, isolation and read-only integration."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.assignments import load_assignments, validate_assignment
from backend.main import create_app


def sample_assignment(number=1):
    source = {'path': 'material/original.pdf', 'title': 'Originalaufgabe', 'pdf_page': 1}
    theory = {'path': 'material/theory.pdf', 'title': 'Theorie', 'pdf_page': 2}
    return {
        'id': f'dd-ea{number}', 'module_number': '32281', 'title': f'Einsendearbeit {number}',
        'rules': {'question_count': 12, 'option_count': 5, 'min_true': 1, 'points': [0, 1, 10, 30, 60, 100]},
        'due_date': '2026-12-01', 'source': source,
        'solution_note': 'Aus Kursunterlagen hergeleitet; keine offizielle Musterlösung.',
        'questions': [
            {'id': f'dd-ea{number}-q{i:02}', 'number': i, 'title': 'Definition',
             'prompt': 'Wahre Aussagen ankreuzen.', 'source_page': 1,
             'options': [{'id': letter, 'text': 'Eine prüfbare Aussage.',
                          'is_correct': letter in 'AC', 'explanation': 'Begründung aus dem Lehrbrief.',
                          'sources': [copy.deepcopy(theory)]} for letter in 'ABCDE']}
            for i in range(1, 13)]}


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'study'
        self.project = self.source / 'master-learning-hub'
        self.directory = self.project / 'content' / 'assignments'
        self.directory.mkdir(parents=True)
        material = self.source / 'material'
        material.mkdir()
        for name in ('original.pdf', 'theory.pdf'):
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.add_blank_page(width=100, height=100)
            with (material / name).open('wb') as stream:
                writer.write(stream)
        for number in (1, 2):
            self.write(sample_assignment(number), number)

    def write(self, content, number=1):
        (self.directory / f'digitale-diversitaet-ea{number}.json').write_text(
            json.dumps(content, ensure_ascii=False), encoding='utf-8')

    def problems(self, content):
        return validate_assignment(content, self.source, self.project)

    def test_complete_originals_and_each_option_has_explanation_and_source(self):
        packages = load_assignments(self.project, self.source)
        self.assertEqual([len(p['questions']) for p in packages], [12, 12])
        self.assertEqual(sum(len(q['options']) for p in packages for q in p['questions']), 120)
        self.assertEqual(self.problems(packages[0]), [])
        broken = copy.deepcopy(packages[0])
        broken['questions'][0]['options'][4]['explanation'] = ''
        broken['questions'][1]['options'][0]['sources'] = []
        broken['questions'][2]['options'][0]['is_correct'] = 'false'
        errors = self.problems(broken)
        self.assertTrue(any('explanation' in e for e in errors))
        self.assertTrue(any('Nachlesestelle' in e for e in errors))
        self.assertTrue(any('Wahr/Falsch' in e for e in errors))

    def test_rejects_missing_original_statements_and_duplicate_questions(self):
        broken = sample_assignment()
        broken['questions'][0]['options'].pop()
        self.assertTrue(any('Genau 5 Originalaussagen' in e for e in self.problems(broken)))
        broken = sample_assignment()
        broken['questions'][1]['id'] = broken['questions'][0]['id']
        self.assertTrue(any('Eindeutige Frage' in e for e in self.problems(broken)))

    def test_checks_pdf_page_bounds_and_source_confinement(self):
        for source in ({'path': 'material/theory.pdf', 'pdf_page': 3},
                       {'path': '../outside.pdf', 'pdf_page': 1},
                       {'path': 'master-learning-hub/data/learning.sqlite3', 'pdf_page': 1},
                       {'path': 'material/original.pdf', 'pdf_page': 1}):
            broken = sample_assignment()
            broken['questions'][0]['options'][0]['sources'] = [{'title': 'Quelle', **source}]
            self.assertTrue(self.problems(broken), source)

    def test_missing_or_malformed_file_is_an_explicit_error(self):
        self.write([])
        with self.assertRaises(ValueError):
            load_assignments(self.project, self.source)
        (self.directory / 'digitale-diversitaet-ea1.json').write_text('{broken', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'kann nicht geladen'):
            load_assignments(self.project, self.source)
        # A module only has the assignments that are prepared; other modules have none.
        (self.directory / 'digitale-diversitaet-ea1.json').unlink()
        self.assertEqual([item['id'] for item in load_assignments(self.project, self.source)], ['dd-ea2'])
        self.assertEqual(load_assignments(self.project, self.source, module_number='99999'), [])

    def test_api_is_read_only_and_follows_module_number(self):
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            module = app.state.hub.add_module({'name': 'Digitale Diversität'})
            mid = module['id']
            app.state.hub.patch_module(mid, {'number': '32281'})
            def snapshot():
                value = client.get('/api/export').json()
                value.pop('exported_at', None)
                return value
            before = snapshot()
            response = client.get(f'/api/assignments/{mid}')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()['assignments']), 2)
            self.assertEqual(snapshot(), before)
            # Updated content is read immediately without a scan or a database import.
            changed = sample_assignment()
            changed['questions'][0]['options'][0]['explanation'] = 'Korrigierte Erklärung.'
            self.write(changed)
            response = client.get(f'/api/assignments/{mid}')
            self.assertEqual(response.json()['assignments'][0]['questions'][0]['options'][0]['explanation'], 'Korrigierte Erklärung.')
            other = app.state.hub.add_module({'name': 'Anderes Modul', 'number': '31311'})
            self.assertEqual(client.get(f"/api/assignments/{other['id']}").status_code, 404)
            self.assertEqual(client.get('/api/assignments/missing').status_code, 404)


    def test_planner_question_about_an_assignment_gets_its_questions_without_solutions(self):
        from unittest.mock import Mock
        from backend.tutor import TutorService
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            mid = app.state.hub.add_module({'name': 'Digitale Diversität', 'number': '32281'})['id']
            transport = Mock(return_value={'message': {'role': 'assistant', 'content': 'Plan.'}})
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, transport)

            def sent(message, module_id=mid):
                response = client.post('/api/planner/ask', json={'module_id': module_id, 'message': message})
                self.assertEqual(response.status_code, 200, response.text)
                payload = json.loads(transport.call_args.args[0].data)
                return payload['messages'][1]['content'], payload

            context, payload = sent('Plane eine Lernstrecke für die Einsendearbeit 1.')
            self.assertIn('EINSENDEARBEITEN', context)
            self.assertIn('Einsendearbeit 1 · Abgabe 01.12.2026', context)
            self.assertNotIn('Einsendearbeit 2 ·', context)
            self.assertIn('Frage 12: Definition', context)
            self.assertIn('Nachlesen in Theorie: ohne Kapitelangabe (PDF-S. 2)', context)
            self.assertIn('Aussage E: Eine prüfbare Aussage.', context)
            # A plan needs the topics; solutions stay in the practice tab.
            self.assertNotIn('Begründung aus dem Lehrbrief', context)
            self.assertNotIn('is_correct', context)
            self.assertEqual(payload['options']['num_predict'], 1400)
            self.assertIn('nenne keine Lösungen', payload['messages'][0]['content'])

            # Without a number both assignments are listed compactly, also across all modules.
            context, _ = sent('Was muss ich für die Einsendearbeiten lernen?', '')
            self.assertIn('Einsendearbeit 2 · Abgabe', context)
            self.assertNotIn('Aussage A:', context)

            context, payload = sent('Wann ist die nächste Prüfung?')
            self.assertNotIn('EINSENDEARBEITEN', context)
            self.assertEqual(payload['options']['num_predict'], 700)


    def test_tutor_chat_works_through_an_assignment_question_by_question(self):
        from unittest.mock import Mock
        from backend.tutor import TutorService
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            mid = app.state.hub.add_module({'name': 'Digitale Diversität', 'number': '32281'})['id']
            transport = Mock(return_value={'message': {'role': 'assistant', 'content': 'Gern.'}})
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, transport)
            first = 'Ich möchte für die Einsenderarbeit 1 lernen. Beginne mit Aufgabe 1 und merke dir, was bearbeitet ist.'
            history = [{'role': 'user', 'content': first}, {'role': 'assistant', 'content': 'Gern.'}]

            def sent(message, turns=()):
                response = client.post('/api/tutor/chat', json={'module_id': mid, 'message': message, 'history': list(turns)})
                self.assertEqual(response.status_code, 200, response.text)
                return json.loads(transport.call_args.args[0].data)['messages'][1]['content'], response.json()

            context, answer = sent(first)
            self.assertIn('EINSENDEARBEIT-MODUS', context)
            self.assertIn('Einsendearbeit 1 · Frage 1 von 12: Definition', context)
            self.assertIn('Aussage B · Belege [S1]', context)
            self.assertIn('Hergeleitete Einordnung: falsch\nBegründung: Begründung aus dem Lehrbrief.', context)
            self.assertIn('noch keine weitere Frage', context)
            self.assertIn('wird jetzt neu geöffnet', context)
            self.assertIn('gib genau das sofort und vollständig', context)
            self.assertEqual([source['id'] for source in answer['sources']], ['S1'])
            self.assertIn('keine offizielle Musterlösung', answer['notice'])

            # The hub, not the model, moves on and remembers what was opened.
            context, _ = sent('Danke, nächste Aufgabe bitte.', history)
            self.assertIn('Frage 2 von 12', context)
            self.assertIn('bereits geöffnet: Frage 1;', context)
            history += [{'role': 'user', 'content': 'Danke, nächste Aufgabe bitte.'}, {'role': 'assistant', 'content': 'Gern.'}]
            context, _ = sent('Ich denke, A ist wahr.', history)
            self.assertIn('Aktuell: Frage 2 von 12', context)
            self.assertIn('bereits geöffnet; setze das Gespräch fort', context)
            context, _ = sent('Weiter mit Frage 7.', history)
            self.assertIn('Aktuell: Frage 7 von 12', context)
            self.assertIn('bereits geöffnet: Frage 1, Frage 2;', context)
            self.assertIn('noch nicht geöffnet: 3, 4, 5, 6, 8, 9, 10, 11, 12.', context)
            # Once the first mention has left the history, the previous message still identifies the conversation.
            later = [{'role': 'user', 'content': 'Weiter mit Frage 7.'}, {'role': 'assistant', 'content': 'Gern.'}]
            context, _ = sent('Und warum ist Aussage B falsch?', later)
            self.assertIn('Aktuell: Frage 7 von 12', context)
            unrelated = [{'role': 'user', 'content': 'Was ist ein Stereotyp?'}, {'role': 'assistant', 'content': 'Gern.'}]
            self.assertEqual(client.post('/api/tutor/chat', json={'module_id': mid, 'message': 'Und ein Beispiel?',
                                                                  'history': unrelated}).status_code, 404)
            # A later conversation resumes at the stored question of the named assignment.
            context, _ = sent('Lass uns mit der Einsendearbeit weitermachen.')
            self.assertIn('Aktuell: Frage 7 von 12', context)
            context, _ = sent('Jetzt Einsendearbeit 2, Aufgabe 3.')
            self.assertIn('Einsendearbeit 2 · Frage 3 von 12', context)

            # A new conversation about something else is an ordinary chat again (no learning page in this fixture).
            other = client.post('/api/tutor/chat', json={'module_id': mid, 'message': 'Erkläre mir das Modul.', 'history': []})
            self.assertEqual(other.status_code, 404, other.text)
            self.assertEqual(client.get('/api/tutor/context', params={'module_id': mid}).status_code, 404)
            # Asking the planner with the same typing slip still selects the one assignment.
            client.post('/api/planner/ask', json={'module_id': mid, 'message': 'Lernstrecke für Einsenderarbeit 1?'})
            planner_context = json.loads(transport.call_args.args[0].data)['messages'][1]['content']
            self.assertIn('Aussage A:', planner_context)
            self.assertNotIn('Einsendearbeit 2 ·', planner_context)


if __name__ == '__main__':
    unittest.main()
