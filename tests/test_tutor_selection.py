"""Regression coverage for module questions and page continuations."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tutor_context import build_tutor_context, _conversation_lesson, _pdf_excerpts
from tests.test_tutor_context import text_pdf, sample_content
from tests import test_tutor
from backend.tutor import TutorService


class SelectionTests(unittest.TestCase):
    def test_question_followup_topic_change_and_assistant_is_not_evidence(self):
        package = {'lessons': [
            {'id': 'diversity', 'title': 'Vier-Ebenen-Modell nach Gardenswartz und Rowe'},
            {'id': 'data', 'title': 'Metadaten'}]}
        question = 'Welche Ebenen hat das Vier-Ebenen-Modell nach Gardenswartz und Rowe?'
        self.assertEqual(_conversation_lesson(package, question, []), 'diversity')
        history = [{'role': 'user', 'content': question}]
        self.assertEqual(_conversation_lesson(package, 'doch es ist Abbildung 7', history), 'diversity')
        self.assertEqual(_conversation_lesson(package, 'Erkläre Metadaten', history), 'data')
        self.assertIsNone(_conversation_lesson(package, 'Danke', [{'role': 'assistant', 'content': question}]))
        self.assertIsNone(_conversation_lesson(package, 'Welches Wetter ist morgen?', history))

    def test_ambiguous_titles_do_not_pick_arbitrarily(self):
        package = {'lessons': [{'id': 'a', 'title': 'Modell der Diversität'},
                               {'id': 'b', 'title': 'Modell der Diversität'}]}
        self.assertIsNone(_conversation_lesson(package, 'Erkläre das Modell der Diversität', []))

    def test_requested_continuation_is_read_with_correct_source_and_offsets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'original.pdf'
            text_pdf(path, ['Abbildungsverzeichnis Abbildung 7: Layers 6',
                            'Die erste Ebene beschreibt',
                            'anderer Text', 'anderer Text', 'anderer Text',
                            'Vollstaendige Fortsetzung. Abbildung 7: Layers of Diversity'])
            refs = [{'id': 'S1', 'kind': 'pdf', 'path': 'original.pdf', 'title': 'Original',
                     'pdf_page': 1, 'pdf_page_end': 6}]
            for request in ('Abbildung 7', 'Abbildung 7 auf PDF-Seite 6'):
                result = _pdf_excerpts(refs, root / 'project', root, 6000,
                                       request_text=request)
                text, _, _, _, _, spans = result
                self.assertEqual(spans['S1'][0]['pdf_page'], 6)
                first = spans['S1'][0]
                self.assertIn('Vollstaendige Fortsetzung', text[first['start']:first['end']])
                self.assertLessEqual(len(spans['S1']), 5)
            missing = _pdf_excerpts(refs, root / 'project', root, 6000,
                                    request_text='PDF-Seite 999')
            self.assertNotIn('PDF-Seite 999', missing[0])

    def test_automatic_selection_limits_curated_text_to_matching_section(self):
        package = sample_content()
        package['lessons'][0]['title'] = 'Vier-Ebenen-Modell nach Gardenswartz und Rowe'
        with patch('backend.tutor_context._selected_package', return_value=package):
            context = build_tutor_context(None, Path('/tmp'), Path('/tmp'), 'module',
                                          message='Welche Ebenen hat das Vier-Ebenen-Modell nach Gardenswartz und Rowe?',
                                          max_chars=9000)
        self.assertEqual(context['lesson_id'], 'lektion-a')
        self.assertEqual(context['section_id'], 'abschnitt-a')
        self.assertIn('ABSCHNITT_A_EXKLUSIV', context['context_text'])
        self.assertNotIn('ABSCHNITT_B_EXKLUSIV', context['context_text'])

    def test_selected_scope_is_preserved(self):
        package = sample_content()
        package['lessons'][1]['title'] = 'Metadaten'
        with patch('backend.tutor_context._selected_package', return_value=package):
            c = build_tutor_context(None, Path('/tmp'), Path('/tmp'), 'module',
                                    lesson_id='lektion-a', message='Erkläre Metadaten')
        self.assertEqual(c['lesson_id'], 'lektion-a')


class RouteSelectionTest(unittest.TestCase):
    def test_normal_chat_automatically_selects_lesson(self):
        fixture = test_tutor.TutorTests()
        fixture.setUp()
        try:
            transport = fixture.use_provider()
            response = fixture.client.post('/api/tutor/chat', json=fixture.body(lesson_id=None))
            self.assertEqual(response.status_code, 200, response.text)
            payload = json.loads(transport.call_args[0][0].data)
            self.assertIn('Kuratierte Lernpage:', payload['input'][0]['content'])
            self.assertIn('Metadaten', payload['input'][0]['content'])
        finally:
            fixture.doCleanups()

class AnswerEvidenceTests(unittest.TestCase):
    def test_response_contains_its_own_excerpts_with_utf16_offsets(self):
        service = TutorService()
        context = {'context_text': '😀 Neue Quelle', 'sources': [],
                   'excerpts': {'S1': [{'pdf_page': 21, 'start': 3, 'end': 14}]},
                   'figures': [{'caption': 'Abbildung 7'}]}
        response = service._finish(context, 'Antwort', False)
        self.assertEqual(response['excerpts']['S1'][0], {'pdf_page': 21, 'text': 'Neue Quelle'})
        self.assertEqual(response['figures'], context['figures'])
