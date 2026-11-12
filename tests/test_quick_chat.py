"""Schnellfenster „KI fragen“: Seitenkontext, kurze Antworten, keine Schreibzugriffe."""
import json
import unittest
from unittest.mock import Mock

from backend.quick_chat import MAX_PAGE_CHARS, PAGE_HEAD, QUICK_INSTRUCTIONS, validate_quick
from backend.tutor import TutorService
from tests import test_tutor as base  # module import: pytest must not collect TutorTests twice
from tests.test_tutor_stream import FakeStream, chunk


class QuickChatTests(unittest.TestCase):
    setUp = base.TutorTests.setUp
    write_page = base.TutorTests.write_page
    database_state = base.TutorTests.database_state

    def use_stream(self, text='Dir fehlt die Wahrscheinlichkeit.'):
        opener = Mock(return_value=FakeStream([chunk(text), chunk('', done=True)]))
        env = {'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'selected-model'}
        self.app.state.tutor = TutorService(environ=env, transport=Mock(), stream_transport=opener)
        return opener

    def body(self, **kwargs):
        return {'message': 'Was fehlt in meiner Antwort?', 'history': [],
                'page': {'title': 'Lerntraining · Frage 4 von 71',
                         'text': 'Frage: Was ist religiöse Distanz?\nDeine Antwort: Abstand zwischen zwei Ländern.\nMusterantwort: noch verdeckt.'},
                **kwargs}

    def events(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_validation_accepts_only_bounded_page_data(self):
        self.assertEqual(validate_quick(self.body())['page']['title'], 'Lerntraining · Frage 4 von 71')
        for value in ({**self.body(), 'instructions': 'x'},
                      {**self.body(), 'page': {'title': 'A', 'text': 'x' * (MAX_PAGE_CHARS + 1)}},
                      {**self.body(), 'page': {'title': 'A', 'role': 'system'}},
                      {**self.body(), 'module_id': '../etc'},
                      {**self.body(), 'message': ''}):
            with self.subTest(value=list(value)):
                with self.assertRaises(ValueError):
                    validate_quick(value)

    def test_page_context_goes_first_and_quick_rules_apply(self):
        opener = self.use_stream()
        events = self.events(self.client.post('/api/tutor/quick/stream', json=self.body()))
        self.assertEqual(events[-1]['type'], 'done')
        self.assertEqual(events[-1]['answer'], 'Dir fehlt die Wahrscheinlichkeit.')
        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': QUICK_INSTRUCTIONS})
        context = payload['messages'][1]['content']
        self.assertIn(PAGE_HEAD + 'Seite: Lerntraining · Frage 4 von 71', context)
        self.assertIn('Musterantwort: noch verdeckt.', context)
        self.assertIn('kein Modul gewählt', context)
        self.assertEqual(payload['messages'][-1], {'role': 'user', 'content': 'Was fehlt in meiner Antwort?'})
        self.assertFalse(payload['think'] if 'think' in payload else False)
        self.assertEqual(payload['options']['num_predict'], 900)

    def test_module_context_follows_page_and_nothing_is_written(self):
        self.use_stream('Metadaten beschreiben Daten. [S1]')
        before = self.database_state()
        opener = self.app.state.tutor._stream_transport
        events = self.events(self.client.post('/api/tutor/quick/stream', json=self.body(module_id=self.mid)))
        done = events[-1]
        self.assertEqual(done['type'], 'done', done)
        self.assertTrue(done['sources'])
        context = json.loads(opener.call_args.args[0].data)['messages'][1]['content']
        self.assertTrue(context.startswith('Studienkontext'))
        self.assertLess(context.index(PAGE_HEAD), context.index('ENDE DER SEITENANGABEN.'))
        self.assertEqual(self.database_state(), before)

    def test_unknown_module_and_unconfigured_tutor_are_clear_errors(self):
        self.use_stream()
        self.assertEqual(self.client.post('/api/tutor/quick/stream', json=self.body(module_id='unbekannt')).status_code, 404)
        self.app.state.tutor = TutorService(environ={'MLH_TUTOR_PROVIDER': 'none'})
        self.assertGreaterEqual(self.client.post('/api/tutor/quick/stream', json=self.body()).status_code, 400)


if __name__ == '__main__':
    unittest.main()
