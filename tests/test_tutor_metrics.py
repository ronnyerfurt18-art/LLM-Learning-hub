"""Measured values of a model request: provider statistics, the hub's clock, and honest gaps."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from backend.bonsai import MODEL as BONSAI_MODEL, StreamAdapter
from backend.tutor import TutorService
from backend.tutor_metrics import Stopwatch, bonsai_stats, memory_snapshot, ollama_stats, performance
from tests import test_tutor as base
from tests.test_tutor_stream import FakeStream, chunk, thinking_model, thought

# Final object of Ollama 0.35.0 for a repeated request (values from a real run, shortened).
OLLAMA_DONE = {'done': True, 'done_reason': 'stop', 'total_duration': 947703083, 'load_duration': 5894958,
               'prompt_eval_count': 3441, 'prompt_eval_cached_count': 3436, 'prompt_eval_duration': 200000000,
               'eval_count': 240, 'eval_duration': 22030000000}


class OllamaStatsTests(unittest.TestCase):
    def test_reads_tokens_cache_and_speeds(self):
        stats = ollama_stats(OLLAMA_DONE)
        self.assertEqual((stats['prompt_tokens'], stats['cached_tokens'], stats['new_prompt_tokens']), (3441, 3436, 5))
        self.assertAlmostEqual(stats['cache_ratio'], 3436 / 3441)
        self.assertAlmostEqual(stats['prefill_seconds'], 0.2)
        self.assertAlmostEqual(stats['prefill_tokens_per_second'], 25.0)
        self.assertAlmostEqual(stats['decode_tokens_per_second'], 240 / 22.03)
        self.assertAlmostEqual(stats['load_seconds'], 0.005894958)

    def test_missing_cache_count_is_unknown_not_zero_and_not_a_hit(self):
        item = {key: value for key, value in OLLAMA_DONE.items() if key != 'prompt_eval_cached_count'}
        stats = ollama_stats(item)
        self.assertEqual(stats['prompt_tokens'], 3441)
        for key in ('cached_tokens', 'new_prompt_tokens', 'cache_ratio', 'prefill_tokens_per_second'):
            self.assertIsNone(stats[key], key)
        self.assertAlmostEqual(stats['prefill_seconds'], 0.2)

    def test_a_cold_request_reports_zero_reused_tokens(self):
        stats = ollama_stats({**OLLAMA_DONE, 'prompt_eval_cached_count': 0, 'prompt_eval_duration': 72610000000})
        self.assertEqual((stats['cached_tokens'], stats['new_prompt_tokens'], stats['cache_ratio']), (0, 3441, 0.0))
        self.assertAlmostEqual(stats['prefill_tokens_per_second'], 3441 / 72.61)

    def test_empty_invalid_or_implausible_values_stay_unknown(self):
        for item in ({}, None, 'text', {'prompt_eval_count': 'viel', 'eval_count': True, 'eval_duration': -1},
                     {'prompt_eval_count': float('inf'), 'eval_count': float('nan')}):
            with self.subTest(item=item):
                stats = ollama_stats(item)
                self.assertTrue(all(value is None for value in stats.values()), stats)
        stats = ollama_stats({'prompt_eval_count': 10, 'prompt_eval_cached_count': 50})
        self.assertEqual(stats['prompt_tokens'], 10)
        self.assertIsNone(stats['cached_tokens'])
        self.assertIsNone(stats['cache_ratio'])


class BonsaiStatsTests(unittest.TestCase):
    usage = {'prompt_tokens': 4362, 'completion_tokens': 341, 'prompt_tokens_details': {'cached_tokens': 0}}
    timings = {'prompt_n': 4362, 'cache_n': 0, 'predicted_n': 341, 'prompt_ms': 98459.0, 'prompt_per_second': 44.3,
               'predicted_ms': 46983.0, 'predicted_per_second': 7.2, 'peak_memory': 9.5}

    def test_reads_usage_and_timings_without_a_load_time(self):
        stats = bonsai_stats(self.usage, self.timings)
        self.assertEqual((stats['prompt_tokens'], stats['cached_tokens'], stats['output_tokens']), (4362, 0, 341))
        self.assertIsNone(stats['load_seconds'])
        self.assertAlmostEqual(stats['prefill_seconds'], 98.459)
        self.assertAlmostEqual(stats['prefill_tokens_per_second'], 44.3)
        self.assertAlmostEqual(stats['decode_tokens_per_second'], 7.2)
        self.assertEqual(stats['peak_memory_bytes'], 9_500_000_000)

    def test_reading_time_is_withheld_when_part_of_the_prompt_was_reused(self):
        usage = {**self.usage, 'prompt_tokens_details': {'cached_tokens': 4096}}
        stats = bonsai_stats(usage, {**self.timings, 'cache_n': 4096})
        self.assertEqual((stats['cached_tokens'], stats['new_prompt_tokens']), (4096, 266))
        self.assertIsNone(stats['prefill_seconds'])
        self.assertIsNone(stats['prefill_tokens_per_second'])

    def test_stream_without_usage_reports_nothing(self):
        stats = bonsai_stats(None, None)
        self.assertTrue(all(value is None for value in stats.values()), stats)
        self.assertIsNone(bonsai_stats({'prompt_tokens': 12}, {})['cached_tokens'])

    def test_adapter_hands_usage_and_timings_to_the_closing_line(self):
        def line(value):
            return b'data: ' + json.dumps(value).encode() + b'\n\n'
        raw = io.BytesIO(line({'choices': [{'delta': {'content': 'Antwort.'}, 'finish_reason': None}]})
                         + line({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
                         + line({'choices': [], 'usage': self.usage, 'timings': self.timings})
                         + b'data: [DONE]\n')
        events = [json.loads(item) for item in StreamAdapter(raw)]
        self.assertEqual(events[0]['message']['content'], 'Antwort.')
        self.assertTrue(events[-1]['done'])
        self.assertEqual(events[-1]['usage'], self.usage)
        self.assertEqual(events[-1]['timings'], self.timings)
        self.assertEqual(sum(event['done'] for event in events), 1)


class MemoryTests(unittest.TestCase):
    def test_reads_model_size_pressure_and_swap(self):
        request = Mock(return_value={'models': [{'name': 'other', 'size': 1}, {'name': 'qwen', 'size': 18647301888}]})
        sysctl = Mock(side_effect=['2\n', 'total = 22528.00M  used = 1024.50M  free = 1606.62M  (encrypted)\n'])
        self.assertEqual(memory_snapshot('ollama', 'qwen', request, sysctl),
                         {'model_bytes': 18647301888, 'pressure_level': 2, 'swap_used_bytes': int(1024.5 * 1024 * 1024)})

    def test_failures_leave_values_unknown(self):
        result = memory_snapshot('ollama', 'qwen', Mock(side_effect=OSError('down')), Mock(side_effect=FileNotFoundError()))
        self.assertEqual(result, {'model_bytes': None, 'pressure_level': None, 'swap_used_bytes': None})
        request = Mock()
        self.assertIsNone(memory_snapshot('bonsai', 'x', request, Mock(return_value='unbekannt'))['model_bytes'])
        request.assert_not_called()


class StopwatchTests(unittest.TestCase):
    def test_first_token_and_first_visible_text_are_separate(self):
        clock = Mock(side_effect=[100.0, 103.0, 109.0, 111.0, 120.0])
        watch = Stopwatch(clock)
        watch.token(visible=False)
        watch.token(visible=True)
        watch.token(visible=True)
        self.assertEqual((watch.first_token, watch.first_visible), (3.0, 9.0))
        record = performance('ollama', 'qwen', watch, ollama_stats(OLLAMA_DONE), {'model_bytes': 5}, 0.25)
        self.assertEqual((record['first_token_seconds'], record['ttft_seconds'], record['total_seconds']), (3.0, 9.0, 20.0))
        self.assertEqual(record['context_seconds'], 0.25)
        self.assertEqual(record['memory'], {'model_bytes': 5})
        self.assertNotIn('peak_memory_bytes', record)
        json.dumps(record)

    def test_without_tokens_nothing_is_claimed(self):
        watch = Stopwatch(Mock(side_effect=[1.0, 2.0]))
        record = performance('bonsai', 'm', watch, bonsai_stats(None, {'peak_memory': 2.0}))
        self.assertIsNone(record['ttft_seconds'])
        self.assertIsNone(record['first_token_seconds'])
        self.assertEqual(record['memory'], {'peak_bytes': 2_000_000_000})


class StreamPerformanceTests(unittest.TestCase):
    setUp = base.TutorTests.setUp
    write_page = base.TutorTests.write_page
    body = base.TutorTests.body

    def run_stream(self, lines, provider='ollama', model='selected-model', local=None):
        env = {'MLH_TUTOR_PROVIDER': provider, 'MLH_TUTOR_MODEL': model}
        service = TutorService(environ=env, transport=Mock(), stream_transport=Mock(return_value=FakeStream(lines)))
        service.local = local
        self.app.state.tutor = service
        response = self.client.post('/api/tutor/chat/stream', json=self.body(think=local is not None))
        self.assertEqual(response.status_code, 200, response.text)
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_done_event_carries_measured_values(self):
        final = json.dumps({'message': {'role': 'assistant', 'content': ''}, **OLLAMA_DONE}).encode() + b'\n'
        with patch('backend.tutor.local_model_info'), \
                patch('backend.tutor.memory_snapshot', return_value={'model_bytes': 7, 'pressure_level': 1, 'swap_used_bytes': 0}) as memory:
            events = self.run_stream([thought('Erst prüfen.'), chunk('Antwort. [S1]'), final], local=thinking_model())
        memory.assert_called_once_with('ollama', 'selected-model')
        record = events[-1]['performance']
        self.assertEqual((record['provider'], record['model']), ('ollama', 'selected-model'))
        self.assertEqual((record['prompt_tokens'], record['cached_tokens'], record['output_tokens']), (3441, 3436, 240))
        self.assertGreaterEqual(record['ttft_seconds'], record['first_token_seconds'])
        self.assertGreaterEqual(record['total_seconds'], record['ttft_seconds'])
        self.assertGreater(record['context_seconds'], 0)
        self.assertEqual(record['memory']['model_bytes'], 7)

    def test_provider_without_statistics_yields_unknown_values_and_still_answers(self):
        events = self.run_stream([chunk('Antwort. [S1]'), chunk('', done=True)])
        self.assertEqual(events[-1]['answer'], 'Antwort. [S1]')
        record = events[-1]['performance']
        for key in ('prompt_tokens', 'cached_tokens', 'cache_ratio', 'prefill_seconds', 'decode_tokens_per_second', 'load_seconds'):
            self.assertIsNone(record[key], key)
        self.assertIsNotNone(record['ttft_seconds'])
        self.assertEqual(record['memory'], {})

    def test_whitespace_is_not_visible_ttft(self):
        with patch('backend.tutor.Stopwatch') as watch, patch.object(TutorService, '_performance', return_value=None):
            events = self.run_stream([chunk(' \n'), thought('Überlegen'), chunk('Antwort. [S1]'), chunk('', done=True)])
        self.assertEqual([call.kwargs for call in watch.return_value.token.call_args_list],
                         [{'visible': False}, {'visible': False}, {'visible': True}])

    def test_measuring_failure_never_costs_the_answer(self):
        with patch('backend.tutor.performance', side_effect=RuntimeError('kaputt')):
            events = self.run_stream([chunk('Antwort. [S1]'), chunk('', done=True)])
        self.assertEqual(events[-1]['type'], 'done')
        self.assertIsNone(events[-1]['performance'])

    def test_bonsai_stream_asks_for_usage_and_reports_it(self):
        def line(value):
            return b'data: ' + json.dumps(value).encode() + b'\n\n'
        lines = [line({'choices': [{'delta': {'content': 'Antwort. [S1]'}, 'finish_reason': None}]}),
                 line({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}),
                 line({'choices': [], 'usage': BonsaiStatsTests.usage, 'timings': BonsaiStatsTests.timings}),
                 b'data: [DONE]\n']
        env = {'MLH_TUTOR_PROVIDER': 'bonsai', 'MLH_TUTOR_MODEL': BONSAI_MODEL}
        opener = Mock(return_value=FakeStream(lines))
        service = TutorService(environ=env, transport=Mock(), stream_transport=opener)
        self.app.state.tutor = service
        response = self.client.post('/api/tutor/chat/stream', json=self.body())
        events = [json.loads(item) for item in response.text.splitlines() if item.strip()]
        self.assertEqual(json.loads(opener.call_args.args[0].data)['stream_options'], {'include_usage': True})
        record = events[-1]['performance']
        self.assertEqual((record['provider'], record['prompt_tokens'], record['cached_tokens']), ('bonsai', 4362, 0))
        self.assertIsNone(record['load_seconds'])
        self.assertEqual(record['memory']['peak_bytes'], 9_500_000_000)

    def test_plain_chat_reports_provider_statistics_too(self):
        transport = Mock(return_value={'message': {'role': 'assistant', 'content': 'Antwort. [S1]'}, **OLLAMA_DONE})
        self.app.state.tutor = TutorService(environ={'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'selected-model'},
                                            transport=transport)
        response = self.client.post('/api/tutor/chat', json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        record = response.json()['performance']
        self.assertEqual(record['cached_tokens'], 3436)
        self.assertIsNone(record['ttft_seconds'])

    def test_cloud_provider_gets_no_local_performance_record(self):
        transport = base.TutorTests.use_provider(self)
        response = self.client.post('/api/tutor/chat', json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('performance', response.json())
        transport.assert_called_once()


if __name__ == '__main__':
    unittest.main()
