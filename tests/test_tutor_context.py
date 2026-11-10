"""Local tutor context is scoped, cited, bounded and strictly read-only."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.core import Hub
from backend.tutor_context import MAX_CONTEXT_CHARS, MAX_PDF_PAGES, build_tutor_context
from tests.test_core import sample_import


def text_pdf(path, page_texts):
    """A real, minimal PDF with extractable text; no optional test dependency."""
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    }))
    for value in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        escaped = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream.set_data(('BT /F1 12 Tf 50 740 Td (' + escaped + ') Tj ET').encode('latin-1'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as output:
        writer.write(output)


def source_ref(page=1, path='material/original.pdf'):
    return {'path': path, 'title': 'Originaler Lehrbrief', 'chapter': f'Kapitel auf Seite {page}',
            'pdf_page': page, 'printed_page': str(page)}


def sample_content(number='32711'):
    return {
        'schema_version': 1, 'module_number': number, 'module_title': 'Beispielmodul',
        'overview': {'title': 'Modulüberblick', 'paragraphs': ['UEBERBLICK_EXKLUSIV erklärt den roten Faden.'],
                     'learning_path': ['Zuerst einordnen, danach anwenden.'], 'sources': [source_ref(1)],
                     'units': [{'unit': 1, 'title': 'Grundlagen', 'description': 'Einordnung der Themen.', 'topics': ['Begriffe']}]},
        'lessons': [
            {'id': 'lektion-a', 'unit': 1, 'title': 'Lektion A', 'summary': 'Zusammenfassung A.',
             'learning_goals': ['Ziel A: den Begriff erklären.'], 'exercise_ids': [],
             'sections': [
                 {'id': 'abschnitt-a', 'title': 'Abschnitt A', 'paragraphs': ['ABSCHNITT_A_EXKLUSIV ist die Erklärung.'],
                  'bullets': ['Ein wichtiger Aufzählungspunkt.'],
                  'table': {'headers': ['Begriff', 'Bedeutung'], 'rows': [['A', 'Tabelleninhalt A']]},
                  'note': 'Die Lernnotiz erklärt die Anwendung.', 'sources': [source_ref(2)]},
                 {'id': 'abschnitt-b', 'title': 'Abschnitt B', 'paragraphs': ['ABSCHNITT_B_EXKLUSIV ist ein anderes Thema.'],
                  'sources': [source_ref(3)]}]},
            {'id': 'lektion-b', 'unit': 1, 'title': 'Lektion B', 'summary': 'LEKTION_B_EXKLUSIV',
             'learning_goals': ['Ein anderes Ziel.'], 'exercise_ids': [],
             'sections': [{'id': 'fremder-abschnitt', 'title': 'Fremdes Thema', 'paragraphs': ['FREMDER_ABSCHNITT'],
                           'sources': [source_ref(4)]}]},
        ],
    }


def concept_content():
    content = sample_content('31311')
    content['module_title'] = 'IT Governance'
    content['overview']['units'] = []
    content['lessons'] = []
    content['overview']['big_picture'] = {
        'title': 'IT Governance als Gesamtbild', 'central_question': 'Wie wird IT gesteuert?',
        'intro': 'Governance ordnet die Informatik ein.', 'takeaway': 'Verantwortung, Ziele und Kontrolle verbinden.',
        'nodes': [
            {'id': 'itgov-richtung', 'title': 'Strategische Richtung', 'summary': 'RICHTUNG_KURATIERT',
             'role': 'Richtet die Entscheidungen an den Zielen aus.', 'sources': [source_ref(1)]},
            {'id': 'itgov-risiken', 'title': 'Risiken und Schutz', 'summary': 'RISIKEN_KURATIERT erklärt die Gefährdungen.',
             'role': 'Schützt die Zielerreichung durch Bewertung und Maßnahmen.',
             'scope_note': 'Belegte Nachlesestellen; ausführliche Lernkapitel folgen.',
             'sources': [source_ref(2), source_ref(3), source_ref(4)]},
            {'id': 'itgov-wert', 'title': 'Wertbeitrag', 'summary': 'WERTBEITRAG_KURATIERT',
             'role': 'Bewertet den Beitrag der IT.', 'sources': [source_ref(5)]},
        ],
        'connections': [{'from': 'itgov-richtung', 'to': 'itgov-risiken', 'label': 'bestimmt die Schutzperspektive'},
                        {'from': 'itgov-risiken', 'to': 'itgov-wert', 'label': 'sichert den Wertbeitrag'}],
    }
    return content


class TutorContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'study'
        self.project = self.source / 'master-learning-hub'
        (self.project / 'content').mkdir(parents=True)
        (self.source / 'material').mkdir()
        self.pdf = self.source / 'material' / 'original.pdf'
        text_pdf(self.pdf, [f'ORIGINAL_SEITE_{i}: Belegtext aus dem echten PDF.' for i in range(1, 13)])
        self.hub = Hub(self.project / 'data' / 'learning.sqlite')
        # A module with an assigned number must keep its pre-existing custom ID.
        self.mid = self.hub.add_module({'name': 'Business Intelligence'})['id']
        self.hub.patch_module(self.mid, {'number': '32711'})
        self.write_content(sample_content())

    def write_content(self, content, filename='example.json'):
        (self.project / 'content' / filename).write_text(json.dumps(content, ensure_ascii=False), encoding='utf-8')

    def context(self, **selection):
        return build_tutor_context(self.hub, self.project, self.source, self.mid, **selection)

    def test_section_isolation_and_curated_contract_with_concrete_original(self):
        context = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        text = context['context_text']
        self.assertEqual(context['module_id'], self.mid)
        self.assertEqual(context['lesson_id'], 'lektion-a')
        self.assertEqual(context['section_id'], 'abschnitt-a')
        self.assertNotIn('concept_id', context)
        for included in ('ABSCHNITT_A_EXKLUSIV', 'Zusammenfassung A', 'Ziel A', 'Aufzählungspunkt',
                         'Tabelleninhalt A', 'Lernnotiz', 'ORIGINAL_SEITE_2', 'PDF-Seite 2', '[S1]'):
            self.assertIn(included, text)
        for excluded in ('UEBERBLICK_EXKLUSIV', 'ABSCHNITT_B_EXKLUSIV', 'LEKTION_B_EXKLUSIV',
                         'FREMDER_ABSCHNITT', 'ORIGINAL_SEITE_1:', 'ORIGINAL_SEITE_3:'):
            self.assertNotIn(excluded, text)
        self.assertEqual(context['sources'], [{**source_ref(2), 'id': 'S1'}])
        self.assertTrue(context['suggestions'])
        self.assertIn('UNVERTRAUTE LERNDATEN', text)

    def test_lesson_has_its_sections_and_overview_does_not_load_lessons(self):
        lesson = self.context(lesson_id='lektion-a')
        self.assertIn('ABSCHNITT_A_EXKLUSIV', lesson['context_text'])
        self.assertIn('ABSCHNITT_B_EXKLUSIV', lesson['context_text'])
        self.assertNotIn('LEKTION_B_EXKLUSIV', lesson['context_text'])
        self.assertEqual([ref['id'] for ref in lesson['sources']], ['S1', 'S2'])
        self.assertEqual([ref['pdf_page'] for ref in lesson['sources']], [2, 3])
        self.assertEqual(lesson, self.context(lesson_id='lektion-a'))
        overview = self.context()
        self.assertIn('UEBERBLICK_EXKLUSIV', overview['context_text'])
        self.assertIn('ORIGINAL_SEITE_1:', overview['context_text'])
        self.assertNotIn('ABSCHNITT_A_EXKLUSIV', overview['context_text'])
        self.assertNotIn('lesson_id', overview)

    def test_unknown_or_cross_context_selection_is_rejected(self):
        for selection in ({'lesson_id': 'unknown'}, {'lesson_id': 'lektion-a', 'section_id': 'fremder-abschnitt'},
                          {'concept_id': 'unknown'}):
            with self.subTest(selection=selection), self.assertRaises(KeyError):
                self.context(**selection)
        for selection in ({'section_id': 'abschnitt-a'}, {'concept_id': 'x', 'lesson_id': 'lektion-a'},
                          {'concept_id': 'x', 'section_id': 'abschnitt-a'}, {'lesson_id': ''},
                          {'lesson_id': []}, {'section_id': True}):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.context(**selection)
        with self.assertRaises(KeyError):
            build_tutor_context(self.hub, self.project, self.source, 'unknown-module')
        other = self.hub.add_module({'name': 'Anderes Modul', 'number': '12345'})
        with self.assertRaises(KeyError):
            build_tutor_context(self.hub, self.project, self.source, other['id'], lesson_id='lektion-a')

    def test_it_governance_without_lessons_uses_selected_concept_and_pdf_text(self):
        content = concept_content()
        self.write_content(content, 'itgov.json')
        module = self.hub.add_module({'name': 'IT Governance', 'number': '31311'})
        context = build_tutor_context(self.hub, self.project, self.source, module['id'], concept_id='itgov-risiken')
        self.assertEqual(context['concept_id'], 'itgov-risiken')
        self.assertEqual(context['title'], 'Risiken und Schutz')
        self.assertNotIn('lesson_id', context)
        for included in ('RISIKEN_KURATIERT', 'Schützt die Zielerreichung', 'Nachlesestellen',
                         'bestimmt die Schutzperspektive', 'sichert den Wertbeitrag',
                         'ORIGINAL_SEITE_2:', 'ORIGINAL_SEITE_3:', 'ORIGINAL_SEITE_4:'):
            self.assertIn(included, context['context_text'])
        for excluded in ('RICHTUNG_KURATIERT', 'WERTBEITRAG_KURATIERT', 'ORIGINAL_SEITE_1:', 'ORIGINAL_SEITE_5:'):
            self.assertNotIn(excluded, context['context_text'])
        self.assertEqual([ref['pdf_page'] for ref in context['sources']], [2, 3, 4])
        self.assertIn('3 belegten PDF-Seiten', context['notice'])

    def test_malicious_source_paths_and_external_content_symlinks_are_rejected(self):
        outside = self.root / 'outside.pdf'
        text_pdf(outside, ['SECRET_OUTSIDE'])
        (self.project / 'internal.pdf').write_bytes(self.pdf.read_bytes())
        (self.source / 'material' / 'outside.pdf').symlink_to(outside)
        (self.source / 'material' / 'internal.pdf').symlink_to(self.project / 'internal.pdf')
        for path in ('../outside.pdf', str(outside), 'material/outside.pdf', 'material/internal.pdf',
                     'master-learning-hub/internal.pdf', '.codex/secret.pdf'):
            content = sample_content()
            content['lessons'][0]['sections'][0]['sources'][0]['path'] = path
            self.write_content(content)
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        self.write_content(sample_content())
        linked = self.root / 'outside.json'
        linked.write_text(json.dumps(sample_content()), encoding='utf-8')
        (self.project / 'content' / 'example.json').unlink()
        (self.project / 'content' / 'example.json').symlink_to(linked)
        with self.assertRaises(ValueError):
            self.context()

    def test_only_the_selected_valid_package_is_required(self):
        (self.project / 'content' / 'broken.json').write_text('[', encoding='utf-8')
        self.assertIn('UEBERBLICK_EXKLUSIV', self.context()['context_text'])
        self.write_content(sample_content(), 'duplicate.json')
        with self.assertRaises(ValueError):
            self.context()

    def test_database_remains_read_only_even_for_existing_progress(self):
        # Populate data outside the context request, then forbid every write in SQL.
        self.hub.import_content(sample_import(['single_choice']))
        self.hub.attempt('test-single_choice', [0])
        with self.hub.db() as connection:
            connection.execute('INSERT INTO metadata VALUES (?,?)', ('existing', '{"keep": true}'))
        before = self.hub.export()
        before.pop('exported_at')
        original_connect = sqlite3.connect

        def read_only_connection(*args, **kwargs):
            connection = original_connect(*args, **kwargs)

            def authorize(action, arg1, arg2, database, trigger):
                if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                              sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            connection.set_authorizer(authorize)
            return connection

        with patch('backend.core.sqlite3.connect', side_effect=read_only_connection):
            self.context()
            self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        after = self.hub.export()
        after.pop('exported_at')
        self.assertEqual(before, after)

    def test_context_payload_pdf_pages_and_source_count_are_bounded(self):
        content = sample_content()
        section = content['lessons'][0]['sections'][0]
        section['paragraphs'] = ['Kuratierter Text. ' * 2500]
        section['sources'] = [source_ref(page) for page in range(1, 13)]
        for ref in section['sources']:
            ref['title'] = 'Originalbezeichnung ' * 200
            ref['chapter'] = 'Kapitelbezeichnung ' * 200
        self.write_content(content)
        text_pdf(self.pdf, [f'ORIGINAL_SEITE_{page}: ' + 'Langer PDF-Belegtext. ' * 1000 for page in range(1, 13)])
        context = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        self.assertLessEqual(len(context['context_text']), MAX_CONTEXT_CHARS)
        self.assertLess(len(json.dumps(context, ensure_ascii=False)), 33_000)
        self.assertEqual(len(context['sources']), 8)
        self.assertLessEqual(context['context_text'].count('Original-PDF · PDF-Seite'), MAX_PDF_PAGES)
        self.assertNotIn('ORIGINAL_SEITE_6:', context['context_text'])
        self.assertIn('Ausschnitt gekürzt', context['context_text'])
        self.assertIn('gekürzt', context['notice'])
        self.assertIn('höchstens acht', context['notice'])
        self.assertIn('fünf belegte Seiten', context['notice'])
        for ref in context['sources']:
            self.assertIn(f"[{ref['id']}]", context['context_text'])

    def test_compact_context_for_local_models_keeps_matching_pdf_passages(self):
        content = sample_content()
        content['lessons'][0]['sections'][0]['sources'] = [source_ref(1)]
        self.write_content(content)
        text_pdf(self.pdf, ['Füllsatz über das Wetter am Morgen. ' * 300
                            + 'Der Aufzählungspunkt und die Lernnotiz stehen hier TREFFERSATZ. ' + 'Noch ein Wettersatz. ' * 300])
        full = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        compact = self.context(lesson_id='lektion-a', section_id='abschnitt-a', max_chars=5000)
        self.assertLessEqual(len(compact['context_text']), 5000)
        self.assertLess(len(compact['context_text']), len(full['context_text']))
        # The full context keeps the beginning of the page; the compact one the matching passage.
        self.assertNotIn('TREFFERSATZ', full['context_text'])
        self.assertIn('TREFFERSATZ', compact['context_text'])
        self.assertIn('ABSCHNITT_A_EXKLUSIV', compact['context_text'])
        self.assertIn('kompakt', compact['notice'])
        self.assertNotIn('kompakt', full['notice'])
        [span] = compact['excerpts']['S1']
        units = compact['context_text'].encode('utf-16-le')
        self.assertIn('TREFFERSATZ', units[span['start'] * 2:span['end'] * 2].decode('utf-16-le'))

    def test_figures_of_included_sections_are_linked_to_their_source_ids(self):
        content = sample_content()
        asset = self.project / 'imports' / 'assets' / 'test' / 'abb-9.png'
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b'\x89PNG\r\n\x1a\n')
        section = content['lessons'][0]['sections'][0]
        section['sources'] = [source_ref(5), source_ref(8)]
        section['image'] = {'path': 'assets/test/abb-9.png', 'caption': 'Abbildung 9: Das CDM', 'source_page': 8}
        self.write_content(content)
        lesson = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        [figure] = lesson['figures']
        self.assertEqual(figure['path'], 'assets/test/abb-9.png')
        self.assertEqual(figure['caption'], 'Abbildung 9: Das CDM')
        page_eight = next(ref['id'] for ref in lesson['sources'] if ref['pdf_page'] == 8)
        self.assertEqual(figure['source_ids'], [page_eight])
        self.assertEqual(self.context(lesson_id='lektion-a', section_id='abschnitt-b')['figures'], [])
        self.assertEqual(self.context()['figures'], [])

    def test_excerpt_positions_point_into_context_text(self):
        content = sample_content()
        content['lessons'][0]['sections'][0]['sources'] = [source_ref(1)]
        self.write_content(content)
        text_pdf(self.pdf, ['ORIGINAL_AUSZUG: Prozessorientierung und Kernprozesse'])
        context = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        [span] = context['excerpts']['S1']
        units = context['context_text'].encode('utf-16-le')
        excerpt = units[span['start'] * 2:span['end'] * 2].decode('utf-16-le')
        self.assertEqual(span['pdf_page'], 1)
        self.assertIn('ORIGINAL_AUSZUG: Prozessorientierung', excerpt)
        self.assertNotIn('Original-PDF · PDF-Seite', excerpt)

    def test_utf16_positions_match_javascript_for_characters_outside_bmp(self):
        from backend.tutor_context import _utf16_index
        text = 'a𝑥b'
        self.assertEqual(_utf16_index(text, 2), 3)
        self.assertEqual(_utf16_index(text, 3), 4)

    def test_pdf_ranges_are_sampled_across_sources_and_only_from_cited_pages(self):
        content = sample_content()
        refs = [source_ref(2), source_ref(9)]
        refs[0]['pdf_page_end'] = 8
        content['lessons'][0]['sections'][0]['sources'] = refs
        self.write_content(content)
        context = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        for page in (2, 3, 4, 5, 9):
            self.assertIn(f'ORIGINAL_SEITE_{page}:', context['context_text'])
        for page in (1, 6, 8, 10):
            self.assertNotIn(f'ORIGINAL_SEITE_{page}:', context['context_text'])
        self.assertIn('weitere verlinkte Seiten sind nicht beigefügt', context['notice'])

    def test_no_source_ids_are_returned_for_curated_sections_omitted_by_text_limit(self):
        content = sample_content()
        content['lessons'][0]['sections'][0]['paragraphs'] = ['Langer Abschnitt A. ' * 2000]
        self.write_content(content)
        context = self.context(lesson_id='lektion-a')
        self.assertNotIn('ABSCHNITT_B_EXKLUSIV', context['context_text'])
        self.assertEqual([ref['pdf_page'] for ref in context['sources']], [2])
        self.assertNotIn('[S2]', context['context_text'])

    def test_videos_images_and_unreadable_pdfs_are_not_claimed_as_extracted(self):
        content = sample_content()
        video = self.source / 'material' / 'lecture.mp4'
        video.write_bytes(b'Not a real video; it must never be opened for extraction.')
        section = content['lessons'][0]['sections'][0]
        section['sources'] = [{'kind': 'video', 'path': 'material/lecture.mp4', 'title': 'Vorlesung',
                               'timestamp_seconds': 12.5, 'timestamp_end_seconds': 18}]
        asset = self.project / 'imports' / 'assets' / 'figure.png'
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b'Not an image; only its curated caption is context.')
        section['image'] = {'path': 'assets/figure.png', 'source_page': 2, 'caption': 'Kuratierte Abbildungserläuterung'}
        self.write_content(content)
        with patch('backend.tutor_context.PdfReader', side_effect=AssertionError('Video or image must not be read.')):
            context = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        self.assertIn('Video-Zeitmarke 12.5 s bis 18 s', context['context_text'])
        self.assertIn('Bild nicht ausgelesen', context['context_text'])
        self.assertIn('kein Original-PDF-Text', context['notice'])
        self.assertIn('MP4-Transkription findet nicht statt', context['notice'])
        self.assertEqual(context['sources'][0]['id'], 'S1')
        self.write_content(sample_content())
        self.pdf.write_bytes(b'%PDF-1.4\ninvalid PDF without pages')
        context = self.context(lesson_id='lektion-a', section_id='abschnitt-a')
        self.assertIn('nicht als Text verfügbar', context['notice'])
        self.assertIn('kein Original-PDF-Text', context['notice'])


if __name__ == '__main__':
    unittest.main()
