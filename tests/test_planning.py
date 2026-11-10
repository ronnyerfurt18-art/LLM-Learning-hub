"""Source dates, persistent personal planning and RFC 5545 calendar export."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.planning import META_KEY
from tests.test_core import sample_import


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'study'
        self.project = self.source / 'master-learning-hub'
        (self.project / 'planning').mkdir(parents=True)
        (self.source / 'material').mkdir()
        (self.source / 'material' / 'dates.ics').write_text('BEGIN:VCALENDAR\nEND:VCALENDAR\n')
        (self.source / 'material' / 'notice.png').write_bytes(b'example')
        self.app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        self.client = TestClient(self.app, base_url='http://127.0.0.1', raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.hub = self.app.state.hub
        self.hub.import_content(sample_import(['single_choice']))
        self.hub.attempt('test-single_choice', [0])
        self.mid = self.hub.modules()[0]['id']
        self.other = self.hub.add_module({'name': 'Anderes Modul', 'number': '88888'})['id']
        self.deadline = {'id': 'exam-registration', 'module_id': self.mid,
                         'title': 'Anmeldung abschließen', 'kind': 'deadline',
                         'start': '2026-12-01', 'end': '2026-12-02', 'all_day': True,
                         'timezone': 'Europe/Berlin', 'description': 'Frist gemäß Kalender.',
                         'source': {'path': 'material/dates.ics', 'title': 'Terminkalender', 'kind': 'ics'},
                         'status': 'planned'}
        self.teaching = {'id': 'online-lecture', 'module_id': self.mid,
                         'title': 'Vorlesung', 'kind': 'teaching',
                         'start': '2026-10-20T17:00:00+02:00', 'all_day': False,
                         'description': 'Ein Ende ist in der Quelle nicht angegeben.', 'status': 'planned'}
        self.write_seed([self.deadline, self.teaching])

    def write_seed(self, events):
        self.seed = {'schema_version': 1, 'events': events, 'notes': ['Quelltermine und eigene Lernblöcke.']}
        (self.project / 'planning' / 'study-events.json').write_text(json.dumps(self.seed, ensure_ascii=False), encoding='utf-8')

    def learning_state(self):
        with self.hub.db() as db:
            return {name: [tuple(row) for row in db.execute('SELECT * FROM ' + name + ' ORDER BY 1')]
                    for name in ('modules', 'questions', 'originals', 'attempts', 'progress', 'exams')}

    def study_block(self, **changes):
        return {**{'module_id': self.mid, 'title': 'Kapitel 1 nachlesen', 'kind': 'study',
                   'start': '2026-10-20T16:00:00Z', 'end': '2026-10-20T17:00:00Z',
                   'all_day': False, 'description': 'Begriffe ordnen.'}, **changes}

    def test_source_dates_are_read_only_filtered_and_get_has_no_database_writes(self):
        before = self.learning_state()
        meta_before = self.hub.get_meta(META_KEY)
        result = self.client.get('/api/planning')
        self.assertEqual(result.status_code, 200, result.text)
        content = result.json()
        self.assertEqual(content['timezone'], 'Europe/Berlin')
        self.assertRegex(content['today'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertEqual(len(content['events']), 2)
        self.assertEqual(content['notes'], self.seed['notes'])
        self.assertEqual(self.client.get('/api/planning', params={'module_id': self.other}).json()['events'], [])
        self.assertEqual(self.client.get('/api/planning', params={'module_id': 'unknown'}).status_code, 404)
        self.assertEqual(self.learning_state(), before)
        self.assertEqual(self.hub.get_meta(META_KEY), meta_before)

    def test_personal_blocks_and_completion_survive_new_app_and_preserve_learning_records(self):
        before = self.learning_state()
        seed_bytes = (self.project / 'planning' / 'study-events.json').read_bytes()
        created = self.client.post('/api/planning/events', json=self.study_block())
        self.assertEqual(created.status_code, 201, created.text)
        event = created.json()
        self.assertEqual(event['start'], '2026-10-20T18:00:00+02:00')
        self.assertEqual(event['end'], '2026-10-20T19:00:00+02:00')
        self.assertEqual(event['status'], 'planned')
        marked = self.client.patch('/api/planning/events/exam-registration', json={'status': 'done'})
        self.assertEqual(marked.status_code, 200, marked.text)
        state = self.hub.get_meta(META_KEY)
        self.assertEqual(self.client.patch('/api/planning/events/exam-registration', json={'status': 'done'}).status_code, 200)
        self.assertEqual(self.hub.get_meta(META_KEY), state)
        other_app = create_app(self.source, self.project / 'data', self.project, start_watch=False)
        with TestClient(other_app, base_url='http://127.0.0.1') as client:
            events = {item['id']: item for item in client.get('/api/planning').json()['events']}
        self.assertEqual(events[event['id']], event)
        self.assertEqual(events['exam-registration']['status'], 'done')
        self.assertEqual((self.project / 'planning' / 'study-events.json').read_bytes(), seed_bytes)
        self.assertEqual(self.learning_state(), before)
        self.assertEqual(self.client.patch('/api/planning/events/unknown', json={'status': 'done'}).status_code, 404)

    def test_bad_dates_types_and_ends_never_write_a_block(self):
        changes = [
            {'start': '2026-02-30T12:00:00+01:00'}, {'start': '2026-10-20T12:00:00'},
            {'start': '2026-10-20'}, {'start': '2026-10-20T12:00:00.123Z'},
            {'end': '2026-10-20T16:00:00Z'}, {'end': '2026-10-20T15:59:00Z'},
            {'end': None}, {'all_day': True}, {'all_day': 'false'}, {'kind': 'exam'},
            {'kind': []}, {'title': '   '}, {'title': 'invalid\x01text'}, {'timezone': 'UTC'},
            {'source': {'path': 'material/dates.ics', 'title': 'Offiziell'}}, {'id': 'invented'},
        ]
        for change in changes:
            with self.subTest(change=change):
                result = self.client.post('/api/planning/events', json=self.study_block(**change))
                self.assertEqual(result.status_code, 400, result.text)
        invalid_unicode = self.client.post('/api/planning/events',
                                           content=json.dumps(self.study_block(title='invalid\ud800text')),
                                           headers={'Content-Type': 'application/json'})
        self.assertEqual(invalid_unicode.status_code, 400, invalid_unicode.text)
        self.assertEqual(self.hub.get_meta(META_KEY), None)
        self.assertEqual(self.client.post('/api/planning/events', json=self.study_block(module_id='unknown')).status_code, 404)
        self.assertEqual(self.hub.get_meta(META_KEY), None)

    def test_patch_cannot_move_source_dates_or_replace_other_fields(self):
        for patch in ({'start': '2027-01-01'}, {'status': 'done', 'title': 'anders'}, {},
                      {'status': 'cancelled'}, {'status': []}):
            response = self.client.patch('/api/planning/events/exam-registration', json=patch)
            self.assertEqual(response.status_code, 400, response.text)
        event = next(event for event in self.client.get('/api/planning').json()['events'] if event['id'] == self.deadline['id'])
        self.assertEqual(event['start'], self.deadline['start'])
        self.assertEqual(event['status'], 'planned')
        self.assertIsNone(self.hub.get_meta(META_KEY))

    def test_calendar_stable_uid_all_day_exclusive_end_no_invented_timed_end(self):
        response = self.client.get('/api/planning/calendar.ics')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('text/calendar', response.headers['content-type'])
        self.assertIn('attachment', response.headers['content-disposition'])
        raw = response.content
        self.assertFalse(re.search(rb'(?<!\r)\n', raw))
        text = raw.decode('utf-8').replace('\r\n ', '')
        self.assertIn('TZID:Europe/Berlin\r\n', text)
        self.assertIn('DTSTART;VALUE=DATE:20261201\r\nDTEND;VALUE=DATE:20261202\r\n', text)
        lecture = next(block for block in text.split('BEGIN:VEVENT') if 'SUMMARY:Vorlesung' in block)
        self.assertIn('DTSTART:20261020T150000Z', lecture)
        self.assertNotIn('DTEND', lecture)
        uids = re.findall(r'^UID:(.*)$', text, re.MULTILINE)
        second = self.client.get('/api/planning/calendar.ics').text.replace('\r\n ', '')
        self.assertEqual(uids, re.findall(r'^UID:(.*)$', second, re.MULTILINE))
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(len(uids), 2)
        filtered = self.client.get('/api/planning/calendar.ics', params={'event_id': self.deadline['id']})
        self.assertEqual(filtered.text.count('BEGIN:VEVENT'), 1)
        self.assertNotIn('SUMMARY:Vorlesung', filtered.text)
        self.assertEqual(self.client.get('/api/planning/calendar.ics', params={'module_id': self.other}).text.count('BEGIN:VEVENT'), 0)
        self.assertEqual(self.client.get('/api/planning/calendar.ics', params={'event_id': 'missing'}).status_code, 404)

    def test_calendar_utf8_folding_and_untrusted_text_cannot_inject_properties(self):
        title = ('Äpfel 🍎; prüfen, lesen \\ ' * 12) + '\r\nBEGIN:VEVENT\r\nSUMMARY:Fake'
        response = self.client.post('/api/planning/events', json=self.study_block(title=title, location='Zuhause\nEND:VCALENDAR'))
        self.assertEqual(response.status_code, 201, response.text)
        raw = self.client.get('/api/planning/calendar.ics', params={'event_id': response.json()['id']}).content
        for line in raw.split(b'\r\n'):
            self.assertLessEqual(len(line), 75)
            line.decode('utf-8')  # Folding never bisects a multibyte codepoint.
        unfolded = raw.decode('utf-8').replace('\r\n ', '')
        self.assertEqual(unfolded.count('\r\nBEGIN:VEVENT\r\n'), 1)
        self.assertEqual(unfolded.count('\r\nEND:VCALENDAR\r\n'), 1)
        self.assertIn(r'\nBEGIN:VEVENT\nSUMMARY:Fake', unfolded)
        self.assertIn(r'\; prüfen\, lesen \\', unfolded)
        self.assertIn(r'LOCATION:Zuhause\nEND:VCALENDAR', unfolded)

    def test_dst_boundaries_and_repeated_hour_retain_absolute_instants(self):
        blocks = [
            self.study_block(start='2026-03-29T01:30:00+01:00', end='2026-03-29T03:30:00+02:00'),
            self.study_block(start='2026-10-25T02:30:00+02:00', end='2026-10-25T02:30:00+01:00'),
        ]
        for block in blocks:
            created = self.client.post('/api/planning/events', json=block)
            self.assertEqual(created.status_code, 201, created.text)
            response = self.client.get('/api/planning/calendar.ics', params={'event_id': created.json()['id']})
            text = response.text.replace('\r\n ', '')
            self.assertIn('RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU', text)
            self.assertIn('RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU', text)
            if block['start'].startswith('2026-03'):
                self.assertIn('DTSTART:20260329T003000Z', text)
                self.assertIn('DTEND:20260329T013000Z', text)
            else:
                self.assertIn('DTSTART:20261025T003000Z', text)
                self.assertIn('DTEND:20261025T013000Z', text)

    def test_duplicate_seed_ids_and_invalid_all_day_end_are_rejected(self):
        self.write_seed([self.deadline, copy.deepcopy(self.deadline)])
        self.assertEqual(self.client.get('/api/planning').status_code, 400)
        self.assertEqual(self.client.get('/api/planning/calendar.ics').status_code, 400)
        for end in ('2026-12-01', '2026-11-30', '2026-12-02T00:00:00+01:00'):
            event = {**self.deadline, 'end': end}
            self.write_seed([event])
            result = self.client.get('/api/planning')
            self.assertEqual(result.status_code, 400, result.text)
        self.assertIsNone(self.hub.get_meta(META_KEY))

    def test_sources_are_confined_even_for_symlinks_and_image_references_are_supported(self):
        internal = self.project / 'data' / 'internal.ics'
        internal.write_text('private')
        outside = self.root / 'external.ics'
        outside.write_text('external')
        (self.source / 'material' / 'escape.ics').symlink_to(outside)
        (self.project / 'data' / 'alias.ics').symlink_to(self.source / 'material' / 'dates.ics')
        (self.source / 'node_modules').mkdir()
        (self.source / 'node_modules' / 'internal.ics').write_text('private')
        for path in ('../external.ics', str(outside), 'master-learning-hub/data/internal.ics',
                     'material/escape.ics', '.aws/private.ics', 'material/unknown.ics',
                     'master-learning-hub/data/alias.ics', 'node_modules/internal.ics'):
            self.write_seed([{**self.deadline, 'source': {**self.deadline['source'], 'path': path}}])
            result = self.client.get('/api/planning')
            self.assertEqual(result.status_code, 400, result.text)
            self.assertNotIn('private', result.text)
        image_source = {'path': 'material/notice.png', 'title': 'Terminübersicht', 'kind': 'image'}
        self.write_seed([{**self.deadline, 'source': image_source}])
        result = self.client.get('/api/planning')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['events'][0]['source'], image_source)
        self.write_seed([{**self.deadline, 'source': {**image_source, 'pdf_page': 1}}])
        self.assertEqual(self.client.get('/api/planning').status_code, 400)

    def test_original_calendar_uid_is_preserved_verbatim_on_repeated_exports(self):
        original_uid = 'bi-kickoff-20261028@fernuni-calendar.local'
        self.write_seed([{**self.teaching, 'calendar_uid': original_uid}])
        event = self.client.get('/api/planning').json()['events'][0]
        self.assertEqual(event['calendar_uid'], original_uid)
        for _ in range(2):
            response = self.client.get('/api/planning/calendar.ics')
            self.assertEqual(response.status_code, 200, response.text)
            unfolded = response.text.replace('\r\n ', '')
            self.assertEqual(re.findall(r'^UID:(.*)\r$', unfolded, re.MULTILINE), [original_uid])
            self.assertNotIn('@master-learning-hub.local', unfolded)

    def test_calendar_uids_reject_duplicates_injection_and_personal_override(self):
        shared_uid = 'already-imported@fernuni-calendar.local'
        self.write_seed([{**self.teaching, 'calendar_uid': shared_uid},
                         {**self.deadline, 'calendar_uid': shared_uid}])
        self.assertEqual(self.client.get('/api/planning').status_code, 400)
        self.assertEqual(self.client.get('/api/planning/calendar.ics').status_code, 400)
        for invalid in ('x\r\nSUMMARY:Injected', 'white space@example.org', '',
                        'x\t@example.org', 'x\x7f@example.org', 'x,second', 'x;second',
                        'x\\second', 'ä' * 128, ['not a string']):
            self.write_seed([{**self.teaching, 'calendar_uid': invalid}])
            response = self.client.get('/api/planning')
            self.assertEqual(response.status_code, 400, response.text)
        self.write_seed([self.teaching])
        response = self.client.post('/api/planning/events', json=self.study_block(calendar_uid=shared_uid))
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIsNone(self.hub.get_meta(META_KEY))

    def test_same_origin_rule_protects_personal_writes(self):
        response = self.client.post('/api/planning/events', json=self.study_block(), headers={'Origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)
        response = self.client.patch('/api/planning/events/exam-registration', json={'status': 'done'}, headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.hub.get_meta(META_KEY))

    def test_missing_seed_still_allows_personal_planning(self):
        (self.project / 'planning' / 'study-events.json').unlink()
        self.assertEqual(self.client.get('/api/planning').json()['events'], [])
        response = self.client.post('/api/planning/events', json=self.study_block())
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(self.client.get('/api/planning').json()['events']), 1)


if __name__ == '__main__':
    unittest.main()
