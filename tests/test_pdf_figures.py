"""Offline figure rendering for "Länger nachdenken" and the module import."""
import base64
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest

from backend import pdf_figures
from backend.module_import import window_messages

pytestmark = pytest.mark.skipif(not pdf_figures.available(), reason='pypdfium2 nicht installiert')


def _pdf(folder):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    for content in (b'BT /F1 12 Tf 72 770 Td (Die erste Ebene der Persoenlichkeit) Tj ET',
                    b'0 0 0 RG 2 w 150 300 300 300 re S 200 350 200 200 re S '
                    b'BT /F1 11 Tf 72 250 Td (Abbildung 7: Layers of Diversity) Tj ET'):
        page = writer.add_blank_page(595, 842)
        stream = DecodedStreamObject()
        stream.set_data(content)
        page[NameObject('/Contents')] = writer._add_object(stream)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    path = Path(folder) / 'lehrbrief.pdf'
    with path.open('wb') as handle:
        writer.write(handle)
    return path


def test_requested_numbers_and_captions():
    assert pdf_figures.requested_numbers('Was sagt Abbildung 7, und Abb. 3?') == ['7', '3']
    assert pdf_figures.captions('Text\nAbbildung 7: Layers of Diversity\n')[0]['number'] == '7'
    assert pdf_figures.captions('siehe Abbildung 7 oben') == []  # a reference is not a caption


def test_figure_is_found_on_next_page_cropped_and_cached():
    with TemporaryDirectory() as folder:
        path = _pdf(folder)
        cache = Path(folder) / 'cache'
        images = pdf_figures.figure_images([{'id': 'S1', 'path': path, 'page': 1}], 'Was sagt Abbildung 7?', cache)
        assert [(item['id'], item['page']) for item in images] == [('S1', 2)]
        assert 'Layers of Diversity' in images[0]['caption']
        from PIL import Image
        from io import BytesIO
        width, height = Image.open(BytesIO(base64.b64decode(images[0]['image']))).size
        assert width < 1240 and height < 1754  # cropped to the drawing, not the whole A4 page
        assert len(list(cache.glob('*.png'))) == 1
        assert 'Bild 1: [S1] PDF-Seite 2' in pdf_figures.figure_note(images)


def test_import_window_gets_descriptions_outside_the_quoted_pages():
    with TemporaryDirectory() as folder:
        path = _pdf(folder)
        window = [{'page': 2, 'text': 'Abbildung 7: Layers of Diversity'}]
        seen = []
        figures = pdf_figures.window_figures(path, window, lambda image, caption: seen.append(caption) or 'Vier Ringe.', None)
        assert figures == [{'page': 2, 'caption': 'Abbildung 7: Layers of Diversity', 'description': 'Vier Ringe.'}]
        content = window_messages({'name': 'Digitale Diversität'}, {'unit': 1}, window, figures)[1]['content']
        assert content.index('ENDE DES AUSSCHNITTS') < content.index('Vier Ringe.')


def test_describer_is_off_for_text_only_models():
    def request(path, body=None, timeout=3):
        if path == '/api/tags':
            return {'models': [{'name': 'text:1b'}]}
        return {'capabilities': ['completion']}
    assert pdf_figures.ollama_describer('text:1b', request) is None
