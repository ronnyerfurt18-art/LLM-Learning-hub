"""Learning and persistence invariants, using isolated SQLite databases."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.core import Hub, grade, sm2, validate_import


def sample_question(kind="free_text", suffix=""):
    question = {
        "id": f"test-{kind}{suffix}", "unit": 1, "topic": "Diversität", "type": kind,
        "question": "Was bezeichnet Diversität?", "original_question": "Was bezeichnet Diversität?",
        "original_solution": "Diversität bezeichnet die Vielfalt von Menschen.",
        "model_answer": "Vielfalt von Menschen", "explanation": "Definition aus der Quelle.",
        "source": "test.txt", "source_page": 1, "difficulty": 1,
        "verified": False, "generated_by": "Test fixture", "keywords": ["Vielfalt", "Menschen"],
        "checklist": ["Vielfalt erklären", "Menschen nennen"],
    }
    if kind in {"single_choice", "multiple_choice"}:
        question.update(options=["Vielfalt", "Gleichheit", "Menschen"], correct_answers=[0] if kind == "single_choice" else [0, 2])
    elif kind == "matching":
        question["pairs"] = [{"term": "Diversität", "definition": "Vielfalt"}, {"term": "Inklusion", "definition": "Teilhabe"}]
    elif kind == "cloze":
        question.update(text="___ bezeichnet die Vielfalt von Menschen.", answers=["Diversität"], synonyms=[["Diversity"]])
    return question


def sample_import(types=None):
    types = types or ["single_choice", "multiple_choice", "matching", "cloze", "flashcard", "free_text", "case_analysis", "exam_question"]
    return {"schema_version": 1, "module": {"name": "Testmodul", "number": "99999", "unit_count": 1},
            "questions": [sample_question(kind) for kind in types], "originals": [], "coverage": []}


class SourceReferenceTests(unittest.TestCase):
    def test_video_references_survive_import_with_exact_time_ranges(self):
        content = sample_import(['free_text'])
        reference = {'kind': 'video', 'path': '12345 Modul/Session3/video1.mp4', 'title': 'Vorlesung', 'timestamp_seconds': 0, 'timestamp_end_seconds': 70.5}
        content['questions'][0]['theory_sources'] = [reference]
        self.assertEqual(validate_import(content), [])
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(Path(directory) / 'learning.sqlite3')
            hub.import_content(content)
            self.assertEqual(hub.questions()[0]['theory_sources'], [reference])

    def test_invalid_video_times_and_mixed_reference_types_are_rejected(self):
        reference = {'kind': 'video', 'path': '12345 Modul/video1.mp4', 'title': 'Vorlesung', 'timestamp_seconds': 12}
        invalid = [{**reference, 'timestamp_seconds': value} for value in (True, -1, float('nan'), float('inf'), '12')]
        invalid += [{**reference, 'timestamp_end_seconds': value} for value in (False, 11, float('nan'))]
        invalid += [{**reference, 'path': '12345 Modul/lehrbrief.pdf'}, {**reference, 'pdf_page': 2}, {**reference, 'kind': 'pdf'}, {**reference, 'kind': 'unknown'}]
        for ref in invalid:
            with self.subTest(ref=ref):
                content = sample_import(['free_text'])
                content['questions'][0]['theory_sources'] = [ref]
                self.assertTrue(validate_import(content))

    def test_theory_references_survive_import_without_replacing_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(Path(directory) / 'learning.sqlite3')
            content = sample_import(['free_text'])
            question = content['questions'][0]
            question['source_kind'] = 'course_material'
            question['theory_sources'] = [{'path': '12345 Modul/lehrbrief.pdf', 'title': 'Lehrbrief', 'pdf_page': 7, 'pdf_page_end': 9, 'printed_page': '1–3', 'chapter': '2.2'}]
            self.assertEqual(validate_import(content), [])
            hub.import_content(content)
            saved = hub.questions()[0]
            self.assertEqual(saved['source'], 'test.txt')
            self.assertEqual(saved['theory_sources'], question['theory_sources'])
            self.assertEqual(saved['source_kind'], 'course_material')

    def test_invalid_theory_references_cannot_be_imported_as_valid_sources(self):
        reference = {'path': '12345 Modul/lehrbrief.pdf', 'title': 'Lehrbrief', 'pdf_page': 7}
        invalid = [None, [], [{}], [{**reference, 'path': '../private.pdf'}], [{**reference, 'path': '/private.pdf'}], [{**reference, 'pdf_page': True}], [{**reference, 'pdf_page_end': 6}], [{**reference, 'printed_page': []}]]
        for refs in invalid:
            with self.subTest(refs=refs):
                content = sample_import(['free_text'])
                content['questions'][0]['theory_sources'] = refs
                self.assertTrue(validate_import(content))


class GradingTests(unittest.TestCase):
    def test_all_eight_types_have_appropriate_grading(self):
        answers = {"single_choice": [0], "multiple_choice": [2, 0],
                   "matching": {"Diversität": "Vielfalt", "Inklusion": "Teilhabe"},
                   "cloze": ["diversitat"], "flashcard": "",
                   "free_text": "Vielfalt der Menschen", "case_analysis": "Vielfalt der Menschen", "exam_question": "Vielfalt der Menschen"}
        for kind, answer in answers.items():
            with self.subTest(kind=kind):
                result = grade(sample_question(kind), answer, rating=4 if kind == "flashcard" else None)
                self.assertEqual(result["score"], 1)
                self.assertTrue(result["correct"])
                expected = "self" if kind == "flashcard" else "keyword_hint" if kind in {"free_text", "case_analysis", "exam_question"} else "automatic"
                self.assertEqual(result["grading"], expected)

    def test_multiple_choice_is_exact_set_not_partial_credit(self):
        question = sample_question("multiple_choice")
        self.assertEqual(grade(question, [0])["score"], 0)
        self.assertEqual(grade(question, [0, 1, 2])["score"], 0)

    def test_matching_partial_credit_and_cloze_typo_synonym(self):
        self.assertEqual(grade(sample_question("matching"), {"Diversität": "Vielfalt"})["score"], .5)
        self.assertEqual(grade(sample_question("cloze"), ["Diversitätt"])["score"], 1)
        self.assertEqual(grade(sample_question("cloze"), ["Diversity"])["score"], 1)
        self.assertEqual(grade(sample_question("cloze"), ["Inklusion"])["score"], 0)

    def test_open_answers_return_keyword_evidence_and_allow_manual_override(self):
        result = grade(sample_question(), "Vielfalt")
        self.assertEqual(result["score"], .5)
        self.assertEqual(result["matched_keywords"], ["Vielfalt"])
        self.assertEqual(result["missing_keywords"], ["Menschen"])
        self.assertEqual(grade(sample_question(), "Umschreibung", manual_score=1)["grading"], "self")
        for bad in (-1, 2, True, "1"):
            with self.assertRaises(ValueError):
                grade(sample_question(), "Antwort", manual_score=bad)

    def test_flashcard_requires_rating(self):
        with self.assertRaises(ValueError):
            grade(sample_question("flashcard"), "")
        self.assertEqual(grade(sample_question("flashcard"), "", rating=0)["score"], 0)


class RepetitionTests(unittest.TestCase):
    def test_sm2_success_intervals_and_failure_reset(self):
        at = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
        first = sm2({}, 4, at)
        self.assertEqual(first["interval"], 1)
        self.assertEqual(datetime.fromisoformat(first["next_due"]), at + timedelta(days=1))
        second = sm2(first, 4, at)
        third = sm2(second, 5, at)
        self.assertEqual(second["interval"], 6)
        self.assertGreater(third["interval"], second["interval"])
        failure = sm2(third, 0, at)
        self.assertEqual(failure["repetitions"], 0)
        self.assertEqual(failure["mastery"], 0)
        self.assertEqual(datetime.fromisoformat(failure["next_due"]), at + timedelta(minutes=10))

    def test_ease_has_lower_bound(self):
        state = {}
        for _ in range(20):
            state = sm2(state, 0)
        self.assertGreaterEqual(state["ease"], 1.3)


class HubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "learning.sqlite3"
        self.hub = Hub(self.path)
        self.content = sample_import()
        self.imported = self.hub.import_content(self.content)

    def test_import_is_idempotent_and_original_sources_immutable(self):
        self.assertEqual(self.imported["imported"], 8)
        self.content["questions"][0]["model_answer"] = "Changed answer"
        self.assertEqual(self.hub.import_content(self.content)["imported"], 0)
        self.assertEqual(self.hub.question("test-single_choice")["model_answer"], "Vielfalt von Menschen")
        other = copy.deepcopy(self.content)
        other["module"] = {"name": "Anderes Modul", "number": "88888"}
        with self.assertRaises(ValueError):
            self.hub.import_content(other)

    def test_progress_and_attempts_survive_reopening_database(self):
        self.hub.attempt("test-single_choice", [0])
        self.hub.attempt("test-single_choice", [1])
        reopened = Hub(self.path)
        progress = reopened.progress("test-single_choice")
        self.assertEqual((progress["attempts"], progress["correct"], progress["incorrect"]), (2, 1, 1))
        self.assertEqual(len(reopened.export()["attempts"]), 2)

    def test_progress_chart_counts_distinct_questions_not_repeat_attempts(self):
        first = self.hub.attempt('test-single_choice', [0])
        second = self.hub.attempt('test-single_choice', [1])
        third = self.hub.attempt('test-multiple_choice', [0, 2])
        with self.hub.db() as db:
            db.execute('UPDATE attempts SET created_at=? WHERE id=?', ('2026-10-10T10:00:00+00:00', first['id']))
            for attempt in (second, third):
                db.execute('UPDATE attempts SET created_at=? WHERE id=?', ('2026-10-11T10:00:00+00:00', attempt['id']))
        self.assertEqual(self.hub.stats()['progress_history'], [{'date': '2026-10-10', 'studied': 1}, {'date': '2026-10-11', 'studied': 2}])

    def test_configured_units_remain_accessible_before_questions_are_imported(self):
        mid = self.imported['module_id']
        self.hub.patch_module(mid, {'unit_count': 3})
        self.assertEqual(self.hub.module(mid)['units'], [1, 2, 3])

    def test_manual_correction_replays_later_attempts_without_duplication(self):
        first = self.hub.attempt("test-free_text", "Umschreibung")
        self.hub.attempt("test-free_text", "Vielfalt der Menschen")
        self.hub.correct_attempt(first["id"], 1, 5)
        progress = self.hub.progress("test-free_text")
        self.assertEqual((progress["attempts"], progress["correct"], progress["incorrect"]), (2, 2, 0))
        self.assertEqual(progress["repetitions"], 2)
        self.hub.correct_attempt(first["id"], 1, 5)
        self.assertEqual(len(self.hub.export()["attempts"]), 2)

    def test_exam_hides_solutions_and_submits_once(self):
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 8, "duration_minutes": 10})
        self.assertEqual(exam["count"], 7)
        for question in exam["questions"]:
            for key in ("model_answer", "original_solution", "correct_answers", "pairs", "answers", "explanation", "keywords"):
                self.assertNotIn(key, question)
            self.assertNotEqual(question["type"], "flashcard")
        saved = self.hub.update_exam(exam["id"], {"test-single_choice": [0]}, 1)
        self.assertEqual(saved["answers"]["test-single_choice"], [0])
        submitted = self.hub.submit_exam(exam["id"])
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(len(submitted["results"]), 7)
        self.hub.submit_exam(exam["id"])
        self.assertEqual(len(self.hub.export()["attempts"]), 7)

    def test_active_exam_does_not_expose_original_definition_answer(self):
        content = sample_import(["cloze"])
        content["questions"][0]["id"] = "definition-cloze"
        content["questions"][0]["original_question"] = "Diversität bezeichnet die Vielfalt von Menschen."
        self.hub.import_content(content)
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 2, "types": ["cloze"], "duration_minutes": 10})
        for question in exam["questions"]:
            self.assertNotIn("original_question", question)

    def test_deadline_auto_submits_saved_answers_and_ignores_late_changes(self):
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 1, "types": ["single_choice"], "duration_minutes": 1})
        self.hub.update_exam(exam["id"], {"test-single_choice": [0]})
        raw = self.hub.raw_exam(exam["id"])
        raw["deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.hub.save_exam(raw)
        submitted = self.hub.submit_exam(exam["id"], {"test-single_choice": [1]})
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(submitted["score"], 1)
        self.assertEqual(len(self.hub.export()["attempts"]), 1)

    def test_exam_invalid_answer_does_not_partially_create_attempts(self):
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 2, "types": ["single_choice", "multiple_choice"], "duration_minutes": 10})
        raw = self.hub.raw_exam(exam["id"])
        raw["question_ids"] = ["test-single_choice", "test-multiple_choice"]
        self.hub.save_exam(raw)
        with self.assertRaises(ValueError):
            self.hub.submit_exam(exam["id"], {"test-single_choice": [0], "test-multiple_choice": "Invalid response shape"})
        self.assertEqual(self.hub.raw_exam(exam["id"])["status"], "active")
        self.assertEqual(len(self.hub.export()["attempts"]), 0)

    def test_manual_exam_grade_updates_exam_statistics(self):
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 1, "types": ["free_text"], "duration_minutes": 10})
        submitted = self.hub.submit_exam(exam["id"], {"test-free_text": "Umschreibung"})
        self.assertEqual(submitted["score"], 0)
        reviewed = self.hub.grade_exam(exam["id"], "test-free_text", 1)
        self.assertEqual(reviewed["score"], 1)
        self.assertEqual(reviewed["results"][0]["grading"], "self")
        self.assertEqual(self.hub.stats()["exams"][0]["percentage"], 100)

    def test_autosave_rejects_malformed_answer_before_deadline(self):
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 1, "types": ["single_choice"], "duration_minutes": 10})
        with self.assertRaises(ValueError):
            self.hub.update_exam(exam["id"], {"test-single_choice": "Invalid response shape"})
        self.assertEqual(self.hub.raw_exam(exam["id"])["answers"], {})

    def test_expired_exam_with_corrupt_saved_answer_still_submits(self):
        exam = self.hub.create_exam({"module_id": self.imported["module_id"], "count": 1, "types": ["single_choice"], "duration_minutes": 10})
        raw = self.hub.raw_exam(exam["id"])
        raw["answers"] = {"test-single_choice": "Invalid legacy response shape"}
        raw["deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.hub.save_exam(raw)
        submitted = self.hub.exam(exam["id"])
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(submitted["score"], 0)
        self.assertEqual(len(self.hub.export()["attempts"]), 1)

    def test_original_id_cannot_silently_collide_across_modules(self):
        content = sample_import(["free_text"])
        content["originals"] = [{"id": "original-001", "unit": 1, "topic": "Diversität",
                                 "source": "test.txt", "original_question": "Was ist Diversität?",
                                 "original_solution": "Vielfalt der Menschen."}]
        self.hub.import_content(content)
        other = copy.deepcopy(content)
        other["module"] = {"name": "Zweites Modul", "number": "88888"}
        other["questions"][0]["id"] = "other-free-text"
        other["originals"][0]["original_solution"] = "Abweichende ursprüngliche Lösung"
        with self.assertRaises(ValueError):
            self.hub.import_content(other)
        self.assertEqual(len([q for q in self.hub.questions() if q["id"] == "other-free-text"]), 0)


class ImportBoundaryTests(unittest.TestCase):
    def test_matching_normalized_terms_and_definitions_are_unambiguous(self):
        for pairs in (
            [{"term": "Diversität", "definition": "Vielfalt"}, {"term": "DIVERSITÄT ", "definition": "Andere Definition"}],
            [{"term": "Diversität", "definition": "Vielfalt der Menschen"}, {"term": "Diversity", "definition": " VIELFALT  der Menschen "}],
        ):
            content = sample_import(["matching"])
            content["questions"][0]["pairs"] = pairs
            with self.subTest(pairs=pairs):
                self.assertTrue(validate_import(content))

    def test_malformed_optional_fields_return_errors(self):
        variants = []
        for name, value in (("coverage", None), ("coverage", 12), ("originals", None), ("originals", ["bad-original"])):
            content = sample_import(["free_text"])
            content[name] = value
            variants.append((name, content))
        for name, content in variants:
            with self.subTest(name=name, value=content[name]):
                self.assertTrue(validate_import(content))

    def test_malformed_question_payloads_return_errors(self):
        variants = [("free_text", "type", []), ("matching", "pairs", [{"term": [], "definition": "Definition"}, {"term": "B", "definition": "Other"}]),
                    ("free_text", "keywords", 7), ("cloze", "synonyms", 7)]
        for kind, key, value in variants:
            content = sample_import([kind])
            content["questions"][0][key] = value
            with self.subTest(kind=kind, key=key):
                self.assertTrue(validate_import(content))


if __name__ == "__main__":
    unittest.main()
