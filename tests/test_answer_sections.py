"""Structured solution text persists, but stays hidden in active exams."""
import copy
import tempfile
import unittest
from pathlib import Path

from backend.core import Hub, validate_import
from tests.test_core import sample_import


SECTIONS = [{
    'title': 'Begriffe im Überblick',
    'paragraphs': ['Die Begriffe beschreiben unterschiedliche Aspekte.'],
    'entries': [{'term': 'Diversität', 'description': 'Vielfalt von Menschen'}],
    'items': ['Unterschiede erkennen', 'Teilhabe ermöglichen'],
}]


class AnswerSectionsTests(unittest.TestCase):
    def content(self):
        content = sample_import(['free_text'])
        content['questions'][0]['model_answer_sections'] = copy.deepcopy(SECTIONS)
        return content

    def test_rejects_empty_and_malformed_structured_answers(self):
        invalid = [None, {}, [], ['Abschnitt'], [{}], [{'title': 'Nur Titel'}],
                   [{'items': 'Keine Liste'}], [{'paragraphs': ['']}],
                   [{'entries': []}], [{'entries': [{'term': ''}]}],
                   [{'entries': [{'term': 'Begriff', 'description': 4}]}],
                   [{'title': 4, 'items': ['Ein Punkt']}]]
        for sections in invalid:
            with self.subTest(sections=sections):
                content = self.content()
                content['questions'][0]['model_answer_sections'] = sections
                self.assertTrue(validate_import(content))
        self.assertEqual(validate_import(self.content()), [])

    def test_section_revision_keeps_attempts_and_answers_and_hides_active_exam_solution(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(Path(directory) / 'learning.sqlite3')
            original = sample_import(['free_text'])
            module_id = hub.import_content(original)['module_id']
            hub.attempt('test-free_text', 'Vielfalt')
            exam = hub.create_exam({'module_id': module_id, 'count': 1, 'duration_minutes': 60})
            hub.update_exam(exam['id'], {'test-free_text': 'Meine Antwort'})
            before = hub.export()
            hub.import_content(self.content(), update_existing=True)
            question = hub.question('test-free_text')
            self.assertEqual(question['model_answer_sections'], SECTIONS)
            self.assertEqual(question['model_answer'], original['questions'][0]['model_answer'])
            self.assertEqual(question['original_solution'], original['questions'][0]['original_solution'])
            after = hub.export()
            for table in ('attempts', 'progress', 'exams'):
                self.assertEqual(after[table], before[table])
            active = hub.exam(exam['id'])
            self.assertNotIn('model_answer_sections', active['questions'][0])
            self.assertEqual(active['answers'], {'test-free_text': 'Meine Antwort'})
            submitted = hub.submit_exam(exam['id'])
            self.assertEqual(submitted['results'][0]['question']['model_answer_sections'], SECTIONS)


if __name__ == '__main__':
    unittest.main()
