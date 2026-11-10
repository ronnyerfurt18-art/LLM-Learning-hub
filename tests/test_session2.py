"""Sessions stay distinct in dashboard progress, imports and coverage hints."""
import copy
import base64
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core import Hub, TYPES, validate_import
from backend.main import create_app
from tests.test_core import sample_import
from tests.seedlist import write_seed_list


def unit_import(unit):
    content = sample_import(["single_choice", "flashcard"])
    content["module"]["unit_count"] = 2
    for question in content["questions"]:
        question.update(id=f"unit-{unit}-" + question["id"], unit=unit, topic="Gemeinsamer Begriff",
                        keywords=["Alpha"] if unit == 1 else ["Beta"])
    content["originals"] = [{"id": f"unit-{unit}-original", "unit": unit, "topic": "Gemeinsamer Begriff",
                             "source": f"unit{unit}.txt", "original_question": "Die unveränderte Originalfrage.",
                             "original_solution": f"Die unveränderte Lösung aus Einheit {unit}."}]
    content["coverage"] = [{"unit": unit, "topic": "Gemeinsamer Begriff", "coverage": "complete" if unit == 1 else "missing",
                            "method": "gpt_work", "notes": f"Inhaltlicher Vergleich für Einheit {unit}.",
                            "source": f"unit{unit}.txt", "summary_source": f"summary{unit}.md", "verified": False}]
    return content


class UnitProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "learning.sqlite3"
        self.hub = Hub(self.path)
        self.first, self.second = unit_import(1), unit_import(2)
        self.module_id = self.hub.import_content(self.first)["module_id"]

    def test_unit_summaries_have_real_counts_and_independent_progress(self):
        self.hub.attempt("unit-1-test-single_choice", [0])
        self.hub.import_content(self.second)
        self.hub.attempt("unit-2-test-flashcard", "", rating=0)
        summary = self.hub.module(self.module_id)
        units = {row["unit"]: row for row in summary["unit_summaries"]}
        self.assertEqual(set(units), {1, 2})
        self.assertEqual(units[1]["question_count"], 2)
        self.assertEqual(units[2]["question_count"], 2)
        self.assertEqual(units[1]["studied_count"], 1)
        self.assertEqual(units[2]["studied_count"], 1)
        self.assertEqual(units[1]["progress"], 50)
        self.assertEqual(units[2]["progress"], 50)
        self.assertEqual(units[1]["success_rate"], 100)
        self.assertEqual(units[2]["success_rate"], 0)
        self.assertEqual(units[1]["topics"], ["Gemeinsamer Begriff"])
        self.assertEqual(units[2]["topics"], ["Gemeinsamer Begriff"])
        self.assertEqual(summary["question_count"], 4)
        self.assertEqual(sum(row["studied_count"] for row in units.values()), summary["studied_count"])

    def test_unit2_import_replay_preserves_unit1_progress_and_sources(self):
        first_attempt = self.hub.attempt("unit-1-test-single_choice", [0])
        before = copy.deepcopy(self.hub.progress("unit-1-test-single_choice"))
        self.assertEqual(self.hub.import_content(self.second)["imported"], 2)
        self.assertEqual(self.hub.import_content(self.second)["imported"], 0)
        self.assertEqual(self.hub.import_content(self.first)["imported"], 0)
        reopened = Hub(self.path)
        self.assertEqual(reopened.progress("unit-1-test-single_choice"), before)
        exported = reopened.export()
        self.assertEqual(len(exported["questions"]), 4)
        self.assertEqual(len(exported["attempts"]), 1)
        self.assertEqual(exported["attempts"][0]["id"], first_attempt["id"])
        originals = {row["id"]: json.loads(row["payload"]) for row in exported["originals"]}
        self.assertEqual(originals["unit-1-original"], self.first["originals"][0])
        self.assertEqual(originals["unit-2-original"], self.second["originals"][0])
        self.assertEqual({row["unit"] for row in reopened.coverage(self.module_id)}, {1, 2})

    def test_active_exam_keeps_question_diagram_but_hides_solution_diagram(self):
        content = sample_import(["exam_question"])
        question = content["questions"][0]
        question.update(id="unit-2-diagram-question", unit=2,
                        original_question_images=[{"path": "assets/einheit2/question.png", "caption": "Fragendiagramm", "source_page": 8}],
                        original_solution_images=[{"path": "assets/einheit2/solution.png", "caption": "Lösungsdiagramm", "source_page": 9}])
        self.hub.import_content(content)
        exam = self.hub.create_exam({"module_id": self.module_id, "units": [2], "types": ["exam_question"], "count": 1, "duration_minutes": 10})
        public = exam["questions"][0]
        self.assertEqual(public["original_question_images"], question["original_question_images"])
        self.assertNotIn("original_solution_images", public)
        self.assertNotIn("solution.png", json.dumps(exam))
        submitted = self.hub.submit_exam(exam["id"])
        self.assertEqual(submitted["results"][0]["question"]["original_solution_images"], question["original_solution_images"])


class UnitCoverageApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "master-learning-hub"
        self.project.mkdir()
        first_dir = self.root / "99999 Testmodul" / "Session1"
        first_dir.mkdir(parents=True)
        # Unit1 happens to mention Beta. It must not cover a Unit2 exercise.
        (first_dir / "zusammenfassung.md").write_text("Alpha und Beta werden hier erwähnt.", encoding="utf-8")
        self.app = create_app(self.root, self.project / "data", self.project, start_watch=False)
        self.client = TestClient(self.app, base_url="http://127.0.0.1")
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        first = self.client.post("/api/import/confirm", json={"content": unit_import(1)})
        second = self.client.post("/api/import/confirm", json={"content": unit_import(2)})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.module_id = first.json()["module_id"]

    def test_dashboard_exposes_both_populated_unit_summaries(self):
        dashboard = self.client.get("/api/dashboard").json()
        module = next(row for row in dashboard["modules"] if row["id"] == self.module_id)
        summaries = {row["unit"]: row for row in module["unit_summaries"]}
        self.assertEqual(summaries[1]["question_count"], 2)
        self.assertEqual(summaries[2]["question_count"], 2)
        self.assertEqual(len(self.client.get("/api/questions", params={"module_id": self.module_id, "unit": 2}).json()), 2)

    def test_startup_marks_an_already_indexed_authorized_package_imported(self):
        imports = self.project / 'imports'
        write_seed_list(self.project)
        path = imports / 'digitale_diversitaet_einheit2.json'
        path.write_text(json.dumps(unit_import(2), ensure_ascii=False), encoding='utf-8')
        self.client.post('/api/scan', json={})
        document = next(d for d in self.client.get('/api/documents').json() if d['path'].startswith('@imports/'))
        self.assertEqual(document['status'], 'pending')
        restarted = create_app(self.root, self.project / 'data', self.project, start_watch=False)
        with TestClient(restarted, base_url='http://127.0.0.1') as client:
            document = next(d for d in client.get('/api/documents').json() if d['path'].startswith('@imports/'))
            self.assertEqual(document['status'], 'imported')
            self.assertEqual(client.get('/api/health').json()['question_count'], 4)

    def test_same_topic_in_two_units_keeps_coverage_and_summary_scope_separate(self):
        response = self.client.post("/api/coverage/analyze", json={"module_id": self.module_id})
        self.assertEqual(response.status_code, 200)
        hints = {row["unit"]: row for row in response.json() if row["method"] == "keyword"}
        self.assertEqual(set(hints), {1, 2})
        self.assertEqual(hints[1]["coverage"], "partial")
        self.assertEqual(hints[2]["coverage"], "missing")
        self.assertEqual(hints[1]["keywords"], ["Alpha"])
        self.assertEqual(hints[2]["keywords"], ["Beta"])
        self.assertIn(":1:", hints[1]["id"])
        self.assertIn(":2:", hints[2]["id"])
        self.assertNotEqual(hints[1]["id"], hints[2]["id"])
        self.assertNotIn("Session1", hints[2]["summary_source"])
        assessed = [row for row in response.json() if row["method"] == "gpt_work"]
        self.assertEqual(len(assessed), 2)
        self.assertEqual({row["unit"] for row in assessed}, {1, 2})
        scoped = self.client.get("/api/coverage", params={"module_id": self.module_id, "unit": 2}).json()
        self.assertEqual(len(scoped), 2)
        self.assertTrue(all(row["unit"] == 2 for row in scoped))

    def test_local_image_asset_is_served_and_escape_paths_are_rejected(self):
        assets = self.project / "imports" / "assets" / "einheit2"
        assets.mkdir(parents=True)
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=")
        (assets / "question.png").write_bytes(png)
        response = self.client.get("/api/assets/assets/einheit2/question.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, png)
        self.assertTrue(response.headers["content-type"].startswith("image/png"))
        secret = self.project / "imports" / "private.png"
        secret.write_bytes(png)
        self.assertEqual(self.client.get("/api/assets/assets/einheit2/%2e%2e/%2e%2e/private.png").status_code, 403)
        self.assertEqual(self.client.get("/api/assets/%2Fprivate%2Ftmp%2Fnot-a-learning-image.png").status_code, 403)
        (assets / "private.png").symlink_to(secret)
        self.assertEqual(self.client.get("/api/assets/assets/einheit2/private.png").status_code, 403)
        (assets / "instructions.txt").write_text("Non-image source", encoding="utf-8")
        self.assertEqual(self.client.get("/api/assets/assets/einheit2/instructions.txt").status_code, 403)
        self.assertEqual(self.client.get("/api/assets/assets/einheit2/missing.png").status_code, 404)

    def test_image_root_symlink_cannot_expose_external_folder(self):
        outside = self.root / "external-assets"
        outside.mkdir()
        (outside / "private.png").write_bytes(b"\x89PNG\r\n\x1a\nprivate")
        imports = self.project / "imports"
        imports.mkdir(exist_ok=True)
        (imports / "assets").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.client.get("/api/assets/assets/private.png").status_code, 403)

    def test_api_active_exam_only_exposes_question_image(self):
        content = sample_import(["exam_question"])
        question = content["questions"][0]
        question.update(id="unit-2-api-diagram", unit=2,
                        original_question_images=[{"path": "assets/einheit2/question.png", "caption": "Fragendiagramm", "source_page": 8}],
                        original_solution_images=[{"path": "assets/einheit2/solution.png", "caption": "Lösungsdiagramm", "source_page": 9}])
        response = self.client.post("/api/import/confirm", json={"content": content})
        self.assertEqual(response.status_code, 200, response.text)
        exam = self.client.post("/api/exams", json={"module_id": self.module_id, "units": [2], "types": ["exam_question"], "count": 1, "duration_minutes": 10}).json()
        self.assertEqual(exam["questions"][0]["original_question_images"], question["original_question_images"])
        self.assertNotIn("original_solution_images", exam["questions"][0])
        self.assertNotIn("solution.png", json.dumps(exam))
        submitted = self.client.post(f"/api/exams/{exam['id']}/submit", json={}).json()
        self.assertEqual(submitted["results"][0]["question"]["original_solution_images"], question["original_solution_images"])


if __name__ == "__main__":
    unittest.main()
