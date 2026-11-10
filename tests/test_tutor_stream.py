"""Etappe 1: streamed tutor answers, cleaned PDF excerpts and excerpt metadata."""
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from backend.tutor import MAX_OUTPUT_TOKENS, MAX_THINKING_OUTPUT_TOKENS, OLLAMA_ENDPOINT, TutorService
from backend.tutor_context import _tidy_page
from tests import test_tutor as base  # module import: pytest must not collect TutorTests twice


class FakeStream:
    def __init__(self, lines):
        self.lines, self.closed = lines, False

    def __iter__(self):
        return iter(self.lines)

    def close(self):
        self.closed = True


def chunk(text, done=False):
    return json.dumps({'message': {'role': 'assistant', 'content': text}, 'done': done}).encode() + b'\n'


def thought(text):
    return json.dumps({'message': {'role': 'assistant', 'content': '', 'thinking': text}, 'done': False}).encode() + b'\n'


def thinking_model():
    return Mock(thinking=True, snapshot=Mock(return_value={'readiness': 'ready', 'message': 'Tutor bereit.', 'thinking': True}))


class TutorStreamTests(unittest.TestCase):
    # Reuse the isolated app setup of the existing tutor tests without re-running them.
    setUp = base.TutorTests.setUp
    write_page = base.TutorTests.write_page
    body = base.TutorTests.body

    def use_stream(self, opener, provider='ollama', transport=None):
        env = {'MLH_TUTOR_PROVIDER': provider, 'MLH_TUTOR_MODEL': 'selected-model',
               'MLH_OPENAI_API_KEY': 'secret-server-key'}
        self.app.state.tutor = TutorService(environ=env, transport=transport or Mock(), stream_transport=opener)
        return self.app.state.tutor

    def events(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'].split(';')[0], 'application/x-ndjson')
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_ollama_stream_sends_deltas_then_done_and_releases_lock(self):
        stream = FakeStream([chunk('Ein kleiner '), b'\n', chunk('Hinweis. [S1]'), chunk('', done=True)])
        opener = Mock(return_value=stream)
        service = self.use_stream(opener)
        events = self.events(self.client.post('/api/tutor/chat/stream', json=self.body()))
        self.assertEqual([event['type'] for event in events], ['delta', 'delta', 'done'])
        self.assertEqual(''.join(event['text'] for event in events[:2]), 'Ein kleiner Hinweis. [S1]')
        self.assertEqual(events[-1]['answer'], 'Ein kleiner Hinweis. [S1]')
        self.assertNotIn('nicht zuordenbare', events[-1]['notice'])
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, OLLAMA_ENDPOINT)
        payload = json.loads(request.data)
        self.assertTrue(payload['stream'])
        self.assertTrue(stream.closed)
        self.assertTrue(service._generation.acquire(blocking=False))
        service._generation.release()

    def test_stream_errors_are_events_without_provider_details(self):
        cases = [
            Mock(side_effect=HTTPError(OLLAMA_ENDPOINT, 404, 'secret', {}, io.BytesIO(b'secret-server-key'))),
            Mock(return_value=FakeStream([b'kein json\n'])),
            Mock(return_value=FakeStream([chunk('', done=True)])),
            Mock(side_effect=OSError('private diagnostic')),
        ]
        for opener in cases:
            with self.subTest(opener=opener):
                service = self.use_stream(opener)
                response = self.client.post('/api/tutor/chat/stream', json=self.body())
                events = self.events(response)
                self.assertEqual(events[-1]['type'], 'error')
                self.assertIn(events[-1]['status'], {502, 503})
                self.assertNotIn('secret', response.text)
                self.assertNotIn('private', response.text)
                self.assertTrue(service._generation.acquire(blocking=False))
                service._generation.release()

    def test_busy_stream_is_reported_without_calling_the_model(self):
        opener = Mock()
        service = self.use_stream(opener)
        service._generation.acquire()
        try:
            events = self.events(self.client.post('/api/tutor/chat/stream', json=self.body()))
        finally:
            service._generation.release()
        self.assertEqual(events, [{'type': 'error', 'status': 429, 'detail': events[0]['detail']}])
        opener.assert_not_called()

    def test_stream_validation_errors_keep_http_status(self):
        opener = Mock()
        self.use_stream(opener)
        self.assertEqual(self.client.post('/api/tutor/chat/stream', json=self.body(provider='x')).status_code, 400)
        self.assertEqual(self.client.post('/api/tutor/chat/stream', json=self.body(lesson_id='unbekannt')).status_code, 404)
        self.app.state.tutor = TutorService(environ={'MLH_TUTOR_PROVIDER': 'none'}, transport=Mock())
        self.assertEqual(self.client.post('/api/tutor/chat/stream', json=self.body()).status_code, 503)
        opener.assert_not_called()

    def test_openai_stream_falls_back_to_one_complete_answer(self):
        transport = Mock(return_value={'output': [{'type': 'message', 'role': 'assistant',
                                                   'content': [{'type': 'output_text', 'text': 'Antwort [S1]'}]}]})
        opener = Mock()
        self.use_stream(opener, provider='openai', transport=transport)
        events = self.events(self.client.post('/api/tutor/chat/stream', json=self.body()))
        self.assertEqual([event['type'] for event in events], ['delta', 'done'])
        self.assertEqual(events[-1]['answer'], 'Antwort [S1]')
        opener.assert_not_called()

    def test_context_reports_excerpts_per_source(self):
        context = self.client.get('/api/tutor/context', params={'module_id': self.mid, 'lesson_id': 'bi-metadaten'})
        self.assertEqual(context.status_code, 200, context.text)
        self.assertIsInstance(context.json()['excerpts'], dict)

    def test_local_models_get_compact_context_but_cloud_does_not(self):
        params = {'module_id': self.mid, 'lesson_id': 'bi-metadaten'}
        self.use_stream(Mock(), provider='ollama')
        local = self.client.get('/api/tutor/context', params=params).json()
        self.assertIn('kompakt', local['notice'])
        self.assertIn('Metadaten', local['context_text'])
        self.use_stream(Mock(), provider='openai')
        cloud = self.client.get('/api/tutor/context', params=params).json()
        self.assertNotIn('kompakt', cloud['notice'])

    def test_context_repeats_citation_rule_after_the_material(self):
        context = self.client.get('/api/tutor/context', params={'module_id': self.mid, 'lesson_id': 'bi-metadaten'}).json()
        self.assertTrue(context['sources'])
        tail = context['context_text'].split('ENDE DER UNVERTRAUTEN LERNDATEN.')[1]
        self.assertIn('Hinweis des Lernhubs', tail)
        self.assertIn('[S1]', tail)

    def test_optional_thinking_is_streamed_before_the_answer(self):
        opener = Mock(return_value=FakeStream([thought('Kernprozesse '), thought('stehen in S4.'),
                                               chunk('Architektur, Entwicklung, Betrieb [S1]'), chunk('', done=True)]))
        service = self.use_stream(opener)
        service.local = thinking_model()
        with patch('backend.tutor.local_model_info'):
            events = self.events(self.client.post('/api/tutor/chat/stream', json=self.body(think=True)))
        self.assertEqual([event['type'] for event in events], ['thinking', 'thinking', 'delta', 'done'])
        payload = json.loads(opener.call_args.args[0].data)
        self.assertIs(payload['think'], True)
        self.assertEqual(payload['options']['num_predict'], MAX_THINKING_OUTPUT_TOKENS)
        self.assertTrue(self.client.get('/api/tutor/status').json()['thinking'])

    def test_thinking_stays_off_unless_requested_and_supported(self):
        opener = Mock(return_value=FakeStream([chunk('Hinweis [S1]', done=True)]))
        service = self.use_stream(opener)
        service.local = thinking_model()
        with patch('backend.tutor.local_model_info'):
            self.events(self.client.post('/api/tutor/chat/stream', json=self.body()))
        payload = json.loads(opener.call_args.args[0].data)
        self.assertIs(payload['think'], False)
        self.assertEqual(payload['options']['num_predict'], MAX_OUTPUT_TOKENS)
        opener = Mock(return_value=FakeStream([chunk('Hinweis [S1]', done=True)]))
        self.use_stream(opener)  # model without thinking capability
        self.events(self.client.post('/api/tutor/chat/stream', json=self.body(think=True)))
        payload = json.loads(opener.call_args.args[0].data)
        self.assertNotIn('think', payload)
        self.assertEqual(payload['options']['num_predict'], MAX_OUTPUT_TOKENS)

    def test_think_flag_must_be_boolean(self):
        self.use_stream(Mock())
        self.assertEqual(self.client.post('/api/tutor/chat/stream', json=self.body(think='ja')).status_code, 400)

    def test_thinking_without_answer_reports_the_length_limit(self):
        opener = Mock(return_value=FakeStream([thought('Ich überlege sehr lange '), chunk('', done=True)]))
        service = self.use_stream(opener)
        service.local = thinking_model()
        with patch('backend.tutor.local_model_info'):
            events = self.events(self.client.post('/api/tutor/chat/stream', json=self.body(think=True)))
        self.assertEqual(events[-1]['type'], 'error')
        self.assertIn('Längenlimit', events[-1]['detail'])
        self.assertTrue(service._generation.acquire(blocking=False))
        service._generation.release()

    def test_free_chat_lists_learning_goals_but_goal_chat_does_not(self):
        goal = {'id': 'ziel-a', 'module_id': self.mid, 'lesson_id': 'bi-metadaten', 'section_id': None,
                'title': 'Metadaten erklären', 'question': 'Wozu?', 'criteria': 'Zweck.', 'sources': [], 'kind': 'Kapitelziel'}
        self.app.state.learning_memory.goals = [goal]
        params = {'module_id': self.mid, 'lesson_id': 'bi-metadaten'}
        free = self.client.get('/api/tutor/context', params=params).json()['context_text']
        tail = free.split('ENDE DER UNVERTRAUTEN LERNDATEN.')[1]
        self.assertIn('Im Lernprotokoll dieses Moduls', tail)
        self.assertIn('Metadaten erklären', tail)
        focused = self.client.get('/api/tutor/context', params={**params, 'goal_id': 'ziel-a'}).json()['context_text']
        self.assertNotIn('Im Lernprotokoll dieses Moduls', focused)

    def test_shortening_keeps_end_marker_and_hub_notes(self):
        service = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'm'}, transport=Mock())
        text = 'Lernstoff ' * 4000 + '\nENDE DER UNVERTRAUTEN LERNDATEN.' + '\n\nHinweis des Lernhubs: Belege mit [S1].'
        request, shortened = service._prepare({'context_text': text, 'sources': []}, 'Frage?', [])
        content = json.loads(request.data)['messages'][1]['content']
        self.assertTrue(shortened)
        self.assertTrue(content.endswith('Hinweis des Lernhubs: Belege mit [S1].'))
        self.assertLess(len(content.encode('utf-8')), len(text.encode('utf-8')))


class TidyPageTests(unittest.TestCase):
    def test_removes_watermarks_duplicate_labels_and_line_break_hyphens(self):
        raw = ('Betrieb\nIT-Controlling\nBetrieb\nIT-Controlling\n'
               'Die Führungsaufgabe lässt sich auf-\nteilen in vier Dimensionen.\n'
               'LmyoXz8VfBiuLZBI18PsssiS0wK9iLGwvy3ThOSocgn/u7Q+q8gLKV5mDHa6KOmZvOan5xHvcoU=\n'
               'Urheberrechtlich geschützt. Persönliche Kopie für Matrikelnummer 123')
        self.assertEqual(_tidy_page(raw), 'Betrieb\nIT-Controlling\nDie Führungsaufgabe lässt sich aufteilen in vier Dimensionen.')

    def test_keeps_capitalised_compounds_and_ordinary_text(self):
        text = 'Ressourcen- und Risikomanagement\nIT-\nSicherheit bleibt getrennt.'
        self.assertEqual(_tidy_page(text), text)


if __name__ == '__main__':
    unittest.main()
