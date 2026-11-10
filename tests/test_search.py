"""Local search locates cited passages without touching learning or source data."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import Hub
from backend.documents import extract_document
from backend.search import MAX_SNIPPET_CHARS, register_search_routes, search_content
from tests.test_core import sample_import
from tests.test_tutor_context import concept_content, sample_content, text_pdf


class ContentSearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'study'
        self.project = self.source / 'master-learning-hub'
        (self.project / 'content').mkdir(parents=True)
        (self.source / 'material').mkdir()
        text_pdf(self.source / 'material' / 'original.pdf', [
            'Erste Originalseite zur Einordnung.',
            'Zweite Originalseite beschreibt Kapital und Herkunft.',
            'Dritte Originalseite mit einer anderen Aussage.',
            'Vierte Originalseite.', 'Fuenfte Originalseite.',
        ])
        self.hub = Hub(self.project / 'data' / 'learning.sqlite3')
        self.dd = self.hub.add_module({'name': 'Digitale Diversität', 'number': '32281'})['id']
        self.itg = self.hub.add_module({'name': 'IT Governance', 'number': '31311'})['id']
        content = sample_content('32281')
        content['module_title'] = 'Digitale Diversität'
        content['lessons'][0]['sections'][0]['paragraphs'] = [
            'Die Straße fördert Café und große Zugänglichkeit. Kapital erklärt soziale Herkunft.',
            'Ein erster Begriff ist ROTERBEGRIFF.',
        ]
        content['lessons'][0]['sections'][1]['paragraphs'] = ['Ein anderer Begriff ist GRUENERBEGRIFF.']
        self.write_content(content, 'dd.json')
        self.write_content(concept_content(), 'itg.json')

    def write_content(self, value, filename):
        (self.project / 'content' / filename).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def insert_document(self, relative='material/original.pdf', module_id=None, **changes):
        path = self.source / relative
        value = {'path': relative, 'title': path.stem, 'name': path.name,
                 'extension': path.suffix, 'kind': 'course_material', 'status': 'pending',
                 'size': path.stat().st_size if path.exists() else 123,
                 'page_texts': changes.get('page_texts', []) if 'page_texts' in changes
                 else extract_document(path) if path.exists() else [], 'unit': 7}
        value.update(changes)
        with self.hub.db() as database:
            database.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?)',
                             (relative, module_id or self.dd, json.dumps(value, ensure_ascii=False)))

    def search(self, query, **options):
        return search_content(self.hub, self.source, self.project, query, **options)

    def snapshot(self):
        with sqlite3.connect(self.hub.path) as database:
            return '\n'.join(database.iterdump())

    def test_curated_section_fields_have_precise_destinations_and_sources(self):
        for query in ('Kapital Herkunft', 'Tabelleninhalt', 'Lernnotiz', 'Aufzählungspunkt'):
            with self.subTest(query=query):
                result = self.search(query, module_id=self.dd)
                self.assertEqual(result['total'], 1)
                hit = result['results'][0]
                self.assertEqual((hit['module_id'], hit['kind'], hit['lesson_id'], hit['section_id']),
                                 (self.dd, 'lesson', 'lektion-a', 'abschnitt-a'))
                self.assertEqual(hit['sources'][0]['pdf_page'], 2)
                self.assertIn('snippet', hit)
        summary = self.search('Zusammenfassung A', module_id=self.dd)['results'][0]
        self.assertEqual(summary['lesson_id'], 'lektion-a')
        self.assertNotIn('section_id', summary)

    def test_all_words_must_share_a_passage_but_can_use_its_heading(self):
        self.assertEqual(self.search('ROTERBEGRIFF GRUENERBEGRIFF')['total'], 0)
        hit = self.search('Lektion ROTERBEGRIFF')['results'][0]
        self.assertEqual(hit['section_id'], 'abschnitt-a')
        self.assertEqual(self.search('definitivnichtenthalten')['results'], [])

    def test_german_case_accents_composed_unicode_and_partial_words(self):
        for query in ('STRASSE FÖRDERT CAFE', 'straße fördert café', 'strass forder Cafe\u0301', 'ZUGÄNGLICH'):
            with self.subTest(query=query):
                result = self.search(query)
                self.assertEqual(result['total'], 1)
                self.assertIn('Straße', result['results'][0]['snippet'])
        self.assertEqual(self.search('STRASSE STRASSE')['terms'], ['strasse'])

    def test_big_picture_search_works_for_itgov_without_any_lessons(self):
        result = self.search('RISIKEN_KURATIERT', module_id=self.itg)
        self.assertEqual(result['total'], 1)
        hit = result['results'][0]
        self.assertEqual((hit['kind'], hit['concept_id'], hit['module_title']),
                         ('concept', 'itgov-risiken', 'IT Governance'))
        self.assertNotIn('lesson_id', hit)
        self.assertEqual(hit['sources'][0]['pdf_page'], 2)
        self.assertEqual(self.search('RISIKEN_KURATIERT', module_id=self.dd)['total'], 0)
        overview = self.search('UEBERBLICK_EXKLUSIV', module_id=self.dd)['results'][0]
        self.assertEqual(overview['kind'], 'concept')
        self.assertEqual(overview['section_id'], 'overview')
        self.assertNotIn('concept_id', overview)
        for query in ('sichert den Wertbeitrag', 'IT Governance als Gesamtbild'):
            overview = self.search(query, module_id=self.itg)['results'][0]
            self.assertEqual(overview['section_id'], 'overview')
        unit = self.search('Einordnung der Themen', module_id=self.dd)['results'][0]
        self.assertEqual(unit['section_id'], 'overview')

    def test_original_pdf_is_page_aware_and_allows_official_exercise_solutions(self):
        self.insert_document(title='Offizielle Musterlösung', kind='solution')
        result = self.search('zweite originalseite', module_id=self.dd)
        self.assertEqual(result['total'], 1)
        hit = result['results'][0]
        self.assertEqual(hit['kind'], 'document')
        self.assertEqual(hit['unit'], 7)
        self.assertEqual(hit['section_title'], 'PDF-Seite 2')
        self.assertEqual(hit['source'], {'path': 'material/original.pdf', 'title': 'Offizielle Musterlösung',
                                         'kind': 'pdf', 'pdf_page': 2})
        self.assertIn('Kapital', hit['snippet'])

    def test_word_slide_and_sheet_results_do_not_invent_pdf_pages(self):
        from docx import Document
        document = Document()
        document.add_paragraph('Ein unverwechselbarer WORDSUCHBEGRIFF im Originaldokument.')
        document.save(self.source / 'material' / 'notes.docx')
        self.insert_document('material/notes.docx')
        hit = self.search('WORDSUCHBEGRIFF')['results'][0]
        self.assertEqual(hit['source']['kind'], 'document')
        self.assertIn('keine feste Seitenzählung', hit['section_title'])
        self.assertNotIn('pdf_page', hit['source'])
        for filename, label in [('slides.pptx', 'Folie 3'), ('tables.xlsx', 'Tabelle: Erlöse')]:
            path = self.source / 'material' / filename
            path.write_text('fixture', encoding='utf-8')
            self.insert_document('material/' + filename, page_texts=[{'page': 3, 'label': label, 'text': 'FORMATBEGRIFF'}])
        hits = self.search('FORMATBEGRIFF')['results']
        self.assertEqual({hit['section_title'] for hit in hits}, {'Folie 3', 'Tabelle: Erlöse'})
        self.assertTrue(all('pdf_page' not in hit['source'] for hit in hits))

    def test_bounded_deterministic_pagination_and_plain_snippets(self):
        path = self.source / 'material' / 'many.txt'
        path.write_text('Originaldatei', encoding='utf-8')
        text = ('Langer Anfang. ' * 100) + ' Straße CAFÉ <script>alert(1)</script> SUCHBEGRIFF ' + ('weiter. ' * 100)
        self.insert_document('material/many.txt', page_texts=[
            {'page': number, 'label': f'Abschnitt {number}', 'text': text} for number in range(1, 106)])
        first = self.search('strasse cafe SUCHBEGRIFF', limit=1)
        second = self.search('strasse cafe SUCHBEGRIFF', limit=1, offset=1)
        self.assertEqual(first['total'], 105)
        self.assertEqual(len(first['results']), 1)
        self.assertNotEqual(first['results'][0]['id'], second['results'][0]['id'])
        self.assertEqual(self.search('strasse cafe SUCHBEGRIFF', limit=1), first)
        snippet = first['results'][0]['snippet']
        self.assertLessEqual(len(snippet), MAX_SNIPPET_CHARS)
        self.assertIn('Straße CAFÉ', snippet)
        self.assertIn('SUCHBEGRIFF', snippet)
        self.assertIsInstance(snippet, str)
        self.assertEqual(len(self.search('SUCHBEGRIFF', limit=100)['results']), 100)
        self.assertEqual(self.search('SUCHBEGRIFF', offset=1000)['results'], [])

    def test_private_import_missing_error_stale_and_external_sources_are_excluded(self):
        for filename, fields in [
            ('admin.txt', {'kind': 'administrative'}), ('missing.txt', {'status': 'missing'}),
            ('broken.txt', {'status': 'error'}), ('import.txt', {'kind': 'gpt_import'}),
            ('stale.txt', {'size': 999999}),
        ]:
            path = self.source / 'material' / filename
            path.write_text('NICHTANZEIGEN', encoding='utf-8')
            self.insert_document('material/' + filename, **fields)
        internal = self.project / 'runtime.txt'
        internal.write_text('NICHTANZEIGEN', encoding='utf-8')
        self.insert_document('master-learning-hub/runtime.txt')
        external = self.root / 'outside.txt'
        external.write_text('NICHTANZEIGEN', encoding='utf-8')
        (self.source / 'material' / 'external.txt').symlink_to(external)
        self.insert_document('material/external.txt')
        self.insert_document('material/deleted.txt', page_texts=[{'page': 1, 'text': 'NICHTANZEIGEN'}])
        with self.hub.db() as database:
            for relative in ('@imports/questions.json', '../outside.txt'):
                database.execute('INSERT INTO documents(path,module_id,payload) VALUES(?,?,?)',
                                 (relative, self.dd, json.dumps({'text': 'NICHTANZEIGEN'})))
        self.assertEqual(self.search('NICHTANZEIGEN')['total'], 0)

    def test_search_never_reads_hidden_runtime_answers_or_changes_database_or_sources(self):
        content = sample_import(['free_text'])
        content['questions'][0]['model_answer'] = 'GEHEIMERLAUFZEITBEGRIFF'
        self.hub.import_content(content)
        self.insert_document(proposals=[{'question': 'GEHEIMERLAUFZEITBEGRIFF'}],
                             import_content={'question': 'GEHEIMERLAUFZEITBEGRIFF'})
        before = self.snapshot()
        source_before = (self.source / 'material' / 'original.pdf').read_bytes()
        with patch('socket.create_connection', side_effect=AssertionError('Search must stay local')):
            self.assertEqual(self.search('GEHEIMERLAUFZEITBEGRIFF')['total'], 0)
            self.assertTrue(self.search('Kapital')['results'])
            self.assertEqual(self.search('   !!!   ')['total'], 0)
            with self.assertRaises(ValueError):
                self.search('x' * 201)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.source / 'material' / 'original.pdf').read_bytes(), source_before)

    def test_invalid_package_does_not_hide_other_valid_sources(self):
        self.insert_document()
        (self.project / 'content' / 'dd.json').write_text('{broken', encoding='utf-8')
        result = self.search('zweite originalseite')
        self.assertEqual(result['total'], 1)
        self.assertIn('ungültige Lernpakete', result['notice'])

    def test_pdf_line_breaks_and_soft_hyphen_match_a_whole_word(self):
        self.insert_document(page_texts=[{'page': 2, 'text': 'Daten-\nmanagement und Informa\u00adtion.'}])
        hit = self.search('datenmanagement information')['results'][0]
        self.assertEqual(hit['source']['pdf_page'], 2)
        self.assertIn('Datenmanagement', hit['snippet'])

    def test_route_has_bounded_inputs_clear_errors_and_empty_initial_state(self):
        app = FastAPI()
        register_search_routes(app, self.hub, self.source, self.project)
        client = TestClient(app)
        self.assertEqual(client.get('/api/search').json()['results'], [])
        response = client.get('/api/search', params={'q': 'Kapital', 'module_id': self.dd, 'limit': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        for parameters in ({'q': 'x' * 201}, {'limit': 101}, {'offset': -1}):
            self.assertEqual(client.get('/api/search', params=parameters).status_code, 422)
        self.assertEqual(client.get('/api/search', params={'q': 'test\x00'}).status_code, 400)
        self.assertEqual(client.get('/api/search', params={'module_id': 'M-unknown'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
