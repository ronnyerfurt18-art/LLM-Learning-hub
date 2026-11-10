"""Read-only document indexing and conservative, reviewable learning proposals.

No extractor writes to a source document. Pages for PDF/PPTX are real pages/slides;
DOCX, XLSX and text use logical sections because pagination is not available.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".markdown"})
_IGNORED_DIRECTORIES = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".agents", ".codex"})
_MODULE_FOLDER = re.compile(r"^(\d{5})(?:[\s_-]+(.+))?$")
_UNIT = re.compile(r"\b(?:session|einheit|kurseinheit|lektion|unit|ke)[\s._-]*(\d{1,3})\b", re.I)
_NUMBER_UNIT = re.compile(r"(?:^|[^\d])(\d{5})-(\d{1,3})(?:[-_ .]|$)")


def _search_text(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).lower()


def _display_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def classify_document(path: str | Path, study_root: str | Path) -> dict[str, Any]:
    """Infer module, unit and document kind without opening or changing a file."""
    root, file_path = Path(study_root).absolute(), Path(path).absolute()
    relative = file_path.relative_to(root)
    module_number = module_name = module_directory = None
    # The nearest matching ancestor wins if module directories are nested.
    for index, component in enumerate(relative.parts[:-1]):
        match = _MODULE_FOLDER.match(_display_text(component))
        if match:
            module_number = match.group(1)
            module_name = match.group(2) or f"Modul {module_number}"
            module_directory = Path(*relative.parts[:index + 1]).as_posix()
    inferred = _NUMBER_UNIT.search(relative.name)
    if not module_number and inferred:
        module_number = inferred.group(1)
        module_name = f"Modul {module_number}"
        module_directory = relative.parent.as_posix() if relative.parent != Path(".") else None

    unit = None
    # Both filename naming conventions take priority over a parent folder.
    explicit = _UNIT.search(_search_text(relative.name))
    if explicit:
        unit = int(explicit.group(1))
    elif inferred and inferred.group(1) == module_number:
        unit = int(inferred.group(2))
    for component in reversed(relative.parts[:-1]) if unit is None else []:
        match = _UNIT.search(_search_text(component))
        if match:
            unit = int(match.group(1))
            break

    searchable = _search_text(relative.as_posix())
    name = _search_text(relative.name)
    if any(term in name for term in ("sepa", "lastschrift", "belegbogen", "immatrikulation", "gebuhren", "zulassung")):
        kind = "administrative"
    elif any(term in searchable for term in ("prufungshinweis", "klausurhinweis", "prufungsinformation")):
        kind = "exam_info"
    elif any(term in searchable for term in ("altklausur", "klausur", "prufungsfrage")):
        kind = "exam"
    elif any(term in searchable for term in ("einsendeaufgab", "einsendearbeit")):
        kind = "assignment"
    elif any(term in searchable for term in ("musterlos", "losungsvorschlag", "losungen", "solution")):
        kind = "solution"
    elif any(term in searchable for term in ("zusammenfassung", "summary", "lernzettel", "lernunterlag")):
        kind = "summary"
    elif any(term in searchable for term in ("ubungsaufgab", "ubung", "exercise")):
        kind = "exercise"
    elif any(term in searchable for term in ("folien", "vorlesung", "lecture", "slides")) or file_path.suffix.lower() == ".pptx":
        kind = "lecture"
    elif inferred or any(term in searchable for term in ("skript", "kurseinheit", "studienbrief")):
        kind = "course_material"
    else:
        kind = "other"
    return {
        "path": relative.as_posix(), "name": file_path.name,
        "title": _display_text(file_path.stem), "extension": file_path.suffix.lower(),
        "module_name": module_name, "module_number": module_number,
        "module_directory": module_directory, "unit": unit, "kind": kind,
    }


def _pdf_pages(path: Path) -> list[dict[str, Any]]:
    try:
        import fitz
    except ImportError:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF ist passwortgeschützt und kann nicht gelesen werden.")
        return [{"page": i, "label": f"Seite {i}", "text": page.extract_text() or ""}
                for i, page in enumerate(reader.pages, 1)]
    with fitz.open(str(path)) as document:
        if document.needs_pass and not document.authenticate(""):
            raise ValueError("PDF ist passwortgeschützt und kann nicht gelesen werden.")
        return [{"page": i, "label": f"Seite {i}", "text": page.get_text("text")}
                for i, page in enumerate(document, 1)]


def _docx_pages(path: Path) -> list[dict[str, Any]]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    document = Document(str(path))
    lines = []
    # Preserve body ordering between paragraphs and tables.
    for node in document.element.body:
        if node.tag.endswith("}p"):
            lines.append(Paragraph(node, document).text)
        elif node.tag.endswith("}tbl"):
            for row in Table(node, document).rows:
                lines.append("\t".join(cell.text for cell in row.cells))
    return [{"page": 1, "label": "Dokument (keine feste Seitenzählung)", "text": "\n".join(lines)}]


def _shape_lines(shape: Any) -> list[str]:
    if getattr(shape, "has_table", False):
        return ["\t".join(cell.text for cell in row.cells) for row in shape.table.rows]
    if getattr(shape, "has_text_frame", False):
        return [shape.text_frame.text]
    # Grouped shapes have no own text frame.
    if hasattr(shape, "shapes"):
        return [line for child in shape.shapes for line in _shape_lines(child)]
    return []


def _pptx_pages(path: Path) -> list[dict[str, Any]]:
    from pptx import Presentation
    result = []
    for i, slide in enumerate(Presentation(str(path)).slides, 1):
        lines = [line for shape in slide.shapes for line in _shape_lines(shape)]
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame
            if notes is not None and notes.text.strip():
                lines.extend(["Referentennotizen:", notes.text])
        result.append({"page": i, "label": f"Folie {i}", "text": "\n".join(lines)})
    return result


def _xlsx_pages(path: Path) -> list[dict[str, Any]]:
    from openpyxl import load_workbook
    # Formulas remain source text; no formula recalculation or external links.
    workbook = load_workbook(str(path), read_only=True, data_only=False, keep_links=False)
    try:
        result = []
        for i, sheet in enumerate(workbook.worksheets, 1):
            lines = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if value is None else str(value) for value in row]
                while cells and cells[-1] == "":
                    cells.pop()
                if cells:
                    lines.append("\t".join(cells))
            result.append({"page": i, "label": f"Tabelle: {sheet.title}", "text": "\n".join(lines)})
        return result
    finally:
        workbook.close()


def extract_document(path: str | Path) -> list[dict[str, Any]]:
    """Return 1-based page/slide/section text. Raise on unreadable documents."""
    source = Path(path)
    extension = source.suffix.lower()
    extractors = {".pdf": _pdf_pages, ".docx": _docx_pages, ".pptx": _pptx_pages, ".xlsx": _xlsx_pages}
    if extension in extractors:
        return extractors[extension](source)
    if extension in {".txt", ".md", ".markdown"}:
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = raw.decode("utf-16")
            else:
                raise ValueError("Textdatei benötigt UTF-8 oder UTF-16; bitte Zeichencodierung prüfen.")
        if "\x00" in text:
            raise ValueError("Textdatei enthält Binärdaten und wurde nicht als Lerntext übernommen.")
        return [{"page": i, "label": f"Abschnitt {i}", "text": section}
                for i, section in enumerate(text.split("\f"), 1)]
    raise ValueError(f"Nicht unterstütztes Dateiformat: {extension}")


def _source_question(document: Mapping[str, Any], page: int, kind: str,
                     question: str, solution: str, topic: str) -> dict[str, Any]:
    content_key = "\0".join([str(document.get("path", "")), str(document.get("sha256", "")),
                               str(page), kind, question, solution])
    return {
        "id": "rule-" + hashlib.sha256(content_key.encode("utf-8")).hexdigest()[:24],
        "module": document.get("module_name"), "module_number": document.get("module_number"),
        "unit": document.get("unit"), "topic": topic, "type": kind,
        "question": question, "original_question": question, "original_solution": solution,
        "source": document.get("path", ""), "source_page": page,
        "model_answer": solution, "explanation": solution, "difficulty": 1,
        "verified": False, "generated_by": "Lokale Regeln", "review_status": "pending",
    }


_QA_QUESTION = re.compile(r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?(?:frage|question|q)(?:[ \t]+\d+)?[ \t]*:[ \t]*")
_QA_ANSWER = re.compile(r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?(?:antwort|answer|a|musterlösung|musterlosung|lösung|losung)[ \t]*:[ \t]*")
_DEFINITION = re.compile(r"^(.{2,80}?)\s+(bezeichnet|bedeutet|wird definiert als|ist definiert als)\s+(.{12,})$", re.I)
_BOLD_DEFINITION = re.compile(r"^\*\*([^*\n]{2,80})\*\*\s*[:–-]\s*(.{12,})$")
_GLOSSARY_LINE = re.compile(r"^([^:\n]{2,80})\s*:\s*(.{12,})$")
_DENIED_TERMS = frozenset({"hinweis", "beispiel", "quelle", "achtung", "seite", "antwort", "frage", "definition", "literatur", "abbildung", "tabelle"})


def generate_proposals(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Produce pending questions only for explicit Q/A pairs or definitions.

    Ordinary prose and lists produce no answer choices; distractors are never
    invented. Original text remains separate from the transformed cloze prompt.
    """
    if not document.get("module_name") or document.get("kind") == "administrative":
        return []
    proposals, definitions, used = [], [], set()
    pages = document.get("page_texts") or [{"page": 1, "text": document.get("text", "")}]
    for section in pages:
        page, text = int(section.get("page", 1)), section.get("text", "")
        questions = list(_QA_QUESTION.finditer(text))
        for index, marker in enumerate(questions):
            end = questions[index + 1].start() if index + 1 < len(questions) else len(text)
            answer = _QA_ANSWER.search(text, marker.end(), end)
            if answer is None:
                continue
            question = text[marker.end():answer.start()].strip("\r\n \t")
            solution = text[answer.end():end].strip("\r\n \t")
            if not question or not solution:
                continue
            signature = (question, solution)
            if signature in used:
                continue
            used.add(signature)
            topic = _display_text(document.get("title", "Originalfrage"))
            card = _source_question(document, page, "flashcard", question, solution, topic)
            proposals.append(card)
            if document.get("kind") == "exam":
                proposals.append(_source_question(document, page, "exam_question", question, solution, topic))
            elif re.search(r"\b(fallbeispiel|fallszenario|szenario)\b", _search_text(question)):
                proposals.append(_source_question(document, page, "case_analysis", question, solution, topic))

        in_glossary = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if re.match(r"^(?:#{1,6}\s*)?(?:glossar|definitionen|begriffsdefinitionen)\s*:?[ \t]*$", line, re.I):
                in_glossary = True
                continue
            if line.startswith("#") and not re.search(r"glossar|definitionen", line, re.I):
                in_glossary = False
            match = _DEFINITION.match(line)
            delimiter = None
            if match:
                term, delimiter, definition = match.groups()
            else:
                match = _BOLD_DEFINITION.match(line) or (_GLOSSARY_LINE.match(line) if in_glossary else None)
                if not match:
                    continue
                term, definition = match.groups()
            term = term.strip()
            if _search_text(term) in _DENIED_TERMS or term.endswith("?") or len(term.split()) > 9:
                continue
            signature = (term, definition)
            if signature in used:
                continue
            used.add(signature)
            definitions.append({"term": term, "definition": definition, "original": raw_line, "page": page})
            cloze = _source_question(document, page, "cloze", raw_line, raw_line, term)
            cloze.update({"question": "Ergänze den Fachbegriff aus der Definition.",
                          "text": f"___ {delimiter} {definition}" if delimiter else f"___: {definition}",
                          "answers": [term], "synonyms": [[]], "model_answer": term,
                          "explanation": raw_line})
            proposals.append(cloze)
    if 2 <= len(definitions) <= 12:
        # Repeated terms or equal definitions would create ambiguous matching.
        terms = [_search_text(row["term"]) for row in definitions]
        values = [_search_text(row["definition"]) for row in definitions]
        if len(set(terms)) == len(terms) and len(set(values)) == len(values):
            original = "\n".join(row["original"] for row in definitions)
            matching = _source_question(document, definitions[0]["page"], "matching", original,
                                        original, "Begriffe und Definitionen")
            matching.update({"question": "Ordne die Begriffe ihren Definitionen aus der Quelle zu.",
                             "pairs": [{"term": row["term"], "definition": row["definition"]} for row in definitions],
                             "source_pages": sorted({row["page"] for row in definitions})})
            proposals.append(matching)
    return proposals


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_documents(study_root: str | Path, project_root: str | Path | None = None,
                   known_hashes: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Recursively index supported files while excluding generated project data.

    File errors are contained in that document's result. Matching known hashes
    return ``status=unchanged`` and no text; the caller retains stored extraction.
    New and changed files return ``status=pending`` and a ``change`` indicator.
    All directory symlinks are skipped to avoid cycles; external file links and
    internal links pointing into the application project are also skipped.
    """
    root = Path(study_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Das Studienverzeichnis ist kein Ordner.")
    excluded = Path(project_root).resolve() if project_root else root / "master-learning-hub"
    known = known_hashes or {}
    results = []
    def traversal_error(error: OSError) -> None:
        # A partial listing must never turn inaccessible existing files into
        # missing documents in the caller's index. No result is committed yet.
        raise ValueError(f"Studienordner kann nicht vollständig gelesen werden: {error.filename or root}. {error.strerror or error}") from error

    for current, directories, files in os.walk(root, followlinks=False, onerror=traversal_error):
        directories[:] = sorted(name for name in directories
                                if name not in _IGNORED_DIRECTORIES and not name.startswith(".")
                                and not (Path(current) / name).is_symlink()
                                and not (Path(current) / name).resolve().is_relative_to(excluded))
        for name in sorted(files):
            source = Path(current) / name
            if name.startswith(".") or name.startswith("~$") or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                resolved = source.resolve(strict=True)
                if not resolved.is_relative_to(root) or resolved.is_relative_to(excluded) or not resolved.is_file():
                    continue
            except OSError:
                # A broken symbolic link is not a readable source document.
                if source.is_symlink():
                    continue
            record = classify_document(source, root)
            record.update({"sha256": None, "size": 0, "pages": 0, "page_texts": [],
                           "text": "", "proposals": [], "status": "pending", "error": None,
                           "change": "new" if record["path"] not in known else "changed"})
            try:
                initial_stat = source.stat()
                record["size"] = initial_stat.st_size
                record["sha256"] = _file_hash(source)
                if record["sha256"] == known.get(record["path"]):
                    record.update({"status": "unchanged", "change": "unchanged"})
                else:
                    page_texts = extract_document(source)
                    final_stat = source.stat()
                    if (final_stat.st_mtime_ns, final_stat.st_size, final_stat.st_ino) != (initial_stat.st_mtime_ns, initial_stat.st_size, initial_stat.st_ino):
                        raise ValueError("Datei wurde während der Erfassung verändert; bitte erneut synchronisieren.")
                    record.update({"page_texts": page_texts, "pages": len(page_texts),
                                   "text": "\n\n".join(page["text"] for page in page_texts)})
                    if not record["text"].strip():
                        raise ValueError("Kein lesbarer Text gefunden; gescannte Bilder benötigen OCR oder manuelle Aufbereitung.")
                    record["proposals"] = generate_proposals(record)
            except Exception as exc:
                record.update({"status": "error", "error": f"{type(exc).__name__}: {exc}", "proposals": []})
            results.append(record)
    return sorted(results, key=lambda record: record["path"])
