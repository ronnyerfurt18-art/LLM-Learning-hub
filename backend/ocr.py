"""Offline text recognition (OCR) for PDF pages without a text layer.

Scanned or photographed PDFs carry no text, so the index could not read them.
This module renders such pages with pypdfium2 and recognises the text locally
with RapidOCR (ONNX models bundled in the package, nothing is downloaded and
nothing leaves the computer). Pages that already have text are left alone.
Recognised text is marked ``ocr: True`` so every screen can say where it came from.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

# Pages with fewer characters than this are treated as image-only and recognised.
MIN_TEXT_CHARS = 20
RENDER_DPI = 200
# Boxes whose vertical centres differ by less than this share of the box height form one line.
LINE_TOLERANCE = 0.6
INSTALL_HINT = 'Für die Texterkennung fehlt das Paket „rapidocr“; bitte Installation.command erneut ausführen.'

_lock = threading.Lock()
_engine: Any = None


def available() -> bool:
    try:
        import pypdfium2  # noqa: F401
        import rapidocr  # noqa: F401
    except ImportError:
        return False
    return True


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr import RapidOCR
            # The bundled PP-OCRv6 models read Latin script including German umlauts.
            _engine = RapidOCR(params={'Global.log_level': 'warning'})
        return _engine


def lines_from_boxes(boxes, texts) -> str:
    """Reading order from detection boxes: top to bottom, left to right, one text line per visual line."""
    items = []
    if boxes is None or texts is None:
        return ''
    for box, text in zip(boxes, texts):
        if not text or not str(text).strip():
            continue
        ys = [float(point[1]) for point in box]
        xs = [float(point[0]) for point in box]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), str(text).strip()))
    items.sort(key=lambda item: (item[0], item[2]))
    lines: list[list[tuple]] = []
    for item in items:
        if lines and abs(item[0] - lines[-1][-1][0]) <= LINE_TOLERANCE * max(item[1], lines[-1][-1][1], 1):
            lines[-1].append(item)
        else:
            lines.append([item])
    return '\n'.join(' '.join(part[3] for part in sorted(line, key=lambda part: part[2])) for line in lines)


def recognise_image(image) -> str:
    """Text of one PIL image, or '' when nothing is recognised."""
    import numpy as np
    result = _get_engine()(np.asarray(image.convert('RGB')))
    if result is None or result.txts is None or len(result.txts) == 0:
        return ''
    return lines_from_boxes(result.boxes, result.txts)


def _render(path: Path, number: int):
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(path))
    try:
        return document[number - 1].render(scale=RENDER_DPI / 72).to_pil()
    finally:
        document.close()


def fill_missing_text(path: str | Path, pages: list[dict[str, Any]], recognise=None) -> int:
    """Recognise the text of every page that has none. Returns the number of pages recognised.

    ``recognise`` (image -> text) can be replaced in tests; by default the local engine is used.
    Raises ImportError with the install hint when OCR would be needed but is not installed.
    """
    missing = [page for page in pages if len((page.get('text') or '').strip()) < MIN_TEXT_CHARS]
    if not missing:
        return 0
    if recognise is None:
        if not available():
            raise ImportError(INSTALL_HINT)
        recognise = recognise_image
    source, done = Path(path), 0
    LOG.info('Texterkennung für %d von %d Seiten: %s', len(missing), len(pages), source.name)
    for page in missing:
        text = recognise(_render(source, int(page['page'])))
        if text.strip():
            page['text'] = text
            page['ocr'] = True
            done += 1
    return done
