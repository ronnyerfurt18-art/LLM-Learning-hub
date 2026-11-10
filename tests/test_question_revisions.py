"""Approved question revisions add missing task context without resetting learning history."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core import Hub
from backend.main import create_app
from tests.test_core import sample_import
from tests.seedlist import write_seed_list


def context_revision(content):
    """A context-only editorial correction leaves IDs and answer semantics intact."""
    revised = copy.deepcopy(content)
    for question in revised['questions']:
        question.update(
            question='Beurteile für den beschriebenen Fall: ' + question['question'],
            question_context='Ein Unternehmen vereinheitlicht die Zugänge zu seiner Lernplattform. '
                             'Beurteile die Auswirkungen auf Beschäftigte mit verschiedenen Voraussetzungen.',
            question_context_source={'path': '99999 Testmodul/aufgaben.pdf', 'source_page': 8},
            original_question_images=[{
                'path': 'assets/revisions/task-diagram.png',
                'caption': 'Organisationsstruktur für die Bearbeitung der Frage',
                'source_page': 8,
            }],
            original_solution_images=[{
                'path': 'assets/revisions/private-solution.png',
                'caption': 'Musterlösung der Fallaufgabe',
                'source_page': 9,
            }],
        )
    return revised


def learning_history(hub):
    """Capture stored rows, including timestamps, SM2 state, and saved exam answers."""
    exported = hub.export()
    return {table: copy.deepcopy(exported[table]) for table in ('progress', 'attempts', 'exams')}


class QuestionRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'learning.sqlite3'
        self.hub = Hub(self.path)
        self.content = sample_import(['single_choice', 'exam_question'])
        self.module_id = self.hub.import_content(self.content)['module_id']

    def studied_active_exam(self):
        self.hub.attempt('test-single_choice', [0])
        self.hub.attempt('test-single_choice', [1])
        self.hub.attempt('test-exam_question', 'Vielfalt der Menschen')
        exam = self.hub.create_exam({
            'module_id': self.module_id, 'count': 2, 'duration_minutes': 60,
        })
        self.hub.update_exam(exam['id'], {
            'test-single_choice': [2], 'test-exam_question': 'Meine noch nicht abgegebene Antwort',
        }, 1)
        return exam['id']

    def test_ordinary_reimport_keeps_existing_question_and_context_immutable(self):
        exam_id = self.studied_active_exam()
        before = self.hub.question('test-exam_question')
        history = learning_history(self.hub)
        revised = context_revision(self.content)
        result = self.hub.import_content(revised)
        self.assertEqual(result['imported'], 0)
        self.assertEqual(self.hub.question('test-exam_question'), before)
        self.assertNotIn('question_context', self.hub.question('test-exam_question'))
        self.assertEqual(learning_history(self.hub), history)
        self.assertEqual(self.hub.raw_exam(exam_id)['status'], 'active')

    def test_explicit_context_revision_preserves_progress_attempts_and_active_exam_answers(self):
        exam_id = self.studied_active_exam()
        history = learning_history(self.hub)
        revised = context_revision(self.content)
        result = self.hub.import_content(revised, update_existing=True)
        self.assertEqual(result['imported'], 0, 'Revisions must not be counted as newly imported questions.')
        reopened = Hub(self.path)
        for expected in revised['questions']:
            actual = reopened.question(expected['id'])
            for field in ('question', 'question_context', 'question_context_source',
                          'original_question_images', 'original_solution_images'):
                self.assertEqual(actual[field], expected[field])
            self.assertEqual(actual['original_question'], expected['original_question'])
            self.assertEqual(actual['model_answer'], expected['model_answer'])
        self.assertEqual(learning_history(reopened), history)
        exam = reopened.raw_exam(exam_id)
        self.assertEqual(exam['status'], 'active')
        self.assertEqual(exam['answers'], {
            'test-single_choice': [2], 'test-exam_question': 'Meine noch nicht abgegebene Antwort',
        })
        self.assertEqual(exam['current_index'], 1)
        public = reopened.exam(exam_id)
        self.assertEqual(public['answers'], exam['answers'])
        self.assertTrue(all(question.get('question_context') for question in public['questions']))

    def test_revision_rejects_reusing_another_modules_question_id(self):
        revised = context_revision(self.content)
        revised['module'] = {'name': 'Ein anderes Modul', 'number': '88888'}
        before = self.hub.question('test-exam_question')
        with self.assertRaisesRegex(ValueError, 'anderen Modul'):
            self.hub.import_content(revised, update_existing=True)
        self.assertEqual(self.hub.question('test-exam_question'), before)


class QuestionRevisionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'study'
        self.project = self.source / 'master-learning-hub'
        write_seed_list(self.project)
        self.data = self.project / 'data'

    def app(self):
        return create_app(self.source, self.data, self.project, start_watch=False)

    def client(self, app):
        return TestClient(app, base_url='http://127.0.0.1', raise_server_exceptions=False)

    def test_public_import_endpoint_cannot_enable_revision_with_extra_flag(self):
        content = sample_import(['exam_question'])
        with self.client(self.app()) as client:
            imported = client.post('/api/import/confirm', json={'content': content})
            self.assertEqual(imported.status_code, 200, imported.text)
            response = client.post('/api/import/confirm', json={
                'content': context_revision(content), 'update_existing': True,
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['imported'], 0)
            saved = client.get('/api/questions').json()[0]
            self.assertEqual(saved['question'], content['questions'][0]['question'])
            self.assertNotIn('question_context', saved)

    def test_active_exam_api_exposes_task_context_and_diagrams_but_no_solution_fields(self):
        content = sample_import(['single_choice', 'multiple_choice', 'matching', 'cloze', 'exam_question'])
        revised = context_revision(content)
        hidden = {
            'correct_answers', 'pairs', 'answers', 'synonyms', 'model_answer',
            'original_question', 'original_solution', 'original_solution_images',
            'explanation', 'correction_note', 'keywords', 'checklist', 'progress',
        }
        app = self.app()
        with self.client(app) as client:
            imported = client.post('/api/import/confirm', json={'content': content})
            self.assertEqual(imported.status_code, 200, imported.text)
            exam = client.post('/api/exams', json={
                'module_id': imported.json()['module_id'], 'count': 5, 'duration_minutes': 60,
            })
            self.assertEqual(exam.status_code, 200, exam.text)
            exam_id = exam.json()['id']
            app.state.hub.import_content(revised, update_existing=True)
            saved_answers = {'test-single_choice': [1], 'test-exam_question': 'Mein Lösungsversuch'}
            responses = [
                client.patch(f'/api/exams/{exam_id}', json={'answers': saved_answers, 'current_index': 1}),
                client.get(f'/api/exams/{exam_id}'),
            ]
            expected = {question['id']: question for question in revised['questions']}
            for response in responses:
                self.assertEqual(response.status_code, 200, response.text)
                public = response.json()
                self.assertEqual(public['status'], 'active')
                self.assertEqual(public['answers'], saved_answers)
                self.assertEqual(len(public['questions']), 5)
                for question in public['questions']:
                    with self.subTest(endpoint=response.request.method, question=question['id']):
                        original = expected[question['id']]
                        self.assertEqual(question['question'], original['question'])
                        self.assertEqual(question['question_context'], original['question_context'])
                        self.assertEqual(question['question_context_source'], original['question_context_source'])
                        self.assertEqual(question['original_question_images'], original['original_question_images'])
                        self.assertFalse(hidden.intersection(question), 'Active exams must hide answer keys and solution material.')
                self.assertNotIn('private-solution.png', response.text)
                matching = next(question for question in public['questions'] if question['type'] == 'matching')
                self.assertCountEqual(matching['terms'], ['Diversität', 'Inklusion'])
                self.assertCountEqual(matching['definitions'], ['Vielfalt', 'Teilhabe'])
            self.assertEqual(app.state.hub.export()['attempts'], [], 'Saving an active answer must not mark it as studied.')

    def test_only_changed_approved_seed_revises_questions_on_restart(self):
        content = sample_import(['single_choice'])
        approved = self.project / 'imports' / 'digitale_diversitaet_einheit1.json'
        approved.write_text(json.dumps(content), encoding='utf-8')
        first_app = self.app()
        with self.client(first_app) as client:
            imported = client.get('/api/questions').json()
            self.assertEqual(len(imported), 1)
            hub = first_app.state.hub
            hub.attempt('test-single_choice', [0])
            exam = hub.create_exam({'module_id': imported[0]['module_id'], 'count': 1, 'duration_minutes': 60})
            hub.update_exam(exam['id'], {'test-single_choice': [1]})
            history = learning_history(hub)

        revised = context_revision(content)
        approved.write_text(json.dumps(revised), encoding='utf-8')
        unapproved = copy.deepcopy(revised)
        unapproved['questions'][0]['question'] = 'Diese beliebige Importdatei darf nicht automatisch überschreiben.'
        (self.project / 'imports' / 'unapproved_revision.json').write_text(json.dumps(unapproved), encoding='utf-8')
        second_app = self.app()
        with self.client(second_app) as client:
            saved = client.get('/api/questions').json()[0]
            self.assertEqual(saved['question'], revised['questions'][0]['question'])
            self.assertEqual(saved['question_context'], revised['questions'][0]['question_context'])
            self.assertEqual(learning_history(second_app.state.hub), history)
            response = client.get(f"/api/exams/{exam['id']}")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['answers'], {'test-single_choice': [1]})
            self.assertEqual(response.json()['questions'][0]['question_context'], saved['question_context'])
            pending = [doc for doc in second_app.state.hub.documents() if doc['path'].endswith('unapproved_revision.json')]
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]['status'], 'pending')


if __name__ == '__main__':
    unittest.main()
