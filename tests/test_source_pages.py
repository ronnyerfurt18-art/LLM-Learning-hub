"""Cited PDF pages are served alone, so every browser opens exactly there."""
import io
import unittest

from pypdf import PdfReader

from tests import test_tutor as base  # module import: pytest must not collect TutorTests twice


class SourcePagesTests(unittest.TestCase):
    setUp = base.TutorTests.setUp
    write_page = base.TutorTests.write_page

    def test_pdf_opens_at_the_cited_page_inline(self):
        response = self.client.get('/api/source/pages', params={'path': 'material/lehrbrief.pdf', 'start': 1})
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertTrue(response.headers['content-disposition'].startswith('inline;'))
        self.assertEqual(len(PdfReader(io.BytesIO(response.content)).pages), 1)

    def test_invalid_ranges_and_paths_are_rejected(self):
        for params, status in (({'start': 2}, 404), ({'start': 0}, 400),
                               ({'start': 1, 'end': 41}, 400), ({'start': 3, 'end': 2}, 400)):
            with self.subTest(params=params):
                response = self.client.get('/api/source/pages', params={'path': 'material/lehrbrief.pdf', **params})
                self.assertEqual(response.status_code, status, response.text[:200])
        self.assertEqual(self.client.get('/api/source/pages', params={'path': '../lehrbrief.pdf', 'start': 1}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
