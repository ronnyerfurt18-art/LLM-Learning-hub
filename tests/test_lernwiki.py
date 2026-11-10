"""Etappe 2: Lernwiki – Musterlösung je Lernziel erzeugen, speichern, wiederverwenden, verbessern."""
import json
import unittest
from unittest.mock import Mock

from backend.tutor import TutorService
from tests import test_tutor as base  # module import: pytest must not collect TutorTests twice


class FakeStream:
    def __init__(self, lines):
        self.lines = lines

    def __iter__(self):
        return iter(self.lines)

    def close(self):
        pass


def chunk(text, done=False):
    return json.dumps({'message': {'role': 'assistant', 'content': text}, 'done': done}).encode() + b'\n'


class LernwikiTests(unittest.TestCase):
    setUp_base = base.TutorTests.setUp
    write_page = base.TutorTests.write_page

    def setUp(self):
        self.setUp_base()
        self.goal = {'id': 'ziel-metadaten', 'module_id': self.mid, 'lesson_id': 'bi-metadaten', 'section_id': None,
                     'title': 'Metadaten erklären', 'question': 'Wozu dienen Metadaten?', 'criteria': 'Zweck nennen; Beispiel geben.',
                     'sources': [], 'kind': 'Kapitelziel'}
        self.app.state.learning_memory.goals = [self.goal]

    def use_stream(self, *answers):
        opener = Mock(side_effect=[FakeStream([chunk(text), chunk('', done=True)]) for text in answers])
        self.app.state.tutor = TutorService(environ={'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'qwen3.8:27b-mlx'},
                                            transport=Mock(), stream_transport=opener)
        return opener

    def read(self, **params):
        response = self.client.get('/api/tutor/wiki', params={'module_id': self.mid, 'goal_id': 'ziel-metadaten', **params})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def generate(self, **body):
        response = self.client.post('/api/tutor/wiki/generate/stream', json={'module_id': self.mid, 'goal_id': 'ziel-metadaten', **body})
        self.assertEqual(response.status_code, 200, response.text)
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_solution_is_stored_once_and_reused_without_model_call(self):
        self.assertEqual(self.read(), {'entry': None, 'versions': [], 'stale': False})
        opener = self.use_stream('## Kurzantwort\nMetadaten beschreiben Daten. [S1]')
        events = self.generate()
        self.assertEqual([event['type'] for event in events], ['delta', 'done'])
        entry = events[-1]['entry']
        self.assertEqual((entry['version'], entry['status'], entry['model']), (1, 'draft', 'qwen3.8:27b-mlx'))
        payload = json.loads(opener.call_args.args[0].data)
        self.assertTrue(payload['messages'][0]['content'].startswith('Du erstellst eine Musterlösung'))
        self.assertIn('Kontrollfrage: Wozu dienen Metadaten?', payload['messages'][-1]['content'])
        self.assertEqual(payload['options']['num_predict'], 2200)
        stored = self.read()
        self.assertEqual(stored['entry']['id'], entry['id'])
        self.assertFalse(stored['stale'])
        self.assertEqual(opener.call_count, 1)

    def test_improvement_creates_new_version_and_keeps_old(self):
        opener = self.use_stream('Erste Fassung [S1]', 'Zweite Fassung [S1]')
        first = self.generate()[-1]['entry']
        second = self.generate(base_id=first['id'], improve='Beispiel ergänzen')[-1]['entry']
        self.assertEqual((second['version'], second['improve_note']), (2, 'Beispiel ergänzen'))
        task = json.loads(opener.call_args.args[0].data)['messages'][-1]['content']
        self.assertIn('BISHERIGE MUSTERLÖSUNG (Version 1)', task)
        self.assertIn('Beispiel ergänzen', task)
        self.assertEqual([v['version'] for v in self.read()['versions']], [2, 1])
        self.assertEqual(self.read(id=first['id'])['entry']['answer'], 'Erste Fassung [S1]')

    def test_review_status_and_errors(self):
        self.use_stream('Fassung [S1]')
        entry = self.generate()[-1]['entry']
        body = {'module_id': self.mid, 'goal_id': 'ziel-metadaten', 'id': entry['id']}
        reviewed = self.client.post('/api/tutor/wiki/status', json={**body, 'status': 'reviewed'})
        self.assertEqual(reviewed.json()['status_label'], 'Von dir geprüft')
        self.assertEqual(self.client.post('/api/tutor/wiki/status', json={**body, 'status': 'final'}).status_code, 400)
        self.assertEqual(self.client.post('/api/tutor/wiki/status', json={**body, 'id': 'fehlt', 'status': 'draft'}).status_code, 404)
        self.assertEqual(self.client.post('/api/tutor/wiki/status', json={**body, 'module_id': 'anderes', 'status': 'draft'}).status_code, 400)

    def test_invalid_requests_are_rejected_before_the_model(self):
        opener = self.use_stream('nie')
        url = '/api/tutor/wiki/generate/stream'
        body = {'module_id': self.mid, 'goal_id': 'ziel-metadaten'}
        for extra in ({'x': 1}, {'think': 'ja'}, {'improve': 'a' * 1001}, {'goal_id': 'fremd'}):
            with self.subTest(extra=extra):
                self.assertEqual(self.client.post(url, json={**body, **extra}).status_code, 400)
        self.assertEqual(self.client.post(url, json={**body, 'base_id': 'fehlt'}).status_code, 404)
        opener.assert_not_called()

    def test_busy_model_stores_nothing_and_changed_context_is_flagged(self):
        self.use_stream('Fassung [S1]')
        service = self.app.state.tutor
        service._generation.acquire()
        try:
            events = self.generate()
        finally:
            service._generation.release()
        self.assertEqual((events[-1]['type'], events[-1]['status']), ('error', 429))
        self.assertIsNone(self.read()['entry'])
        self.generate()
        with self.app.state.lernwiki.hub.db() as db:
            db.execute("UPDATE tutor_wiki_entries SET context_hash='alt'")
        self.assertTrue(self.read()['stale'])


if __name__ == '__main__':
    unittest.main()
