"""The shipped demo module installs into an empty hub and passes every content check."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core import validate_import
from backend.main import create_app
from tools.install_demo import install

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'demo'


class DemoModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name) / 'Studium'
        self.project = Path(self.temp.name) / 'hub'
        self.project.mkdir()

    def client(self):
        return TestClient(create_app(self.study, self.project / 'data', self.project, start_watch=False), base_url='http://127.0.0.1')

    def test_installed_demo_offers_every_feature_without_errors(self):
        copied, skipped, merged, study = install(self.project, self.study)
        self.assertEqual((len(copied), skipped, sorted(merged), study), (7, [], ['content/tutor/goals.json', 'imports/seed.json'], self.study.resolve()))
        questions = [q for unit in (1, 2) for q in json.loads((DEMO / f'imports/lernen_lernen_einheit{unit}.json').read_text())['questions']]
        with self.client() as client:
            module = client.get('/api/modules').json()
            self.assertEqual([(m['id'], m['name'], m['question_count'], m['unit_count'], m['has_assignments']) for m in module],
                             [('M-10001', 'Lernen lernen (Demo)', len(questions), 2, True)])
            pages = client.get('/api/learning-pages/M-10001')
            self.assertEqual(pages.status_code, 200, pages.text)
            bundle = pages.json()
            self.assertEqual(([lesson['unit'] for lesson in bundle['lessons']], len(bundle['overview']['big_picture']['nodes'])), ([1, 1, 2, 2], 4))
            # Every exercise linked from a learning page exists in the question packages.
            linked = {qid for lesson in bundle['lessons'] for qid in lesson['exercise_ids']}
            self.assertEqual(linked, {q['id'] for q in questions})
            assignments = client.get('/api/assignments/M-10001')
            self.assertEqual(assignments.status_code, 200, assignments.text)
            self.assertEqual([len(q['options']) for q in assignments.json()['assignments'][0]['questions']], [4, 4, 4])
            memory = client.get('/api/tutor/learning-memory', params={'module_id': 'M-10001'}).json()
            self.assertEqual((len(memory['goals']), memory['coverage']), (3, '3 Lernziele sind für dieses Modul erfasst. Andere Themen sind noch nicht erfasst.'))
            documents = {d['name']: d for d in client.get('/api/documents').json() if not d['path'].startswith('@imports/')}
            self.assertEqual({name: (d['module_id'], d['unit'], d['status']) for name, d in documents.items()},
                             {'10001-01-S#1-demo.pdf': ('M-10001', 1, 'imported'), '10001-02-S#1-demo.pdf': ('M-10001', 2, 'imported'),
                              '10001-uebungsarbeit-1-demo.pdf': ('M-10001', None, 'pending')})
            self.assertEqual(client.get('/api/planner', params={'module_id': 'M-10001'}).status_code, 200)
            hits = client.get('/api/search', params={'q': 'Vergessenskurve', 'module_id': 'M-10001'}).json()
            self.assertGreater(hits['total'], 0)
            source = client.get('/api/source', params={'path': bundle['lessons'][0]['sections'][0]['sources'][0]['path']})
            self.assertEqual((source.status_code, source.content[:5]), (200, b'%PDF-'))

    def test_question_packages_are_valid_and_cite_existing_pages(self):
        for unit in (1, 2):
            content = json.loads((DEMO / f'imports/lernen_lernen_einheit{unit}.json').read_text(encoding='utf-8'))
            self.assertEqual(validate_import(content), [])
            for question in content['questions']:
                self.assertTrue((DEMO / 'study' / question['source']).is_file(), question['id'])
                self.assertIn(question['source_page'], (1, 2, 3, 4), question['id'])
                self.assertIs(question['verified'], False)

    def test_install_never_overwrites_and_only_adds_to_existing_lists(self):
        (self.project / 'imports').mkdir()
        (self.project / 'imports' / 'seed.json').write_text(json.dumps(['eigenes_paket.json']), encoding='utf-8')
        goals = self.project / 'content' / 'tutor' / 'goals.json'
        goals.parent.mkdir(parents=True)
        goals.write_text(json.dumps([{'id': 'eigenes-ziel', 'module_id': 'M-1'}]), encoding='utf-8')
        own = self.project / 'content' / 'lernen-lernen-learning-pages.json'
        own.write_text('{"eigene": "Fassung"}', encoding='utf-8')
        copied, skipped, merged, _ = install(self.project, self.study)
        self.assertEqual((len(copied), skipped, len(merged)), (6, ['content/lernen-lernen-learning-pages.json'], 2))
        self.assertEqual(own.read_text(encoding='utf-8'), '{"eigene": "Fassung"}')
        self.assertEqual(json.loads((self.project / 'imports' / 'seed.json').read_text()),
                         ['eigenes_paket.json', 'lernen_lernen_einheit1.json', 'lernen_lernen_einheit2.json'])
        self.assertEqual([goal['id'] for goal in json.loads(goals.read_text())], ['eigenes-ziel', 'll-testeffekt', 'll-abstaende', 'll-lernplan'])
        own.unlink()
        self.assertEqual(install(self.project, self.study)[:3], (['content/lernen-lernen-learning-pages.json'], [
            'study/10001 Lernen lernen (Demo)/10001-01-S#1-demo.pdf', 'study/10001 Lernen lernen (Demo)/10001-02-S#1-demo.pdf',
            'study/10001 Lernen lernen (Demo)/Einsendearbeiten/10001-uebungsarbeit-1-demo.pdf',
            'content/assignments/lernen-lernen-uebung1.json', 'imports/lernen_lernen_einheit1.json', 'imports/lernen_lernen_einheit2.json'], []))

    def test_study_folder_inside_the_program_folder_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'nicht im Programmordner'):
            install(self.project, self.project / 'studium')
        self.assertFalse((self.project / 'content').exists())


if __name__ == '__main__':
    unittest.main()
