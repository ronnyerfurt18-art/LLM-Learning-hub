"""Learning pages, original-source confinement and the explicitly approved BI seed."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.learning_pages import module_id_for_package, validate_learning_page
from backend.main import create_app
from tests.test_core import sample_import
from tests.seedlist import write_seed_list


def sample_page(relative='material/lehrbrief.pdf'):
    ref = {'path': relative, 'title': 'BI Lehrbrief', 'chapter': '2.2 Metadatenmanagement',
           'pdf_page': 1, 'pdf_page_end': 1, 'printed_page': '1'}
    return {
        'schema_version': 1, 'module_number': '32711', 'module_title': 'Business Intelligence',
        'overview': {'title': 'Vom Geschäftsproblem zur Entscheidung',
                     'paragraphs': ['Die Kurseinheiten verbinden Daten mit Entscheidungen.'],
                     'sources': [copy.deepcopy(ref)],
                     'units': [{'unit': 3, 'title': 'Data Warehouse',
                                'description': 'Daten und Metadaten organisieren.',
                                'topics': ['Metadatenmanagement']}],
                     'learning_path': ['Begriff verstehen.', 'Beispiel prüfen.', 'Selbst üben.']},
        'lessons': [{'id': 'bi-metadaten', 'unit': 3, 'title': 'Metadatenmanagement',
                     'summary': 'Metadaten beschreiben Daten und ihre Verarbeitung.',
                     'learning_goals': ['Fachliche und technische Metadaten unterscheiden.'],
                     'sections': [{'id': 'begriff', 'title': 'Warum Metadaten?',
                                   'paragraphs': ['Eine Kennzahl braucht eine fachliche Bedeutung.'],
                                   'bullets': ['Fachlich: Definition der Kennzahl.', 'Technisch: Datentyp.'],
                                   'table': {'headers': ['Art', 'Beispiel'],
                                             'rows': [['Fachlich', 'Umsatzdefinition'], ['Technisch', 'Datentyp']]},
                                   'note': 'Die Definition und die Verarbeitung gemeinsam prüfen.',
                                   'sources': [copy.deepcopy(ref)]}],
                     'exercise_ids': ['BI-META-01']}],
    }


def sample_big_picture_page(overview_only=False):
    """Use the same real, confined PDF fixture for every concept reference."""
    content = sample_page()
    reference = content['overview']['sources'][0]
    content['overview']['big_picture'] = {
        'title': 'Vom Bedarf zum begründeten Handeln',
        'central_question': 'Wie unterstützen Daten eine Entscheidung?',
        'intro': 'Bedarf, verständliche Daten und Auswertung gehören zusammen.',
        'takeaway': 'Die Bedeutung der Daten verbindet Bedarf und Auswertung.',
        'nodes': [
            {'id': 'bedarf', 'title': 'Informationsbedarf',
             'summary': 'Das Entscheidungsproblem bestimmt den Bedarf.',
             'role': 'Gibt die Richtung vor.', 'sources': [copy.deepcopy(reference)]},
            {'id': 'daten', 'title': 'Verständliche Daten',
             'summary': 'Metadaten erklären die Bedeutung der Daten.',
             'role': 'Verbindet den Bedarf mit der Auswertung.',
             'sources': [copy.deepcopy(reference)]},
            {'id': 'auswertung', 'title': 'Auswertung',
             'summary': 'Die Auswertung unterstützt die Entscheidung.',
             'role': 'Führt zurück zum Entscheidungsproblem.',
             'sources': [copy.deepcopy(reference)]},
        ],
        'connections': [
            {'from': 'bedarf', 'to': 'daten', 'label': 'bestimmt die benötigte Bedeutung'},
            {'from': 'daten', 'to': 'auswertung', 'label': 'ermöglicht Interpretation'},
        ],
    }
    if overview_only:
        content['overview']['units'] = []
        content['lessons'] = []
        for node in content['overview']['big_picture']['nodes']:
            node['scope_note'] = 'Nachlesestelle im Original; Lernkapitel folgen später.'
    else:
        content['overview']['big_picture']['nodes'][1]['lesson_ids'] = ['bi-metadaten']
    return content


class LearningPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'study'
        self.project = self.source / 'master-learning-hub'
        write_seed_list(self.project)
        (self.project / 'content').mkdir()
        (self.source / 'material').mkdir()
        self.pdf = self.source / 'material' / 'lehrbrief.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with self.pdf.open('wb') as stream:
            writer.write(stream)
        self.app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        self.client = TestClient(self.app, base_url='http://127.0.0.1', raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        # Assigning a module number after creation preserves the original, custom ID.
        module = self.app.state.hub.add_module({'name': 'Business Intelligence', 'unit_count': 4})
        self.mid = module['id']
        self.app.state.hub.patch_module(self.mid, {'number': '32711'})

    def write_page(self, content=None, name='bi-learning-pages.json'):
        content = content if content is not None else sample_page()
        (self.project / 'content' / name).write_text(json.dumps(content, ensure_ascii=False), encoding='utf-8')
        return content

    def database_state(self):
        state = self.client.get('/api/export').json()
        state.pop('exported_at')
        return state

    def test_complete_page_has_real_module_id_concrete_references_and_no_database_writes(self):
        content = self.write_page()
        self.app.state.hub.import_content(sample_import(['single_choice']))
        self.app.state.hub.attempt('test-single_choice', [0])
        before = self.database_state()
        summary = self.client.get('/api/learning-pages')
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json(), [{'module_id': self.mid, 'module_number': '32711',
                                          'module_title': 'Business Intelligence', 'lesson_count': 1}])
        detail = self.client.get(f'/api/learning-pages/{self.mid}')
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json(), {**content, 'module_id': self.mid, 'unit_label': 'Einheit', 'has_assignments': False})
        self.assertEqual(self.database_state(), before)
        # Files are reread, so an edited page becomes available without a rescan or mutation.
        content['lessons'][0]['summary'] = 'Aktualisierte Erläuterung.'
        self.write_page(content)
        self.assertEqual(self.client.get(f'/api/learning-pages/{self.mid}').json()['lessons'][0]['summary'], 'Aktualisierte Erläuterung.')
        self.assertEqual(self.database_state(), before)

    def test_missing_pages_and_unknown_modules_are_404(self):
        self.assertEqual(self.client.get('/api/learning-pages').json(), [])
        self.assertEqual(self.client.get(f'/api/learning-pages/{self.mid}').status_code, 404)
        self.assertEqual(self.client.get('/api/learning-pages/unknown-module').status_code, 404)

    def test_big_picture_overview_only_package_is_read_only_and_available_without_lessons(self):
        content = self.write_page(sample_big_picture_page(overview_only=True))
        self.app.state.hub.import_content(sample_import(['single_choice']))
        self.app.state.hub.attempt('test-single_choice', [0])
        before = self.database_state()
        self.assertEqual(validate_learning_page(content, self.source, self.project), [])

        summary = self.client.get('/api/learning-pages')
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json(), [{'module_id': self.mid, 'module_number': '32711',
                                          'module_title': 'Business Intelligence',
                                          'lesson_count': 0, 'has_big_picture': True}])
        detail = self.client.get(f'/api/learning-pages/{self.mid}')
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json(), {**content, 'module_id': self.mid, 'unit_label': 'Einheit', 'has_assignments': False})
        self.assertEqual(detail.json()['overview']['units'], [])
        self.assertEqual(detail.json()['lessons'], [])
        self.assertEqual(self.database_state(), before)

        # Editing a concept is reread without importing questions or touching progress.
        content['overview']['big_picture']['nodes'][0]['summary'] = 'Aktualisierter Informationsbedarf.'
        self.write_page(content)
        reread = self.client.get(f'/api/learning-pages/{self.mid}')
        self.assertEqual(reread.status_code, 200, reread.text)
        self.assertEqual(reread.json()['overview']['big_picture'], content['overview']['big_picture'])
        self.assertEqual(self.database_state(), before)

    def test_big_picture_can_link_an_existing_lesson_and_keep_its_sources(self):
        content = self.write_page(sample_big_picture_page())
        self.assertEqual(validate_learning_page(content, self.source, self.project), [])
        summary = self.client.get('/api/learning-pages')
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()[0]['lesson_count'], 1)
        self.assertTrue(summary.json()[0]['has_big_picture'])
        response = self.client.get(f'/api/learning-pages/{self.mid}')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['overview']['big_picture']['nodes'][1]['lesson_ids'], ['bi-metadaten'])
        self.assertEqual(response.json()['lessons'], content['lessons'])

    def test_big_picture_rejects_missing_or_unconfined_concept_sources(self):
        invalid_sources = [
            [], None, [None],
            [{'path': 'material/missing.pdf', 'title': 'Fehlt', 'pdf_page': 1}],
            [{'path': '../outside.pdf', 'title': 'Außerhalb', 'pdf_page': 1}],
            [{'path': 'master-learning-hub/private.md', 'title': 'Intern', 'pdf_page': 1}],
            [{'path': 'material/lehrbrief.pdf', 'title': 'Quelle', 'pdf_page': 0}],
        ]
        before = self.database_state()
        for references in invalid_sources:
            with self.subTest(sources=references):
                content = sample_big_picture_page(overview_only=True)
                content['overview']['big_picture']['nodes'][0]['sources'] = references
                errors = validate_learning_page(content, self.source, self.project)
                self.assertTrue(any('big_picture.nodes[0].sources' in error for error in errors), errors)
                self.write_page(content)
                for endpoint in ('/api/learning-pages', f'/api/learning-pages/{self.mid}'):
                    response = self.client.get(endpoint)
                    self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.database_state(), before)

    def test_big_picture_rejects_broken_connections_and_missing_lesson_targets(self):
        connections = [
            [], None, [None],
            [{'from': 'bedarf', 'to': 'unknown', 'label': 'Fehlendes Ziel'}],
            [{'from': 'unknown', 'to': 'daten', 'label': 'Fehlender Ursprung'}],
            [{'from': 'daten', 'to': 'daten', 'label': 'Selbstverweis'}],
            [{'from': 'bedarf', 'to': 'daten', 'label': ''}],
        ]
        for value in connections:
            with self.subTest(connections=value):
                content = sample_big_picture_page()
                content['overview']['big_picture']['connections'] = value
                errors = validate_learning_page(content, self.source, self.project)
                self.assertTrue(any('big_picture.connections' in error for error in errors), errors)
                self.write_page(content)
                response = self.client.get(f'/api/learning-pages/{self.mid}')
                self.assertEqual(response.status_code, 422, response.text)

        for value in (['missing-lesson'], 'bi-metadaten', [None], None, [True]):
            with self.subTest(lesson_ids=value):
                content = sample_big_picture_page()
                content['overview']['big_picture']['nodes'][1]['lesson_ids'] = value
                errors = validate_learning_page(content, self.source, self.project)
                self.assertTrue(any('lesson_ids' in error for error in errors), errors)
                self.write_page(content)
                response = self.client.get(f'/api/learning-pages/{self.mid}')
                self.assertEqual(response.status_code, 422, response.text)

        content = sample_big_picture_page(overview_only=True)
        content['overview']['big_picture']['nodes'][1]['lesson_ids'] = ['bi-metadaten']
        self.assertTrue(any('Lernseite nicht vorhanden' in error
                            for error in validate_learning_page(content, self.source, self.project)))

    def test_big_picture_rejects_duplicate_concepts_and_invalid_concept_counts(self):
        content = sample_big_picture_page()
        content['overview']['big_picture']['nodes'][1]['id'] = 'bedarf'
        errors = validate_learning_page(content, self.source, self.project)
        self.assertTrue(any('doppelte Konzept-ID' in error for error in errors), errors)
        self.write_page(content)
        response = self.client.get('/api/learning-pages')
        self.assertEqual(response.status_code, 422, response.text)

        for count in (0, 2, 8):
            with self.subTest(concept_count=count):
                content = sample_big_picture_page()
                prototype = content['overview']['big_picture']['nodes'][0]
                content['overview']['big_picture']['nodes'] = [
                    {**copy.deepcopy(prototype), 'id': f'concept-{i}'} for i in range(count)
                ]
                self.assertTrue(any('drei bis sieben' in error
                                    for error in validate_learning_page(content, self.source, self.project)))

    def test_empty_legacy_package_remains_invalid_without_a_valid_big_picture(self):
        for picture in ('absent', None, {}, []):
            with self.subTest(big_picture=picture):
                content = sample_page()
                content['lessons'] = []
                content['overview']['units'] = []
                if picture != 'absent':
                    content['overview']['big_picture'] = picture
                self.assertTrue(validate_learning_page(content, self.source, self.project))
                self.write_page(content)
                for endpoint in ('/api/learning-pages', f'/api/learning-pages/{self.mid}'):
                    response = self.client.get(endpoint)
                    self.assertEqual(response.status_code, 422, response.text)

    def test_malformed_json_and_invalid_sections_report_errors_without_breaking_other_routes(self):
        file = self.project / 'content' / 'bi-learning-pages.json'
        file.write_text('{bad JSON', encoding='utf-8')
        for endpoint in ('/api/learning-pages', f'/api/learning-pages/{self.mid}'):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn(file.name, response.json()['detail'])
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        page = sample_page()
        page['lessons'][0]['sections'][0]['sources'] = []
        self.write_page(page)
        response = self.client.get(f'/api/learning-pages/{self.mid}')
        self.assertEqual(response.status_code, 422)
        self.assertIn('Quellnachweis', response.json()['detail'])
        for number in (True, ['32711'], {'number': '32711'}):
            with self.subTest(module_number=number):
                page = sample_page()
                page['module_number'] = number
                self.write_page(page)
                self.assertEqual(self.client.get('/api/learning-pages').status_code, 422)
                self.assertEqual(self.client.get(f'/api/learning-pages/{self.mid}').status_code, 422)

    def test_unrelated_bad_package_does_not_hide_a_valid_module_page(self):
        self.write_page()
        (self.project / 'content' / 'broken.json').write_text('[', encoding='utf-8')
        self.assertEqual(self.client.get('/api/learning-pages').status_code, 422)
        self.assertEqual(self.client.get(f'/api/learning-pages/{self.mid}').status_code, 200)

    def test_reference_page_ranges_shapes_and_confined_paths_are_validated(self):
        changes = [
            ('pdf_page', 0), ('pdf_page', True), ('pdf_page', '1'),
            ('pdf_page_end', 0), ('pdf_page_end', '2'),
            ('path', '../outside.pdf'), ('path', 'master-learning-hub/internal.md'),
            ('path', 'material/missing.pdf'), ('title', ''),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                content = sample_page()
                content['lessons'][0]['sections'][0]['sources'][0][field] = value
                self.assertTrue(validate_learning_page(content, self.source, self.project))
        content = sample_page()
        content['overview']['sources'][0].update(pdf_page=3, pdf_page_end=2)
        self.assertTrue(any('Endseite' in error for error in validate_learning_page(content, self.source, self.project)))
        for malformed in ([], {'schema_version': 1}, sample_page() | {'lessons': [None]}):
            self.assertTrue(validate_learning_page(malformed, self.source, self.project))

    def test_missing_local_images_and_duplicate_modules_are_reported(self):
        page = sample_page()
        page['lessons'][0]['sections'][0]['image'] = {'path': 'assets/bi/missing.png', 'caption': 'Metadaten', 'source_page': 1}
        self.write_page(page)
        self.assertEqual(self.client.get('/api/learning-pages').status_code, 422)
        self.write_page()
        self.write_page(name='bi-duplicate.json')
        response = self.client.get('/api/learning-pages')
        self.assertEqual(response.status_code, 422)
        self.assertIn('dieselbe Modulnummer', response.json()['detail'])
        self.assertEqual(self.client.get(f'/api/learning-pages/{self.mid}').status_code, 422)

    def test_module_id_fallback_cannot_bind_a_different_module(self):
        package = sample_page()
        self.assertEqual(module_id_for_package(package, [{'id': 'custom-bi-id', 'number': '32711'}]), 'custom-bi-id')
        self.assertEqual(module_id_for_package(package, [{'id': 'M-32711', 'number': ''}]), 'M-32711')
        self.assertIsNone(module_id_for_package(package, [{'id': 'M-32711', 'number': '88888'}]))
        self.assertIsNone(module_id_for_package(package, []))

    def test_study_sources_open_inline_with_correct_mime_and_original_bytes(self):
        response = self.client.get('/api/source', params={'path': 'material/lehrbrief.pdf'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertTrue(response.headers['content-disposition'].startswith('inline;'))
        self.assertEqual(response.content, self.pdf.read_bytes())
        notes = self.source / 'material' / 'nachlesen.md'
        notes.write_text('# Metadaten\nErläuterung.', encoding='utf-8')
        response = self.client.get('/api/source', params={'path': notes.relative_to(self.source).as_posix()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['content-type'].startswith('text/markdown'))
        self.assertEqual(response.text, notes.read_text(encoding='utf-8'))
        for filename, payload, mime in [
            ('termin.png', b'\x89PNG\r\n\x1a\nsource fixture', 'image/png'),
            ('termine.ics', b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n', 'text/calendar'),
        ]:
            with self.subTest(filename=filename):
                source = self.source / 'material' / filename
                source.write_bytes(payload)
                original = self.client.get('/api/source', params={'path': source.relative_to(self.source).as_posix()})
                self.assertEqual(original.status_code, 200)
                self.assertTrue(original.headers['content-type'].startswith(mime))
                self.assertEqual(original.content, payload)
        # The original indexed-document endpoint remains available.
        doc = next(doc for doc in self.app.state.hub.documents() if doc['path'] == 'material/lehrbrief.pdf')
        indexed = self.client.get(f"/api/documents/{doc['id']}/source")
        self.assertEqual(indexed.status_code, 200)
        self.assertEqual(indexed.content, self.pdf.read_bytes())

    def test_video_references_coexist_with_pdf_references_and_do_not_write_to_database(self):
        video = self.source / 'material' / 'lektion #3.mp4'
        video.write_bytes(b'fake mp4 fixture for source references')
        reference = {'kind': 'video', 'path': video.relative_to(self.source).as_posix(),
                     'title': 'Vorlesung Einheit 3', 'chapter': 'Erklärung des Beispiels',
                     'timestamp_seconds': 12.5, 'timestamp_end_seconds': 44.25}
        content = sample_page()
        content['lessons'][0]['sections'][0]['sources'].append(reference)
        self.write_page(content)
        before = self.database_state()
        response = self.client.get(f'/api/learning-pages/{self.mid}')
        self.assertEqual(response.status_code, 200, response.text)
        refs = response.json()['lessons'][0]['sections'][0]['sources']
        self.assertEqual(refs[0], sample_page()['lessons'][0]['sections'][0]['sources'][0])
        self.assertEqual(refs[1], reference)
        self.assertEqual(self.client.get('/api/learning-pages').status_code, 200)
        self.assertEqual(self.database_state(), before)
        for start, end in ((0, None), (0, 0), (1, 2), (1.25, 2.5)):
            with self.subTest(start=start, end=end):
                ref = {**reference, 'timestamp_seconds': start}
                if end is None:
                    ref.pop('timestamp_end_seconds')
                else:
                    ref['timestamp_end_seconds'] = end
                content['lessons'][0]['sections'][0]['sources'][1] = ref
                self.assertEqual(validate_learning_page(content, self.source, self.project), [])

    def test_video_references_reject_invalid_time_marks_and_contradictory_source_types(self):
        (self.source / 'material' / 'video.mp4').write_bytes(b'fake video')
        reference = {'kind': 'video', 'path': 'material/video.mp4',
                     'title': 'Vorlesung', 'timestamp_seconds': 4, 'timestamp_end_seconds': 5}
        changes = [('timestamp_seconds', value) for value in (-1, True, False, '1', None, [], float('nan'), float('inf'), -float('inf'))]
        changes += [('timestamp_end_seconds', value) for value in (-1, 3, True, '5', None, float('nan'), float('inf'))]
        changes += [('path', 'material/lehrbrief.pdf'), ('kind', 'audio'), ('kind', None),
                    ('pdf_page', 1), ('pdf_page_end', 2), ('printed_page', '1')]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                content = sample_page()
                ref = {**reference, field: value}
                content['lessons'][0]['sections'][0]['sources'] = [ref]
                self.assertTrue(validate_learning_page(content, self.source, self.project))
        for ref in ({key: value for key, value in reference.items() if key != 'timestamp_seconds'},
                    {key: value for key, value in reference.items() if key != 'kind'},
                    {**reference, 'kind': 'pdf', 'pdf_page': 1},
                    {'path': 'material/video.mp4', 'title': 'Video ohne Typangabe', 'pdf_page': 1}):
            content = sample_page()
            content['lessons'][0]['sections'][0]['sources'] = [ref]
            self.write_page(content)
            response = self.client.get(f'/api/learning-pages/{self.mid}')
            self.assertEqual(response.status_code, 422, response.text)
        content = sample_page()
        content['overview']['sources'][0]['kind'] = 'pdf'
        self.assertEqual(validate_learning_page(content, self.source, self.project), [])
        content['overview']['sources'][0]['timestamp_seconds'] = 0
        self.assertTrue(validate_learning_page(content, self.source, self.project))

    def test_mp4_sources_open_inline_and_byte_range_requests_support_seeking(self):
        video = self.source / 'material' / 'lektion #3.mp4'
        payload = bytes(range(64))
        video.write_bytes(payload)
        relative = video.relative_to(self.source).as_posix()
        response = self.client.get('/api/source', params={'path': relative})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'video/mp4')
        self.assertTrue(response.headers['content-disposition'].startswith('inline;'))
        self.assertEqual(response.headers['accept-ranges'], 'bytes')
        self.assertEqual(response.content, payload)
        partial = self.client.get('/api/source', params={'path': relative}, headers={'range': 'bytes=8-15'})
        self.assertEqual(partial.status_code, 206, partial.text)
        self.assertEqual(partial.headers['content-type'], 'video/mp4')
        self.assertEqual(partial.headers['content-range'], 'bytes 8-15/64')
        self.assertEqual(partial.headers['content-length'], '8')
        self.assertEqual(partial.content, payload[8:16])
        bad_range = self.client.get('/api/source', params={'path': relative}, headers={'range': 'bytes=64-80'})
        self.assertEqual(bad_range.status_code, 416)
        outside = self.root / 'outside.mp4'
        outside.write_bytes(b'outside movie')
        (self.source / 'material' / 'outside.mp4').symlink_to(outside)
        for path in ('../outside.mp4', 'material/outside.mp4', 'master-learning-hub/private.mp4', 'material/video.mov'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/api/source', params={'path': path}).status_code, 403)

    def test_source_paths_reject_project_data_directories_traversal_and_symlinks(self):
        outside = self.root / 'outside.pdf'
        outside.write_bytes(b'private original')
        internal = self.project / 'internal.md'
        internal.write_text('Private application data.', encoding='utf-8')
        (self.source / 'material' / 'outside.pdf').symlink_to(outside)
        (self.source / 'material' / 'internal.md').symlink_to(internal)
        (self.project / 'shortcut.md').symlink_to(self.source / 'material' / 'lehrbrief.pdf')
        self.assertEqual(self.client.get('/api/source', params={'path': 'material/missing.pdf'}).status_code, 404)
        (self.source / '.codex').mkdir()
        (self.source / '.codex' / 'private.md').write_text('Private.', encoding='utf-8')
        (self.source / 'material' / 'loop.pdf').symlink_to(self.source / 'material' / 'loop.pdf')
        paths = ['../outside.pdf', str(outside), str(self.pdf), 'master-learning-hub/internal.md',
                 'material', 'material/outside.pdf', 'material/internal.md',
                 'master-learning-hub/shortcut.md', '.codex/private.md', 'material/loop.pdf',
                 'material/script.html']
        for relative in paths:
            with self.subTest(path=relative):
                response = self.client.get('/api/source', params={'path': relative})
                self.assertEqual(response.status_code, 403, response.text)
                self.assertNotIn('Private application data.', response.text)

    def test_only_approved_bi_seed_is_imported_and_restart_preserves_progress(self):
        content = sample_import(['single_choice'])
        content['module'] = {'name': 'Business Intelligence', 'number': '32711', 'unit_count': 4}
        content['questions'][0].update(id='BI-META-01', source='material/lehrbrief.pdf')
        seed = self.project / 'imports' / 'business_intelligence_metadaten.json'
        seed.write_text(json.dumps(content), encoding='utf-8')
        unapproved = copy.deepcopy(content)
        unapproved['questions'][0]['id'] = 'BI-UNAPPROVED-01'
        (seed.parent / 'business_intelligence_extra.json').write_text(json.dumps(unapproved), encoding='utf-8')
        self.app.state.hub.import_content(sample_import(['single_choice']))
        self.app.state.hub.attempt('test-single_choice', [0])
        existing = copy.deepcopy(self.app.state.hub.export()['progress'])
        with TestClient(create_app(self.source, self.project / 'data', self.project, start_watch=False), base_url='http://127.0.0.1') as first:
            questions = first.get('/api/questions').json()
            self.assertEqual({question['id'] for question in questions}, {'BI-META-01', 'test-single_choice'})
            first.post('/api/attempts', json={'question_id': 'BI-META-01', 'answer': [0]})
            original_progress = next(row for row in first.get('/api/export').json()['progress'] if row['question_id'] == 'test-single_choice')
            self.assertEqual([original_progress], existing)
            bi_progress = next(row for row in first.get('/api/export').json()['progress'] if row['question_id'] == 'BI-META-01')
        with TestClient(create_app(self.source, self.project / 'data', self.project, start_watch=False), base_url='http://127.0.0.1') as second:
            self.assertEqual(second.get('/api/health').json()['question_count'], 2)
            exported = second.get('/api/export').json()
            self.assertEqual(next(row for row in exported['progress'] if row['question_id'] == 'BI-META-01'), bi_progress)
            self.assertEqual(next(row for row in exported['progress'] if row['question_id'] == 'test-single_choice'), original_progress)
            documents = {row['path']: row for row in second.get('/api/documents').json()}
            self.assertEqual(documents['@imports/business_intelligence_metadaten.json']['status'], 'imported')
            self.assertEqual(documents['@imports/business_intelligence_extra.json']['status'], 'pending')

    def test_approved_sessions3_to8_preserve_progress_units_and_do_not_load_movies(self):
        video = self.source / 'material' / 'session3.mp4'
        video.write_bytes(b'fake video bytes')
        content = sample_import(['single_choice'])
        content['module'] = {'name': 'Digitale Diversität', 'number': '32281', 'unit_count': 3}
        content['questions'][0].update(id='DD-E3-VIDEO-01', unit=3,
                                       source=video.relative_to(self.source).as_posix())
        seed = self.project / 'imports' / 'digitale_diversitaet_einheit3.json'
        seed.write_text(json.dumps(content), encoding='utf-8')
        approved_ids = {'DD-E3-VIDEO-01'}
        for unit in (4, 5, 6, 7, 8):
            extra = copy.deepcopy(content)
            extra['module']['unit_count'] = unit
            qid = f'DD-E{unit}-VIDEO-01'
            extra['questions'][0].update(id=qid, unit=unit)
            (seed.parent / f'digitale_diversitaet_einheit{unit}.json').write_text(json.dumps(extra), encoding='utf-8')
            approved_ids.add(qid)
        unapproved = copy.deepcopy(content)
        unapproved['questions'][0].update(id='DD-E9-UNAPPROVED-01', unit=9)
        (seed.parent / 'digitale_diversitaet_einheit9.json').write_text(json.dumps(unapproved), encoding='utf-8')
        self.app.state.hub.import_content(sample_import(['single_choice']))
        self.app.state.hub.attempt('test-single_choice', [0])
        old_progress = copy.deepcopy(self.app.state.hub.export()['progress'])
        read_bytes = Path.read_bytes

        def reject_movie_read(path):
            if path.suffix.lower() == '.mp4':
                raise AssertionError('MP4 originals must not be loaded into RAM during seed import.')
            return read_bytes(path)

        with patch.object(Path, 'read_bytes', reject_movie_read):
            with TestClient(create_app(self.source, self.project / 'data', self.project, start_watch=False), base_url='http://127.0.0.1') as first:
                self.assertEqual(first.get('/api/health').json()['question_count'], 7)
                questions = first.get('/api/questions').json()
                self.assertEqual({question['id'] for question in questions}, {'test-single_choice'} | approved_ids)
                modules = first.get('/api/modules').json()
                dd = next(module for module in modules if module['number'] == '32281')
                self.assertEqual(dd['units'], [1, 2, 3, 4, 5, 6, 7, 8])
                self.assertEqual([row['question_count'] for row in dd['unit_summaries'][2:]], [1, 1, 1, 1, 1, 1])
                self.assertEqual(first.get('/api/export').json()['progress'], old_progress)
                for qid in sorted(approved_ids):
                    attempted = first.post('/api/attempts', json={'question_id': qid, 'answer': [0]})
                    self.assertEqual(attempted.status_code, 200, attempted.text)
                all_progress = first.get('/api/export').json()['progress']
            with TestClient(create_app(self.source, self.project / 'data', self.project, start_watch=False), base_url='http://127.0.0.1') as second:
                self.assertEqual(second.get('/api/health').json()['question_count'], 7)
                self.assertEqual(second.get('/api/export').json()['progress'], all_progress)
                documents = {row['path']: row for row in second.get('/api/documents').json()}
                for unit in (3, 4, 5, 6, 7, 8):
                    self.assertEqual(documents[f'@imports/digitale_diversitaet_einheit{unit}.json']['status'], 'imported')
                self.assertEqual(documents['@imports/digitale_diversitaet_einheit9.json']['status'], 'pending')


if __name__ == '__main__':
    unittest.main()
