"""Readiness, offline fallback, bounded prompts and launcher ownership."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi import HTTPException
from backend.local_model import LocalModel, local_model_info
from backend.tutor import TutorService, MAX_OUTPUT_TOKENS
import launcher

class LocalStartTests(unittest.TestCase):
    def request(self, path, body=None, timeout=3):
        if path == '/api/tags': return {'models': [{'name': 'llama3.1:8b'}]}
        if path == '/api/show': return {'capabilities': ['completion']}
        if path == '/api/chat': return {'done': True}
        return {'version': 'test'}

    def test_ready_after_successful_load(self):
        request = Mock(side_effect=self.request)
        model = LocalModel('llama3.1:8b', request)
        model._stop.set()  # run exactly the loading pass, no monitor loop
        model._run()
        self.assertEqual(model.snapshot()['readiness'], 'ready')
        call = next(c for c in request.call_args_list if c.args[0] == '/api/chat')
        self.assertEqual(call.args[1]['messages'], [])
        self.assertEqual(call.args[1]['keep_alive'], '15m')

    def test_missing_model_never_loads_or_downloads(self):
        request = Mock(return_value={'models': []})
        model = LocalModel('missing', request)
        model._run()
        self.assertEqual(model.snapshot()['readiness'], 'error')
        self.assertIn('nicht lokal', model.snapshot()['message'])
        self.assertEqual(request.call_count, 1)

    def test_cloud_reference_is_rejected(self):
        request = Mock(side_effect=[{'models': [{'name': 'remote'}]}, {'remote_model': 'cloud', 'capabilities': ['completion']}])
        with self.assertRaisesRegex(ValueError, 'ausschließlich lokale'):
            local_model_info('remote', request)

    def test_unavailable_service_is_readable(self):
        model = LocalModel('llama3.1:8b', Mock(side_effect=OSError('private diagnostic')))
        model._run()
        self.assertEqual(model.snapshot()['readiness'], 'error')
        self.assertNotIn('private', model.snapshot()['message'])

    def test_long_local_request_is_bounded_and_disclosed(self):
        transport = Mock(return_value={'message': {'role': 'assistant', 'content': 'Eine Erklärung.'}})
        service = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'llama3.1:8b'}, transport)
        result = service.chat({'context_text': 'ä' * 24000, 'sources': []}, 'Bitte erklären.', [{'role': 'user', 'content': 'x'*4000}, {'role': 'assistant', 'content': 'y'*16000}])
        payload = json.loads(transport.call_args.args[0].data)
        size = sum(len(m['content'].encode()) for m in payload['messages'])
        self.assertLessEqual(size + MAX_OUTPUT_TOKENS + 1024, 32768)
        self.assertIn('gekürzt', result['notice'])

    def test_concurrent_request_does_not_call_model(self):
        transport = Mock()
        service = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, transport)
        service._generation.acquire()
        with self.assertRaises(HTTPException) as error:
            service.chat({'context_text': 'Text', 'sources': []}, 'Frage', [])
        self.assertEqual(error.exception.status_code, 429)
        transport.assert_not_called()
        service._generation.release()

    def test_existing_ollama_is_not_owned(self):
        with patch('launcher.local_json', return_value={'version': 'test'}), patch('launcher.subprocess.Popen') as spawn:
            self.assertIsNone(launcher.ensure_ollama(io.StringIO()))
            spawn.assert_not_called()

    def test_foreign_or_old_server_is_not_reused(self):
        self.assertFalse(launcher.is_our_hub({'status': 'ok', 'question_count': 411}))
        self.assertFalse(launcher.is_our_hub({'application': 'master-learning-hub', 'project_id': 'other', 'launcher_version': 1}))
        self.assertTrue(launcher.is_our_hub({'application': 'master-learning-hub', 'project_id': launcher.project_id(), 'launcher_version': 1}))

    def test_local_config_cannot_select_cloud_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'tutor.local.json').write_text('{"enabled": true, "model": "llama3.1:8b"}')
            with patch('launcher.PROJECT', Path(tmp)), patch.dict(os.environ, {'MLH_TUTOR_PROVIDER': 'openai'}):
                launcher.configure()
                self.assertEqual(os.environ['MLH_TUTOR_PROVIDER'], 'ollama')

if __name__ == '__main__': unittest.main()
