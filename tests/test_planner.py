"""Integration coverage for cross-module deadlines and saved learning positions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.main import create_app
from backend.tutor import TutorService
from tests.test_learning_pages import sample_page


def test_saved_position_and_studywide_deadline_are_used_in_answers():
    with TemporaryDirectory() as directory:
        source = Path(directory)
        project = source / 'hub'
        (project / 'content').mkdir(parents=True)
        (source / 'material').mkdir()
        pdf = PdfWriter()
        pdf.add_blank_page(width=100, height=100)
        pdf.write(source / 'material' / 'lehrbrief.pdf')
        (project / 'content' / 'bi.json').write_text(json.dumps(sample_page()), encoding='utf-8')
        app = create_app(source, project / 'data', project, start_watch=False)
        mid = app.state.hub.add_module({'name': 'Business Intelligence', 'number': '32711'})['id']
        with TestClient(app, base_url='http://127.0.0.1') as client:
            lesson = {'module_id': mid, 'lesson_id': 'bi-metadaten'}
            progress = '/api/planner/progress'
            assert client.post(progress, json={**lesson, 'status': 'started', 'section_id': 'unknown'}).status_code == 404
            assert client.post(progress, json={**lesson, 'status': 'started', 'section_id': 'begriff'}).status_code == 200

            deadlines = '/api/planning/deadlines'
            deadline = {'title': 'Rückmeldung', 'category': 'reenrollment', 'module_id': None,
                        'start': '2027-01-31', 'all_day': True}
            created = client.post(deadlines, json=deadline)
            assert created.status_code == 201, created.text
            event_id = created.json()['id']
            assert client.get('/api/planning').json()['events'][0]['id'] == event_id
            plan = client.get('/api/planner', params={'module_id': mid}).json()
            assert plan['resume']['section_id'] == 'begriff'
            assert plan['events'][0]['id'] == event_id
            assert 'Warum Metadaten?' in client.post('/api/planner/ask', json={'topic': 'resume'}).json()['answer']
            assert '31.01.2027' in client.post('/api/planner/ask', json={'topic': 'deadlines'}).json()['answer']

            transport = Mock(return_value={'message': {'role': 'assistant', 'content': 'Die Rückmeldung ist am 31.01.2027 fällig.'}})
            app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'test'}, transport)
            generated = client.post('/api/planner/ask', json={'message': 'Wann ist die Rückmeldung?'})
            assert generated.status_code == 200, generated.text
            assert generated.json()['generated']
            assert '31.01.2027' in str(json.loads(transport.call_args.args[0].data))
            assert transport.call_args.args[0].full_url.startswith('http://127.0.0.1:')

            assert client.post(progress, json={**lesson, 'status': 'done'}).status_code == 200
            assert client.get('/api/planner').json()['resume'] is None
            assert client.get('/api/planner/lesson-status', params=lesson).json() == {'status': 'done'}
            endpoint = f'/api/planning/events/{event_id}'
            assert client.patch(endpoint, json={'status': 'done'}).status_code == 200
            updated = client.put(f'{deadlines}/{event_id}', json={**deadline, 'start': '2027-02-01'})
            assert updated.json()['status'] == 'done'
            assert client.delete(f'{deadlines}/{event_id}').status_code == 204
            assert client.get('/api/planner').json()['events'] == []
