"""Read-only indexing tests; all fixtures are created in disposable directories."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.documents import classify_document, extract_document, generate_proposals, scan_documents


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_nested_module_and_combining_unicode(self):
        path = self.root / "1.semester" / "32281 Digitale Diversita\u0308t" / "Session1" / "Lo\u0308sungsvorschla\u0308ge U\u0308bungsaufgaben Einheit 1.pdf"
        result = classify_document(path, self.root)
        self.assertEqual(result["module_number"], "32281")
        self.assertEqual(result["module_name"], "Digitale Diversität")
        self.assertEqual(result["unit"], 1)
        self.assertEqual(result["kind"], "solution")
        self.assertEqual(result["path"], path.relative_to(self.root).as_posix())

    def test_unit_from_course_filename(self):
        path = self.root / "1.semester" / "32711 BI" / "32711-03-S#1-2001332-V1.0.pdf"
        result = classify_document(path, self.root)
        self.assertEqual((result["module_number"], result["unit"], result["kind"]), ("32711", 3, "course_material"))

    def test_root_administrative_document_is_unassigned(self):
        result = classify_document(self.root / "Belegbogen_8919810_WS2026.pdf", self.root)
        self.assertIsNone(result["module_number"])
        self.assertIsNone(result["unit"])
        self.assertEqual(result["kind"], "administrative")

    def test_explicit_file_unit_precedes_folder_unit(self):
        path = self.root / "32281 Diversität" / "Session1" / "Einheit-2-Zusammenfassung.md"
        self.assertEqual(classify_document(path, self.root)["unit"], 2)

    def test_course_filename_unit_precedes_folder_unit(self):
        path = self.root / "32711 BI" / "Session1" / "32711-03-S#1-2001332-V1.0.pdf"
        self.assertEqual(classify_document(path, self.root)["unit"], 3)

    def test_path_outside_root_rejected(self):
        with self.assertRaises(ValueError):
            classify_document(self.root.parent / "outside.txt", self.root)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_utf8_markdown_and_logical_pages(self):
        source = self.root / "notes.md"
        source.write_text("# Diversität\nEinführung\fZweite Seite", encoding="utf-8")
        self.assertEqual(extract_document(source)[1], {"page": 2, "label": "Abschnitt 2", "text": "Zweite Seite"})

    def test_utf16_and_binary_detection(self):
        source = self.root / "notes.txt"
        source.write_bytes("Diversität\nAntwort".encode("utf-16"))
        self.assertIn("Diversität", extract_document(source)[0]["text"])
        source.write_bytes(b"hello\x00binary")
        with self.assertRaises(ValueError):
            extract_document(source)

    def test_docx_keeps_paragraph_table_order(self):
        from docx import Document
        source = self.root / "notes.docx"
        doc = Document()
        doc.add_paragraph("Vor der Tabelle")
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Begriff"
        table.cell(0, 1).text = "Definition"
        doc.add_paragraph("Nach der Tabelle")
        doc.save(source)
        self.assertEqual(extract_document(source)[0]["text"], "Vor der Tabelle\nBegriff\tDefinition\nNach der Tabelle")

    def test_pptx_slides_text_tables_and_notes(self):
        from pptx import Presentation
        from pptx.util import Inches
        source = self.root / "notes.pptx"
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = "Lerninhalt"
        table = slide.shapes.add_table(1, 2, Inches(1), Inches(2), Inches(5), Inches(1)).table
        table.cell(0, 0).text = "Begriff"
        table.cell(0, 1).text = "Erklärung"
        slide.notes_slide.notes_text_frame.text = "Zusätzliche Notiz"
        slide2 = deck.slides.add_slide(deck.slide_layouts[5])
        slide2.shapes.title.text = "Zweite Folie"
        deck.save(source)
        pages = extract_document(source)
        self.assertEqual(len(pages), 2)
        self.assertIn("Begriff\tErklärung", pages[0]["text"])
        self.assertIn("Zusätzliche Notiz", pages[0]["text"])
        self.assertEqual(pages[1]["page"], 2)

    def test_xlsx_values_formula_and_multiple_sheets(self):
        from openpyxl import Workbook
        source = self.root / "notes.xlsx"
        workbook = Workbook()
        workbook.active.title = "Definitionen"
        workbook.active.append(["Begriff", "Definition", None])
        workbook.active.append(["Wert", "=1+1"])
        workbook.create_sheet("Übungen").append(["Frage", 2])
        workbook.save(source)
        pages = extract_document(source)
        self.assertEqual(len(pages), 2)
        self.assertIn("=1+1", pages[0]["text"])
        self.assertEqual(pages[1]["label"], "Tabelle: Übungen")

    def test_pdf_page_numbers_and_encryption(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        source = self.root / "notes.pdf"
        plain = PdfWriter()
        for text in ("First page", "Second page"):
            page = plain.add_blank_page(width=612, height=792)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 60 750 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = plain._add_object(stream)
        with source.open("wb") as stream:
            plain.write(stream)
        pages = extract_document(source)
        self.assertEqual([page["page"] for page in pages], [1, 2])
        self.assertIn("Second page", pages[1]["text"])
        encrypted = self.root / "encrypted.pdf"
        writer = PdfWriter()
        writer.append(PdfReader(source))
        writer.encrypt("secret")
        with encrypted.open("wb") as stream:
            writer.write(stream)
        with self.assertRaises(ValueError):
            extract_document(encrypted)


class ProposalTests(unittest.TestCase):
    def document(self, text, kind="solution"):
        return {"path": "32281 Diversität/Einheit1/notes.txt", "sha256": "abc",
                "module_name": "Diversität", "module_number": "32281", "unit": 1,
                "title": "Übungsfragen", "kind": kind, "text": text,
                "page_texts": [{"page": 3, "text": text}]}

    def test_explicit_qa_exact_originals_and_pending_status(self):
        question = "Was bedeutet Diversität?\nNennen Sie zwei Beispiele."
        answer = "Verschiedenheit.\nBeispiele: Alter und Beruf."
        proposals = generate_proposals(self.document(f"Frage: {question}\nAntwort: {answer}"))
        self.assertEqual(len(proposals), 1)
        card = proposals[0]
        self.assertEqual(card["original_question"], question)
        self.assertEqual(card["original_solution"], answer)
        self.assertEqual(card["source_page"], 3)
        self.assertFalse(card["verified"])
        self.assertEqual(card["review_status"], "pending")
        self.assertEqual(card["type"], "flashcard")
        self.assertEqual(card["id"], generate_proposals(self.document(f"Frage: {question}\nAntwort: {answer}"))[0]["id"])

    def test_question_without_answer_does_not_invent_content(self):
        self.assertEqual(generate_proposals(self.document("Frage: Warum entsteht Diversität?")), [])

    def test_plain_prose_and_metadata_are_not_definitions(self):
        self.assertEqual(generate_proposals(self.document("Autor: Max Mustermann\nTitel: Alles über die Diversität\nDiversity ist ein wichtiges Thema.")), [])

    def test_definitions_generate_cloze_and_unambiguous_matching(self):
        text = "Diversität bezeichnet die Vielfalt von Menschen.\n**Inklusion**: Gleichberechtigte Teilhabe aller Menschen."
        proposals = generate_proposals(self.document(text))
        self.assertEqual([q["type"] for q in proposals], ["cloze", "cloze", "matching"])
        self.assertEqual(proposals[0]["answers"], ["Diversität"])
        self.assertEqual(proposals[0]["original_solution"], text.splitlines()[0])
        self.assertTrue(proposals[0]["text"].startswith("___ bezeichnet"))
        self.assertEqual(len(proposals[-1]["pairs"]), 2)
        self.assertFalse(any(q["type"] in {"single_choice", "multiple_choice"} for q in proposals))

    def test_ambiguous_definitions_do_not_generate_matching(self):
        text = "**Diversität**: Vielfalt von Menschen in einer Gruppe.\n**Diversität**: Unterschiede zwischen Menschen und Gruppen."
        self.assertNotIn("matching", [q["type"] for q in generate_proposals(self.document(text))])

    def test_admin_and_unassigned_do_not_generate_questions(self):
        document = self.document("Frage: Worum geht es?\nAntwort: Um das Studium.")
        document["module_number"] = None
        document["module_name"] = None
        self.assertEqual(generate_proposals(document), [])
        document["module_number"] = "32281"
        document["module_name"] = "Diversität"
        document["kind"] = "administrative"
        self.assertEqual(generate_proposals(document), [])

    def test_manually_assigned_module_without_number_can_generate(self):
        document = self.document("Frage: Worum geht es?\nAntwort: Um das Studium.")
        document["module_number"] = None
        self.assertEqual(len(generate_proposals(document)), 1)

    def test_original_exams_and_cases_offer_appropriate_variant(self):
        text = "Frage: Beschreiben Sie das Fallszenario.\nAntwort: Die Antwort aus der Quelle."
        self.assertEqual([q["type"] for q in generate_proposals(self.document(text))], ["flashcard", "case_analysis"])
        self.assertEqual([q["type"] for q in generate_proposals(self.document(text, "exam"))], ["flashcard", "exam_question"])


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.module = self.root / "1.semester" / "32281 Diversität" / "Session1"
        self.module.mkdir(parents=True)

    def test_scan_hash_changes_errors_exclusions_and_original_integrity(self):
        valid = self.module / "notes.txt"
        valid.write_text("Frage: Was ist Diversität?\nAntwort: Verschiedenheit von Menschen.", encoding="utf-8")
        broken = self.module / "broken.pdf"
        broken.write_bytes(b"This is not a PDF")
        (self.module / "video.mp4").write_bytes(b"unindexed")
        (self.module / "~$draft.docx").write_bytes(b"Office temporary file")
        project = self.root / "master-learning-hub"
        project.mkdir()
        (project / "generated.md").write_text("Generated question data", encoding="utf-8")
        before = hashlib.sha256(valid.read_bytes()).hexdigest()
        stat = valid.stat()
        records = scan_documents(self.root, project)
        self.assertEqual(len(records), 2)
        indexed = next(row for row in records if row["name"] == "notes.txt")
        error = next(row for row in records if row["name"] == "broken.pdf")
        self.assertEqual(indexed["sha256"], before)
        self.assertEqual(len(indexed["proposals"]), 1)
        self.assertEqual(error["status"], "error")
        self.assertTrue(error["error"])
        self.assertEqual((valid.stat().st_size, valid.stat().st_mtime_ns), (stat.st_size, stat.st_mtime_ns))
        self.assertEqual(hashlib.sha256(valid.read_bytes()).hexdigest(), before)
        known = {indexed["path"]: before}
        unchanged = next(row for row in scan_documents(self.root, project, known) if row["name"] == "notes.txt")
        self.assertEqual(unchanged["status"], "unchanged")
        self.assertEqual(unchanged["text"], "")
        self.assertEqual(unchanged["proposals"], [])
        valid.write_text("New source content", encoding="utf-8")
        changed = next(row for row in scan_documents(self.root, project, known) if row["name"] == "notes.txt")
        self.assertEqual(changed["change"], "changed")
        self.assertNotEqual(changed["sha256"], before)

    def test_external_symlinks_and_directory_loops_are_skipped(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "secret.txt"
            external.write_text("Outside", encoding="utf-8")
            (self.module / "outside.txt").symlink_to(external)
            (self.module / "loop").symlink_to(self.root, target_is_directory=True)
            (self.module / "valid.txt").write_text("Inside", encoding="utf-8")
            self.assertEqual([row["name"] for row in scan_documents(self.root)], ["valid.txt"])

    def test_empty_scanned_pdf_has_actionable_error(self):
        from pypdf import PdfWriter
        path = self.module / "scan.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with path.open("wb") as stream:
            writer.write(stream)
        record = scan_documents(self.root)[0]
        self.assertEqual(record["status"], "error")
        self.assertIn("OCR", record["error"])

    def test_another_copy_of_the_program_inside_the_study_folder_is_not_indexed(self):
        (self.module / "notes.txt").write_text("Frage: Was ist Diversität?\nAntwort: Verschiedenheit.", encoding="utf-8")
        copy = self.root / "alter-hub"
        for name in ("launcher.py", "backend/main.py", "frontend/README.md", "docs/anleitung.md", "data/notiz.txt", "README.md"):
            (copy / name).parent.mkdir(parents=True, exist_ok=True)
            (copy / name).write_text("Programmdatei, kein Lernstoff", encoding="utf-8")
        # A folder that merely looks similar stays study material: all three marks are needed.
        partial = self.root / "kurs-mit-skript"
        (partial / "backend").mkdir(parents=True)
        (partial / "launcher.py").write_text("print(1)", encoding="utf-8")
        (partial / "backend" / "main.py").write_text("print(1)", encoding="utf-8")
        (partial / "mitschrift.md").write_text("Mitschrift zur Vorlesung", encoding="utf-8")
        project = self.root.parent / (self.root.name + "-programm")  # the running program lies outside the study folder
        self.assertEqual(sorted(row["path"] for row in scan_documents(self.root, project)),
                         ["1.semester/32281 Diversität/Session1/notes.txt", "kurs-mit-skript/mitschrift.md"])

    def test_missing_root_is_reported(self):
        with self.assertRaises(FileNotFoundError):
            scan_documents(self.root / "missing")

    def test_unreadable_subdirectory_aborts_incomplete_index(self):
        (self.root / "valid.txt").write_text("Valid source", encoding="utf-8")
        def incomplete_walk(top, followlinks, onerror):
            yield str(top), [], ["valid.txt"]
            onerror(PermissionError(13, "Permission denied", str(self.root / "private")))
        with patch("backend.documents.os.walk", incomplete_walk):
            with self.assertRaisesRegex(ValueError, "nicht vollständig gelesen"):
                scan_documents(self.root)


if __name__ == "__main__":
    unittest.main()
