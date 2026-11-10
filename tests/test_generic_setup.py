"""The hub carries no module of its own: labels, assignments, start list and runtimes come from data and settings."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.assignments import assignment_module_numbers, load_assignments, validate_assignment
from backend.core import Hub
from backend.local_model import context_tokens, runtime_dir
from backend.main import create_app, seed_packages
from tests.test_assignments import AssignmentTests, sample_assignment


class UnitLabelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = Hub(Path(self.temp.name) / 'hub.sqlite3')

    def test_label_defaults_to_einheit_and_is_kept_per_module(self):
        first = self.hub.add_module({'name': 'Statistik', 'number': '10001'})
        second = self.hub.add_module({'name': 'Videokurs', 'number': '10002', 'unit_label': 'Session'})
        self.assertEqual((first['unit_label'], second['unit_label']), ('Einheit', 'Session'))
        self.assertEqual(self.hub.patch_module(first['id'], {'unit_label': 'Kapitel'})['unit_label'], 'Kapitel')
        self.assertEqual(self.hub.patch_module(first['id'], {'name': 'Statistik I'})['unit_label'], 'Kapitel')
        self.assertEqual(self.hub.module(second['id'])['unit_label'], 'Session')
        self.assertEqual(Hub(self.hub.path).module(first['id'])['unit_label'], 'Kapitel')

    def test_unknown_label_is_rejected_without_changes(self):
        module = self.hub.add_module({'name': 'Statistik'})
        with self.assertRaises(ValueError):
            self.hub.patch_module(module['id'], {'unit_label': 'Abenteuer'})
        with self.assertRaises(ValueError):
            self.hub.add_module({'name': 'Neu', 'unit_label': 'Abenteuer'})
        self.assertEqual(self.hub.module(module['id'])['unit_label'], 'Einheit')
        self.assertEqual(len(self.hub.modules()), 1)


class GenericAssignmentTests(AssignmentTests):
    def small(self):
        content = sample_assignment()
        content.update(id='statistik-uebung-1', module_number='10001')
        del content['rules']
        content['questions'] = copy.deepcopy(content['questions'][:2])
        for number, question in enumerate(content['questions'], 1):
            question['id'] = f'statistik-uebung-1-q{number:02}'
            question['options'] = question['options'][:3]
            for option in question['options']:
                option['is_correct'] = False
        return content

    def test_assignment_without_fixed_shape_is_valid_for_its_own_module(self):
        content = self.small()
        self.assertEqual(self.problems(content), [])
        (self.directory / 'statistik-uebung-1.json').write_text(json.dumps(content), encoding='utf-8')
        self.assertEqual(assignment_module_numbers(self.project), {'10001', '32281'})
        self.assertEqual([item['id'] for item in load_assignments(self.project, self.source, module_number='10001')],
                         ['statistik-uebung-1'])
        self.assertEqual(len(load_assignments(self.project, self.source, module_number='32281')), 2)
        app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            own = app.state.hub.add_module({'name': 'Statistik', 'number': '10001'})['id']
            other = app.state.hub.add_module({'name': 'Ohne Arbeiten', 'number': '10003'})['id']
            self.assertEqual([item['id'] for item in client.get(f'/api/assignments/{own}').json()['assignments']],
                             ['statistik-uebung-1'])
            self.assertEqual(client.get(f'/api/assignments/{other}').status_code, 404)
            flags = {module['number']: module['has_assignments'] for module in client.get('/api/modules').json()}
            self.assertEqual(flags, {'10001': True, '10003': False})

    def test_shape_rules_and_ids_are_checked(self):
        for change in ({'id': 'Mit Leerzeichen'}, {'module_number': ''}, {'rules': {'question_count': 3}},
                       {'rules': {'option_count': 5}}, {'rules': {'min_true': 1}},
                       {'rules': {'option_count': 3, 'points': [0, 50, 100]}}):
            self.assertTrue(self.problems({**self.small(), **change}), change)
        self.assertEqual(self.problems({**self.small(), 'rules': {'option_count': 3, 'points': [0, 10, 50, 100]}}), [])
        duplicate = self.small()
        duplicate['id'] = 'dd-ea1'
        (self.directory / 'zweite.json').write_text(json.dumps(duplicate), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'bereits von einer anderen'):
            load_assignments(self.project, self.source)


class StartListAndRuntimeTests(unittest.TestCase):
    def test_start_list_names_only_plain_package_files(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            self.assertEqual(seed_packages(project), [])
            (project / 'imports').mkdir()
            (project / 'imports' / 'seed.json').write_text(json.dumps(
                ['demo.json', '../outside.json', 'seed.json', 'notes.txt', 7, 'sub/inner.json']), encoding='utf-8')
            self.assertEqual(seed_packages(project), ['demo.json'])
            (project / 'imports' / 'seed.json').write_text('{"demo.json": true}', encoding='utf-8')
            self.assertEqual(seed_packages(project), [])
            # The list itself never shows up as a learning package to confirm.
            app = create_app(project, project / 'data', project, start_watch=False)
            with TestClient(app, base_url='http://127.0.0.1') as client:
                client.post('/api/scan', json={})
                self.assertFalse([d for d in client.get('/api/documents').json() if d['path'].endswith('seed.json')])

    def test_runtime_folders_and_context_window_follow_the_settings(self):
        with patch.dict(os.environ, {'MLH_BONSAI_RUNTIME': '/opt/laufzeit/bonsai'}):
            self.assertEqual(runtime_dir('bonsai-demo', 'MLH_BONSAI_RUNTIME'), Path('/opt/laufzeit/bonsai'))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('MLH_VOICE_RUNTIME', None)
            self.assertEqual(runtime_dir('voice', 'MLH_VOICE_RUNTIME'), Path.home() / '.learning-hub' / 'runtimes' / 'voice')
        self.assertEqual([context_tokens(value) for value in ('', '16384', '100', '9999999', 'viel')],
                         [32768, 16384, 8192, 131072, 32768])

    def test_launcher_accepts_machine_settings_and_rejects_bad_ones(self):
        import launcher
        from backend import local_model
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'tutor.local.json'
            before = local_model.CONTEXT_TOKENS
            try:
                with patch.object(launcher, 'PROJECT', Path(folder)), patch.dict(os.environ, {}, clear=False):
                    config.write_text(json.dumps({'model': 'test:1b', 'context_tokens': 16384,
                                                  'bonsai_runtime': '/opt/bonsai', 'voice_runtime': '/opt/voice'}))
                    launcher.configure()
                    self.assertEqual((os.environ['MLH_CONTEXT_TOKENS'], os.environ['MLH_BONSAI_RUNTIME'],
                                      os.environ['MLH_VOICE_RUNTIME'], local_model.CONTEXT_TOKENS),
                                     ('16384', '/opt/bonsai', '/opt/voice', 16384))
                    for bad in ({'context_tokens': 100}, {'context_tokens': '16384'}, {'bonsai_runtime': ''}, {'voice_runtime': 5}):
                        config.write_text(json.dumps({'model': 'test:1b', **bad}))
                        with self.assertRaises(ValueError, msg=bad):
                            launcher.configure()
            finally:
                local_model.CONTEXT_TOKENS = before


class StudyFolderTests(unittest.TestCase):
    def test_study_folder_never_follows_the_project_location(self):
        from backend.local_model import study_folder
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('MLH_SOURCE_ROOT', None)
            project = Path(folder) / 'neben-anderen-projekten' / 'hub'
            project.mkdir(parents=True)
            default = Path.home() / 'LearningHub' / 'Studium'
            self.assertEqual(study_folder(project), default)
            self.assertEqual(study_folder(), default)
            (project / 'tutor.local.json').write_text(json.dumps({'study_folder': str(Path(folder) / 'Unterlagen')}))
            self.assertEqual(study_folder(project), Path(folder) / 'Unterlagen')
            os.environ['MLH_SOURCE_ROOT'] = str(Path(folder) / 'Vorrang')
            self.assertEqual(study_folder(project), Path(folder) / 'Vorrang')
            (project / 'tutor.local.json').write_text('{kaputt')
            os.environ.pop('MLH_SOURCE_ROOT')
            self.assertEqual(study_folder(project), default)

    def test_launcher_requires_a_configured_folder_and_refuses_the_program_folder(self):
        import launcher
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            project = Path(folder) / 'hub'
            project.mkdir()
            with patch.object(launcher, 'PROJECT', project):
                os.environ['MLH_SOURCE_ROOT'] = str(Path(folder) / 'fehlt')
                with self.assertRaisesRegex(ValueError, 'Studienordner nicht gefunden'):
                    launcher.ensure_study_folder()
                self.assertFalse((Path(folder) / 'fehlt').exists())
                os.environ['MLH_SOURCE_ROOT'] = str(project / 'unterlagen')
                with self.assertRaisesRegex(ValueError, 'nicht im Programmordner'):
                    launcher.ensure_study_folder()
                (Path(folder) / 'Studium').mkdir()
                os.environ['MLH_SOURCE_ROOT'] = str(Path(folder) / 'Studium')
                self.assertEqual(launcher.ensure_study_folder(), (Path(folder) / 'Studium').resolve())


if __name__ == '__main__':
    unittest.main()
