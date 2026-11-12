"""Text recognition for PDFs without a text layer."""
import glob
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter

from backend import ocr
from backend.documents import extract_document, scan_documents

LINES = ['Klausurfragen Personalverwaltung', '1. Erläutern Sie die Aufgaben der Personalplanung.',
         '2. Welche Rolle spielt die Personalentwicklung für die Mitarbeiterbindung?']


def scanned_pdf(path, lines=LINES):
    """A PDF that holds only an image of the text, like a scan or a photo."""
    fonts = glob.glob('/usr/share/fonts/**/*.ttf', recursive=True) + glob.glob('/System/Library/Fonts/*.ttf')
    font = ImageFont.truetype(fonts[0], 28) if fonts else ImageFont.load_default()
    image = Image.new('RGB', (1200, 120 + 70 * len(lines)), 'white')
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((40, 40 + index * 70), line, fill='black', font=font)
    image.save(path)


class LineOrderTests(unittest.TestCase):
    def test_boxes_become_lines_in_reading_order(self):
        box = lambda x, y, w=100, h=20: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        boxes = [box(300, 100), box(10, 10), box(10, 100), box(10, 50)]
        self.assertEqual(ocr.lines_from_boxes(boxes, ['rechts', 'oben', 'links', 'mitte']), 'oben\nmitte\nlinks rechts')
        self.assertEqual(ocr.lines_from_boxes([], []), '')


class FillTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.module = self.root / '32711 BI'
        self.module.mkdir()

    def tearDown(self):
        self.directory.cleanup()

    def test_only_pages_without_text_are_recognised(self):
        path = self.module / 'scan.pdf'
        scanned_pdf(path)
        pages = [{'page': 1, 'label': 'Seite 1', 'text': ''}]
        seen = []

        def fake(image):
            seen.append(image.size)
            return 'Erkannter Text'
        self.assertEqual(ocr.fill_missing_text(path, pages, recognise=fake), 1)
        self.assertEqual(pages[0]['text'], 'Erkannter Text')
        self.assertTrue(pages[0]['ocr'])
        self.assertEqual(len(seen), 1)
        full = [{'page': 1, 'label': 'Seite 1', 'text': 'Dieser Text stammt aus der Textebene des PDF.'}]
        self.assertEqual(ocr.fill_missing_text(path, full, recognise=fake), 0)
        self.assertNotIn('ocr', full[0])

    def test_without_the_package_a_scan_names_the_missing_piece(self):
        path = self.module / 'scan.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with path.open('wb') as stream:
            writer.write(stream)
        with patch.object(ocr, 'available', return_value=False):
            record = scan_documents(self.root)[0]
        self.assertEqual(record['status'], 'error')
        self.assertIn('rapidocr', record['error'])
        self.assertIn('Installation.command', record['error'])

    @unittest.skipUnless(ocr.available(), 'rapidocr ist nicht installiert')
    def test_scanned_pdf_is_read_with_the_local_engine(self):
        path = self.module / '32711-01-klausur.pdf'
        scanned_pdf(path)
        pages = extract_document(path)
        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0].get('ocr'))
        for line in LINES:
            self.assertIn(line, pages[0]['text'])
        record = scan_documents(self.root)[0]
        self.assertEqual(record['status'], 'pending')
        self.assertEqual(record['ocr_pages'], 1)
        self.assertIn('Personalplanung', record['text'])

    @unittest.skipUnless(ocr.available(), 'rapidocr ist nicht installiert')
    def test_blank_scan_still_fails_with_a_clear_message(self):
        path = self.module / 'leer.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with path.open('wb') as stream:
            writer.write(stream)
        record = scan_documents(self.root)[0]
        self.assertEqual(record['status'], 'error')
        self.assertIn('Texterkennung (OCR)', record['error'])
