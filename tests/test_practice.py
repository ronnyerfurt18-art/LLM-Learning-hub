"""Practice rounds persist atomically and share the latest-attempt mistakes pool."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core import validate_import
from backend.main import create_app
from tests.test_core import sample_import


def feedback_content():
    content = sample_import()
    content['questions'][1].update(unit=2, difficulty=2)
    question = content['questions'][0]
    question['option_explanations'] = [
        'Vielfalt beschreibt Unterschiede.',
        'Gleichheit bezeichnet hier nicht das gesuchte Konzept.',
        'Menschen allein bezeichnet keine Verschiedenheit.',
    ]
    question['learning_context'] = {
        'title': 'Alle Begriffe im Zusammenhang',
        'paragraphs': ['BELEGTERLERNKONTEXT beschreibt Unterschiede und ihre Einordnung.'],
        'table': {'headers': ['Begriff', 'Bedeutung'], 'rows': [['Diversität', 'Vielfalt']]},
        'sources': [{'kind': 'pdf', 'path': 'material/lehrbrief.pdf', 'title': 'Lehrbrief', 'pdf_page': 2}],
        'lesson_id': 'modell-ueberblick',
    }
    return content


class PracticeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'study'
        self.project = self.source / 'master-learning-hub'
        (self.project / 'imports').mkdir(parents=True)
        self.app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        self.client = TestClient(self.app, base_url='http://127.0.0.1', raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.content = feedback_content()
        self.mid = self.app.state.hub.import_content(self.content)['module_id']

    def snapshot(self):
        with self.app.state.hub.db() as database:
            return '\n'.join(database.iterdump())

    def create(self, **config):
        response = self.client.post('/api/practice', json={'module_id': self.mid, **config})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def answer(self, round_id, qid, answer):
        response = self.client.post(f'/api/practice/{round_id}/answer', json={'question_id': qid, 'answer': answer})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def attempt(self, qid, answer):
        response = self.client.post('/api/attempts', json={'question_id': qid, 'answer': answer})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def mistakes(self, **filters):
        response = self.client.get('/api/mistakes', params=filters)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def exam(self, kind, answer):
        response = self.client.post('/api/exams', json={
            'module_id': self.mid, 'count': 1, 'types': [kind], 'duration_minutes': 10,
        })
        self.assertEqual(response.status_code, 200, response.text)
        exam = response.json()
        qid = exam['questions'][0]['id']
        submitted = self.client.post(f"/api/exams/{exam['id']}/submit", json={'answers': {qid: answer}})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        return submitted.json()

    def test_shared_mistakes_follow_latest_training_and_exam_attempts(self):
        self.assertEqual(self.mistakes(module_id=self.mid), [])
        self.attempt('test-single_choice', [1])
        self.attempt('test-multiple_choice', [0, 2])
        self.assertEqual({q['id'] for q in self.mistakes()}, {'test-single_choice'})
        self.exam('single_choice', [0])
        self.assertEqual(self.mistakes(), [])
        self.attempt('test-single_choice', [1])
        self.exam('multiple_choice', [1])
        self.assertEqual({q['id'] for q in self.mistakes()}, {'test-single_choice', 'test-multiple_choice'})
        self.assertEqual({q['id'] for q in self.mistakes(module_id=self.mid, unit=2)}, {'test-multiple_choice'})
        self.attempt('test-multiple_choice', [0, 2])
        self.assertEqual({q['id'] for q in self.mistakes()}, {'test-single_choice'})

    def test_latest_attempt_ties_use_insertion_order_and_partial_answers_are_mistakes(self):
        first = self.attempt('test-single_choice', [1])
        second = self.attempt('test-single_choice', [0])
        with self.app.state.hub.db() as database:
            database.execute('UPDATE attempts SET created_at=? WHERE id IN (?,?)',
                             ('2026-10-16T10:00:00+00:00', first['id'], second['id']))
        self.assertEqual(self.mistakes(), [])
        partial = self.attempt('test-matching', {'Diversität': 'Vielfalt'})
        self.assertEqual(partial['score'], .5)
        self.assertEqual(self.mistakes()[0]['id'], 'test-matching')

    def test_full_keyword_match_stays_pending_until_self_assessment_and_uses_latest_attempt(self):
        first = self.attempt('test-free_text', 'Vielfalt der Menschen')
        self.assertEqual((first['score'], first['grading']), (1, 'keyword_hint'))
        pending = self.mistakes()[0]
        self.assertEqual(pending['mistake_status'], 'needs_review')
        self.assertEqual(pending['latest_attempt']['id'], first['id'])
        self.assertEqual(self.client.patch(f"/api/attempts/{first['id']}", json={'manual_score': 1}).status_code, 200)
        self.assertEqual(self.mistakes(), [])
        self.client.patch(f"/api/attempts/{first['id']}", json={'manual_score': 0})
        self.assertEqual(self.mistakes()[0]['mistake_status'], 'incorrect')
        latest = self.attempt('test-free_text', 'Keine passenden Begriffe')
        self.client.patch(f"/api/attempts/{first['id']}", json={'manual_score': 1})
        self.assertEqual(self.mistakes()[0]['latest_attempt']['id'], latest['id'])
        self.client.patch(f"/api/attempts/{latest['id']}", json={'manual_score': 1})
        self.assertEqual(self.mistakes(), [])

    def test_filters_and_count_select_available_questions_and_exclude_flashcards(self):
        state = self.create(count=200)
        self.assertEqual(state['count'], 7)
        self.assertNotIn('flashcard', {q['type'] for q in state['questions']})
        selected = self.create(units=[2], types=['multiple_choice'], difficulty=2, count=10)
        self.assertEqual(selected['question_ids'], ['test-multiple_choice'])
        self.assertEqual(self.app.state.hub.export()['attempts'], [])
        self.attempt('test-single_choice', [1])
        errors = self.create(mistakes_only=True)
        self.assertEqual(errors['question_ids'], ['test-single_choice'])
        self.attempt('test-single_choice', [0])
        self.assertEqual(self.client.post('/api/practice', json={'module_id': self.mid, 'mistakes_only': True}).status_code, 400)

    def test_mistakes_count_and_practice_pool_both_exclude_failed_flashcards(self):
        failed_card = self.client.post('/api/attempts', json={
            'question_id': 'test-flashcard', 'answer': '', 'rating': 0,
        })
        self.assertEqual(failed_card.status_code, 200, failed_card.text)
        self.assertEqual(self.app.state.hub.progress('test-flashcard')['incorrect'], 1)
        self.assertEqual(self.mistakes(module_id=self.mid), [])
        empty_round = self.client.post('/api/practice', json={'module_id': self.mid, 'mistakes_only': True})
        self.assertEqual(empty_round.status_code, 400)
        self.attempt('test-single_choice', [1])
        mistakes = self.mistakes(module_id=self.mid)
        state = self.create(mistakes_only=True, count=200)
        self.assertEqual(state['count'], len(mistakes))
        self.assertEqual(state['question_ids'], ['test-single_choice'])

    def test_round_list_can_filter_modules_without_mutating_rounds(self):
        own = self.create(types=['single_choice'], count=1)
        own_second = self.create(types=['free_text'], count=1)
        other = sample_import(['single_choice'])
        other['module'] = {'name': 'Anderes Modul', 'number': '88888'}
        other['questions'][0]['id'] = 'foreign-question'
        other_mid = self.app.state.hub.import_content(other)['module_id']
        response = self.client.post('/api/practice', json={'module_id': other_mid, 'count': 1})
        self.assertEqual(response.status_code, 200, response.text)
        foreign = response.json()
        before = self.snapshot()
        all_rounds = self.client.get('/api/practice').json()
        self.assertEqual({state['id'] for state in all_rounds}, {own['id'], own_second['id'], foreign['id']})
        filtered = self.client.get('/api/practice', params={'module_id': self.mid})
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual({state['id'] for state in filtered.json()}, {own['id'], own_second['id']})
        foreign_rounds = self.client.get('/api/practice', params={'module_id': other_mid}).json()
        self.assertEqual([state['id'] for state in foreign_rounds], [foreign['id']])
        self.assertEqual(self.client.get('/api/practice', params={'module_id': 'missing-module'}).status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_round_and_feedback_survive_restart_through_completion(self):
        state = self.create(types=['single_choice', 'multiple_choice'], count=2)
        rid = state['id']
        checked = self.answer(rid, 'test-single_choice', [0])
        self.assertEqual((checked['checked_count'], checked['score']), (1, 1))
        self.assertEqual(self.client.patch(f'/api/practice/{rid}', json={'current_index': 1}).status_code, 200)
        reopened = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(reopened, base_url='http://127.0.0.1', raise_server_exceptions=False) as client:
            restored = client.get(f'/api/practice/{rid}').json()
            self.assertEqual((restored['current_index'], restored['answers']['test-single_choice']), (1, [0]))
            response = client.post(f'/api/practice/{rid}/answer', json={'question_id': 'test-multiple_choice', 'answer': [0, 2]})
            self.assertEqual(response.status_code, 200, response.text)
            finished = client.post(f'/api/practice/{rid}/finish').json()
            self.assertEqual((finished['status'], finished['percentage'], finished['checked_count']), ('completed', 100, 2))
        restored = self.client.get(f'/api/practice/{rid}').json()
        self.assertEqual(restored['status'], 'completed')
        self.assertEqual(len(self.client.get('/api/practice').json()), 1)
        self.assertEqual(len(self.app.state.hub.export()['attempts']), 2)

    def test_double_answer_and_finish_posts_never_create_duplicate_attempts(self):
        state = self.create(types=['single_choice'], count=1)
        first = self.answer(state['id'], 'test-single_choice', [1])
        second = self.answer(state['id'], 'test-single_choice', [1])
        self.assertEqual(first['results'][0]['attempt_id'], second['results'][0]['attempt_id'])
        self.client.post(f"/api/practice/{state['id']}/finish")
        self.client.post(f"/api/practice/{state['id']}/finish")
        self.answer(state['id'], 'test-single_choice', [1])
        before = self.snapshot()
        changed = self.client.post(f"/api/practice/{state['id']}/answer", json={'question_id': 'test-single_choice', 'answer': [0]})
        self.assertEqual(changed.status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.app.state.hub.export()['attempts']), 1)
        self.assertEqual(self.app.state.hub.progress('test-single_choice')['attempts'], 1)

    def test_invalid_answers_and_unrelated_question_ids_leave_no_partial_writes(self):
        other = sample_import(['single_choice'])
        other['module'] = {'name': 'Anderes Modul', 'number': '88888'}
        other['questions'][0]['id'] = 'foreign-question'
        self.app.state.hub.import_content(other)
        state = self.create(types=['single_choice'], count=1)
        invalid = [
            {'question_id': 'foreign-question', 'answer': [0]},
            {'question_id': 'test-multiple_choice', 'answer': [0, 2]},
            {'question_id': 'unknown', 'answer': [0]},
            {'question_id': [], 'answer': [0]},
            {'question_id': 'test-single_choice', 'answer': [99]},
            {'question_id': 'test-single_choice', 'answer': [True]},
            {'question_id': 'test-single_choice', 'answer': [0, 1]},
            {'question_id': 'test-single_choice', 'answer': '0'},
            {'question_id': 'test-single_choice'},
            {'question_id': 'test-single_choice', 'answer': [0], 'manual_score': 1},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                before = self.snapshot()
                response = self.client.post(f"/api/practice/{state['id']}/answer", json=payload)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self.snapshot(), before)

    def test_unchecked_questions_finish_at_zero_without_learning_attempts(self):
        state = self.create(types=['single_choice', 'multiple_choice'], count=2)
        self.answer(state['id'], 'test-single_choice', [0])
        finished = self.client.post(f"/api/practice/{state['id']}/finish").json()
        self.assertEqual((finished['percentage'], finished['checked_count'], finished['max_score']), (50, 1, 2))
        skipped = next(result for result in finished['results'] if result['question_id'] == 'test-multiple_choice')
        self.assertEqual((skipped['unanswered'], skipped['score'], skipped['attempt_id']), (True, 0, None))
        self.assertEqual(skipped['grading'], 'unanswered')
        self.assertEqual(self.app.state.hub.progress('test-multiple_choice')['attempts'], 0)
        self.assertEqual(self.mistakes(), [])
        before = self.snapshot()
        response = self.client.post(f"/api/practice/{state['id']}/answer", json={'question_id': 'test-multiple_choice', 'answer': [0, 2]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_entirely_unchecked_round_can_finish_without_attempts(self):
        state = self.create(types=['free_text'], count=1)
        finished = self.client.post(f"/api/practice/{state['id']}/finish").json()
        self.assertEqual((finished['score'], finished['percentage'], finished['checked_count'], finished['pending_count']), (0, 0, 0, 0))
        self.assertEqual(self.app.state.hub.export()['attempts'], [])

    def test_self_assessment_updates_completed_round_results_without_new_attempts(self):
        state = self.create(types=['free_text'], count=1)
        checked = self.answer(state['id'], 'test-free_text', 'Vielfalt der Menschen')
        self.assertEqual((checked['pending_count'], checked['correct_count']), (1, 0))
        aid = checked['results'][0]['attempt_id']
        self.client.post(f"/api/practice/{state['id']}/finish")
        self.client.patch(f'/api/attempts/{aid}', json={'manual_score': 0})
        corrected = self.client.get(f"/api/practice/{state['id']}").json()
        self.assertEqual((corrected['score'], corrected['percentage'], corrected['pending_count']), (0, 0, 0))
        self.assertEqual(corrected['results'][0]['grading'], 'self')
        self.client.patch(f'/api/attempts/{aid}', json={'manual_score': 1})
        corrected = self.client.get(f"/api/practice/{state['id']}").json()
        self.assertEqual((corrected['percentage'], corrected['correct_count']), (100, 1))
        self.assertEqual(len(self.app.state.hub.export()['attempts']), 1)
        self.assertEqual(self.mistakes(), [])

    def test_export_includes_round_metadata_and_attempt_links(self):
        state = self.create(types=['single_choice'], count=1)
        answered = self.answer(state['id'], 'test-single_choice', [0])
        exported = self.client.get('/api/export').json()
        record = next(row for row in exported['metadata'] if row['key'] == 'practice_round:' + state['id'])
        persisted = json.loads(record['value'])
        self.assertEqual(persisted['question_ids'], ['test-single_choice'])
        self.assertEqual(persisted['answers']['test-single_choice'], [0])
        self.assertEqual(persisted['results'][0]['attempt_id'], answered['results'][0]['attempt_id'])
        self.assertEqual(exported['attempts'][0]['id'], persisted['results'][0]['attempt_id'])

    def test_config_and_cursor_validation_never_mutate_existing_data(self):
        invalid = [
            ({}, 400), ({'module_id': ''}, 400), ({'module_id': []}, 400),
            ({'module_id': 'missing-module'}, 404),
        ]
        for field, values in {
            'count': [0, 201, True, '2', 1.5],
            'units': [None, {}, '', [0], [True], ['1'], [1000]],
            'types': [None, {}, '', ['flashcard'], ['unknown'], [True]],
            'mistakes_only': [1, 'true', None],
            'difficulty': [0, 4, True, '1'],
        }.items():
            invalid.extend(({'module_id': self.mid, field: value}, 400) for value in values)
        invalid.append(({'module_id': self.mid, 'unknown_setting': True}, 400))
        for config, status in invalid:
            with self.subTest(config=config):
                before = self.snapshot()
                response = self.client.post('/api/practice', json=config)
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(self.snapshot(), before)
        state = self.create(types=['single_choice'])
        for value in (-1, 1, True, '0'):
            before = self.snapshot()
            response = self.client.patch(f"/api/practice/{state['id']}", json={'current_index': value})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.snapshot(), before)
        for method, path, payload in [
            ('get', '/api/practice/unknown', None),
            ('post', '/api/practice/unknown/finish', {}),
            ('post', '/api/practice/unknown/answer', {'question_id': 'test-single_choice', 'answer': [0]}),
        ]:
            before = self.snapshot()
            response = self.client.request(method, path, json=payload)
            self.assertEqual(response.status_code, 404, response.text)
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.get('/api/mistakes', params={'unit': 0}).status_code, 422)
        self.assertEqual(self.client.get('/api/mistakes', params={'module_id': 'unknown'}).status_code, 404)

    def test_foreign_origin_cannot_create_answer_move_or_finish_practice(self):
        state = self.create(types=['single_choice'])
        paths = [
            ('post', '/api/practice', {'module_id': self.mid}),
            ('post', f"/api/practice/{state['id']}/answer", {'question_id': 'test-single_choice', 'answer': [0]}),
            ('patch', f"/api/practice/{state['id']}", {'current_index': 0}),
            ('post', f"/api/practice/{state['id']}/finish", {}),
        ]
        for method, path, payload in paths:
            with self.subTest(path=path):
                before = self.snapshot()
                response = self.client.request(method, path, json=payload, headers={'origin': 'https://foreign.example'})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.snapshot(), before)

    def test_practice_feedback_has_full_content_but_active_exam_hides_new_answer_fields(self):
        response = self.client.post('/api/exams', json={
            'module_id': self.mid, 'count': 1, 'types': ['single_choice'], 'duration_minutes': 10,
        })
        self.assertEqual(response.status_code, 200, response.text)
        active = response.json()
        for key in ('option_explanations', 'learning_context', 'correct_answers', 'model_answer', 'explanation'):
            self.assertNotIn(key, active['questions'][0])
        self.assertNotIn('BELEGTERLERNKONTEXT', json.dumps(active))
        state = self.create(types=['single_choice'], count=1)
        feedback = self.answer(state['id'], 'test-single_choice', [1])['results'][0]
        question = feedback['question']
        for key in ('options', 'correct_answers', 'model_answer', 'explanation', 'option_explanations', 'learning_context'):
            self.assertIn(key, question)
        for key in ('score', 'correct', 'grading', 'matched_keywords', 'missing_keywords', 'answer', 'attempt_id'):
            self.assertIn(key, feedback)
        self.assertEqual(question['option_explanations'], self.content['questions'][0]['option_explanations'])
        self.assertEqual(question['learning_context'], self.content['questions'][0]['learning_context'])


class FeedbackImportValidationTests(unittest.TestCase):
    def test_complete_feedback_and_table_only_context_are_valid(self):
        content = feedback_content()
        self.assertEqual(validate_import(content), [])
        content['questions'][0]['learning_context']['paragraphs'] = []
        self.assertEqual(validate_import(content), [])

    def test_option_feedback_requires_one_nonempty_explanation_per_choice(self):
        for value in (None, [], ['too short'], ['a', '', 'c'], ['a', None, 'c'], 'text'):
            with self.subTest(value=value):
                content = feedback_content()
                content['questions'][0]['option_explanations'] = value
                self.assertTrue(validate_import(content))
        content = sample_import(['free_text'])
        content['questions'][0]['option_explanations'] = ['not a choice question']
        self.assertTrue(validate_import(content))

    def test_context_rejects_missing_content_bad_tables_and_invalid_source_references(self):
        valid = feedback_content()['questions'][0]['learning_context']
        variants = [None, {}, {**valid, 'title': ''}, {**valid, 'paragraphs': None},
                    {**valid, 'paragraphs': ['']}, {**valid, 'paragraphs': [], 'table': None},
                    {**valid, 'sources': []}, {**valid, 'table': {'headers': ['one'], 'rows': [['a', 'b']]}},
                    {**valid, 'sources': [{'path': '../private.pdf', 'title': 'Outside', 'pdf_page': 1}]},
                    {**valid, 'sources': [{'path': 'material/book.pdf', 'title': 'Book', 'pdf_page': True}]}]
        for value in variants:
            with self.subTest(value=value):
                content = feedback_content()
                content['questions'][0]['learning_context'] = copy.deepcopy(value)
                self.assertTrue(validate_import(content))


if __name__ == '__main__':
    unittest.main()
