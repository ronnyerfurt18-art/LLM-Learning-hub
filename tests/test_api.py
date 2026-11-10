"""Local API workflows with disposable source, project and database directories."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.test_core import sample_import
from tests.seedlist import write_seed_list


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "study"
        self.project = self.source / "master-learning-hub"
        self.source.mkdir()
        self.project.mkdir()
        write_seed_list(self.project)
        self.app = create_app(self.source, self.project / "data", self.project, start_watch=False)
        self.client = TestClient(self.app, base_url="http://127.0.0.1", raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def import_questions(self):
        response = self.client.post("/api/import/confirm", json={"content": sample_import()})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_document_assignment_without_proposals_survives_source_change(self):
        folder = self.source / '12345 Ursprüngliches Modul'
        folder.mkdir()
        path = folder / 'Session1.txt'
        path.write_text('Ein Text ohne eindeutige Fragen oder Definitionen.', encoding='utf-8')
        self.client.post('/api/scan', json={})
        document = self.client.get('/api/documents').json()[0]
        self.assertEqual(document['proposal_count'], 0)
        module = self.client.post('/api/modules', json={'name': 'Manuell zugeordnet', 'unit_count': 1}).json()
        response = self.client.patch(f"/api/documents/{document['id']}", json={'module_id': module['id'], 'unit': 3})
        self.assertEqual(response.status_code, 200, response.text)
        path.write_text('Der Text hat sich geändert und bleibt ohne sichere Frage.', encoding='utf-8')
        self.client.post('/api/scan', json={})
        updated = self.client.get(f"/api/documents/{document['id']}").json()
        self.assertEqual((updated['module_id'], updated['unit']), (module['id'], 3))
        modules = self.client.get('/api/modules').json()
        self.assertEqual(next(m for m in modules if m['id'] == module['id'])['unit_count'], 3)
        self.client.patch(f"/api/modules/{module['id']}", json={'unit_count': 1})
        scan = self.client.post('/api/scan', json={}).json()
        self.assertEqual(scan['changed'], 0)
        modules = self.client.get('/api/modules').json()
        self.assertEqual(next(m for m in modules if m['id'] == module['id'])['unit_count'], 3)


    def test_local_only_host_origin_and_fetch_site(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/health", headers={"host": "malicious.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/scan", json={}, headers={"origin": "https://malicious.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/scan", json={}, headers={"sec-fetch-site": "cross-site"}).status_code, 403)
        self.assertEqual(self.client.post("/api/scan", json={}, headers={"origin": "http://127.0.0.1"}).status_code, 200)

    def test_import_preview_confirmation_and_idempotence(self):
        content = sample_import()
        preview = self.client.post("/api/import/preview", json={"content": content})
        self.assertTrue(preview.json()["valid"])
        self.assertEqual(self.client.get("/api/health").json()["question_count"], 0)
        result = self.import_questions()
        self.assertEqual(result["imported"], 8)
        again = self.client.post("/api/import/confirm", json={"content": content})
        self.assertEqual(again.json()["imported"], 0)
        self.assertEqual(len(self.client.get("/api/questions").json()), 8)

    def test_invalid_json_and_import_shape_have_clear_errors(self):
        malformed = self.client.post("/api/import/preview", content="{bad-json", headers={"content-type": "application/json"})
        self.assertEqual(malformed.status_code, 422)
        response = self.client.post("/api/import/preview", json={"content": []})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["valid"])
        for change in (("type", []), ("keywords", 7)):
            content = sample_import(["free_text"])
            content["questions"][0][change[0]] = change[1]
            invalid = self.client.post("/api/import/preview", json={"content": content})
            self.assertEqual(invalid.status_code, 200, invalid.text)
            self.assertFalse(invalid.json()["valid"])

    def test_document_proposals_require_confirmation_and_deleted_sources_are_missing(self):
        directory = self.source / "99999 Testmodul" / "Session1"
        directory.mkdir(parents=True)
        original = directory / "notes.txt"
        text = "Frage: Was ist Diversität?\nAntwort: Vielfalt der Menschen."
        original.write_text(text, encoding="utf-8")
        summary = self.client.post("/api/scan", json={}).json()
        self.assertEqual(summary["new"], 1)
        doc = self.client.get("/api/documents").json()[0]
        self.assertEqual(doc["status"], "pending")
        self.assertEqual(doc["proposal_count"], 1)
        self.assertEqual(self.client.get("/api/health").json()["question_count"], 0)
        detail = self.client.get(f"/api/documents/{doc['id']}").json()
        self.assertEqual(detail["text"], text)
        result = self.client.post(f"/api/documents/{doc['id']}/confirm", json={"module_id": doc["module_id"], "unit": 1, "questions": detail["proposals"]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["imported"], 1)
        original.unlink()
        self.client.post("/api/scan", json={})
        self.assertEqual(self.client.get(f"/api/documents/{doc['id']}").json()["status"], "missing")
        self.assertEqual(self.client.get("/api/health").json()["question_count"], 1)

    def test_new_manual_module_maps_previously_unassigned_document(self):
        directory = self.source / "Manuelles Modul" / "Session1"
        directory.mkdir(parents=True)
        (directory / "notes.txt").write_text("Frage: Warum?\nAntwort: Weil dies die Musterlösung ist.", encoding="utf-8")
        self.client.post("/api/scan", json={})
        self.assertIsNone(self.client.get("/api/documents").json()[0]["module_id"])
        module = self.client.post("/api/modules", json={"name": "Manuelles Modul", "directory": "Manuelles Modul", "unit_count": 1}).json()
        self.client.post("/api/scan", json={})
        doc = self.client.get("/api/documents").json()[0]
        self.assertEqual(doc["module_id"], module["id"])
        self.assertEqual(doc["proposal_count"], 1)

    def test_patch_directory_maps_previously_unassigned_cached_document(self):
        directory = self.source / "Manuelles Modul" / "Session1"
        directory.mkdir(parents=True)
        (directory / "notes.txt").write_text("Frage: Warum?\nAntwort: Weil dies die Musterlösung ist.", encoding="utf-8")
        self.client.post("/api/scan", json={})
        module = self.client.post("/api/modules", json={"name": "Manuelles Modul", "unit_count": 1}).json()
        self.client.patch(f"/api/modules/{module['id']}", json={"directory": "Manuelles Modul"})
        self.client.post("/api/scan", json={})
        doc = self.client.get("/api/documents").json()[0]
        self.assertEqual(doc["module_id"], module["id"])
        self.assertEqual(doc["proposal_count"], 1)

    def test_import_watcher_rejects_malformed_and_keeps_valid_import_pending(self):
        content = sample_import(["free_text"])
        (self.project / "imports" / "new-content.json").write_text(json.dumps(content), encoding="utf-8")
        (self.project / "imports" / "bad-content.json").write_text("{broken", encoding="utf-8")
        self.client.post("/api/scan", json={})
        documents = {row["path"]: row for row in self.client.get("/api/documents").json()}
        self.assertEqual(documents["@imports/new-content.json"]["status"], "pending")
        self.assertEqual(documents["@imports/bad-content.json"]["status"], "error")
        self.assertEqual(self.client.get("/api/health").json()["question_count"], 0)
        invalid_scan = self.client.post("/api/scan", json={}).json()
        self.assertEqual(invalid_scan["errors"], 1)

    def test_watched_import_preview_selection_keeps_originals_and_coverage(self):
        content = sample_import(["free_text", "single_choice"])
        content["module"] = {"name": "Importiertes Modul", "number": "77777", "unit_count": 1}
        content["originals"] = [{"id": "import-original-001", "unit": 1, "topic": "Diversität",
                                 "source": "test.txt", "source_page": 1,
                                 "original_question": "Was bezeichnet Diversität?",
                                 "original_solution": "Diversität bezeichnet die Vielfalt von Menschen."}]
        content["coverage"] = [{"topic": "Diversität", "coverage": "partial", "method": "gpt_work",
                                "notes": "Die Erläuterung ist noch unvollständig.", "source": "test.txt",
                                "summary_source": "summary.md", "keywords": ["Vielfalt"], "verified": False}]
        path = self.project / "imports" / "reviewable-content.json"
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        self.client.post("/api/scan", json={})
        listing = self.client.get("/api/documents").json()
        doc = next(row for row in listing if row["path"] == "@imports/reviewable-content.json")
        self.assertNotIn("import_content", doc)
        self.assertNotIn("proposals", doc)
        self.assertEqual(self.client.get("/api/health").json()["question_count"], 0)
        detail = self.client.get(f"/api/documents/{doc['id']}").json()
        selected = {**detail["proposals"][0], "question": "Vor dem Import bearbeitete Übungsfrage."}
        response = self.client.post(f"/api/documents/{doc['id']}/confirm", json={
            "module_id": "__import_module__", "unit": 1, "questions": [selected]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["imported"], 1)
        module_id = response.json()["module_id"]
        modules = self.client.get("/api/modules").json()
        self.assertEqual(next(row for row in modules if row["id"] == module_id)["name"], "Importiertes Modul")
        questions = self.client.get("/api/questions").json()
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["question"], selected["question"])
        exported = self.client.get("/api/export").json()
        self.assertEqual(len(exported["originals"]), 1)
        self.assertEqual(json.loads(exported["originals"][0]["payload"]), content["originals"][0])
        self.assertEqual(exported["originals"][0]["module_id"], module_id)
        coverage = self.client.get("/api/coverage", params={"module_id": module_id}).json()
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0]["method"], "gpt_work")
        self.assertEqual(coverage[0]["notes"], content["coverage"][0]["notes"])
        after = next(row for row in self.client.get("/api/documents").json() if row["id"] == doc["id"])
        self.assertEqual(after["status"], "imported")
        self.assertNotIn("import_content", after)

    def test_attempt_manual_review_and_exam_persistence(self):
        result = self.import_questions()
        attempt = self.client.post("/api/attempts", json={"question_id": "test-free_text", "answer": "Umschreibung"}).json()
        corrected = self.client.patch(f"/api/attempts/{attempt['id']}", json={"manual_score": 1, "rating": 5})
        self.assertEqual(corrected.json()["grading"], "self")
        self.assertEqual(corrected.json()["question"]["progress"]["attempts"], 1)
        exam = self.client.post("/api/exams", json={"module_id": result["module_id"], "types": ["single_choice"], "count": 1, "duration_minutes": 5}).json()
        saved = self.client.patch(f"/api/exams/{exam['id']}", json={"answers": {"test-single_choice": [0]}, "current_index": 0})
        self.assertEqual(saved.status_code, 200)
        restored = self.client.get(f"/api/exams/{exam['id']}").json()
        self.assertEqual(restored["answers"]["test-single_choice"], [0])
        submitted = self.client.post(f"/api/exams/{exam['id']}/submit", json={}).json()
        self.assertEqual(submitted["percentage"], 100)
        self.client.post(f"/api/exams/{exam['id']}/submit", json={})
        exported = self.client.get("/api/export").json()
        self.assertEqual(len(exported["attempts"]), 2)

    def test_sqlite_backup_contains_questions_and_progress(self):
        self.import_questions()
        self.client.post("/api/attempts", json={"question_id": "test-single_choice", "answer": [0]})
        response = self.client.get("/api/backup")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"SQLite format 3\x00"))
        path = self.root / "backup.sqlite3"
        path.write_bytes(response.content)
        with sqlite3.connect(path) as database:
            self.assertEqual(database.execute("SELECT count(*) FROM questions").fetchone()[0], 8)
            self.assertEqual(database.execute("SELECT sum(attempts) FROM progress").fetchone()[0], 1)

    def test_module_directory_outside_source_is_rejected(self):
        response = self.client.post("/api/modules", json={"name": "External module", "directory": str(self.root.parent)})
        self.assertEqual(response.status_code, 400)

    def test_module_bad_field_types_return_user_errors(self):
        for value in ({"name": None}, {"name": 4}, {"name": "Modul", "directory": 4}):
            with self.subTest(value=value):
                self.assertEqual(self.client.post("/api/modules", json=value).status_code, 400)
        module = self.client.post("/api/modules", json={"name": "Modul"}).json()
        for value in ({"name": None}, {"exam_date": 4}):
            with self.subTest(value=value):
                self.assertEqual(self.client.patch(f"/api/modules/{module['id']}", json=value).status_code, 400)

    def test_initial_seed_import_and_progress_survive_restart_without_duplicates(self):
        seed = Path(__file__).resolve().parents[1] / "demo" / "imports" / "lernen_lernen_einheit1.json"
        write_seed_list(self.project, [seed.name])
        content = json.loads(seed.read_text(encoding="utf-8"))
        (self.project / "imports" / seed.name).write_bytes(seed.read_bytes())
        with TestClient(create_app(self.source, self.project / "data", self.project, start_watch=False), base_url="http://127.0.0.1") as first:
            self.assertEqual(first.get("/api/health").json()["question_count"], len(content["questions"]))
            card = next(q for q in content["questions"] if q["type"] == "flashcard")
            result = first.post("/api/attempts", json={"question_id": card["id"], "answer": "", "rating": 4})
            self.assertEqual(result.status_code, 200)
            before = first.get("/api/export").json()
        with TestClient(create_app(self.source, self.project / "data", self.project, start_watch=False), base_url="http://127.0.0.1") as reopened:
            after = reopened.get("/api/export").json()
            self.assertEqual(len(after["questions"]), len(content["questions"]))
            self.assertEqual(len(after["originals"]), len(content["originals"]))
            self.assertEqual(len(after["attempts"]), 1)
            self.assertEqual(after["progress"], before["progress"])


if __name__ == "__main__":
    unittest.main()
