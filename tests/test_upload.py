"""Upload of study documents: placement, refusals and a clean folder after every failure."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from backend import upload
from backend.main import create_app

TEXT = ('Die Stichprobe beschreibt einen Ausschnitt der Grundgesamtheit. Aus ihr werden Kennzahlen berechnet, '
        'die Rückschlüsse auf die Grundgesamtheit erlauben. ') * 3


def _tree(root):
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob('*'))


@pytest.fixture
def hub(tmp_path):
    study, project = tmp_path / 'Studium', tmp_path / 'hub'
    study.mkdir()
    project.mkdir()
    app = create_app(study, project / 'data', project, start_watch=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.study, client.project, client.hub = study, project, app.state.hub
        client.module = app.state.hub.add_module({'name': 'Statistik (Test)', 'number': '10002'})['id']
        yield client


def _send(client, name, content=TEXT.encode(), unit=None, module=None, **kwargs):
    params = {'module_id': module or client.module, 'filename': name, **({} if unit is None else {'unit': unit})}
    return client.post('/api/documents/upload', params=params, content=content,
                       headers={'Content-Type': 'application/octet-stream'}, **kwargs)


def test_upload_lands_in_the_unit_folder_and_appears_in_the_document_list(hub):
    answer = _send(hub, 'skript.md', unit=2)
    assert answer.status_code == 200, answer.text
    assert answer.json() == {'path': '10002 Statistik (Test)/Einheit 2/skript.md', 'module_id': hub.module,
                             'unit': 2, 'requested_unit': 2, 'size': len(TEXT.encode())}
    assert (hub.study / answer.json()['path']).read_bytes() == TEXT.encode()
    # The module has no folder yet: it was created and recorded at the module.
    assert hub.hub.module(hub.module)['directory'] == '10002 Statistik (Test)'
    documents = [doc for doc in hub.get('/api/documents').json() if doc['name'] == 'skript.md']
    assert [(doc['module_id'], doc['unit'], doc['status']) for doc in documents] == [(hub.module, 2, 'pending')]
    # Without a unit the file goes into the module folder itself.
    plain = _send(hub, 'glossar.md')
    assert plain.json()['path'] == '10002 Statistik (Test)/glossar.md' and plain.json()['unit'] is None
    assert not [name for name in _tree(hub.study) if name.endswith('.part')]


def test_existing_file_is_never_overwritten(hub, monkeypatch):
    assert _send(hub, 'skript.md', unit=1).status_code == 200
    started = []
    monkeypatch.setattr(upload.secrets, 'token_hex', lambda size: started.append(size) or 'abc')
    again = _send(hub, 'skript.md', content=b'Etwas ganz anderes', unit=1)
    assert again.status_code == 409 and 'nicht überschrieben' in again.json()['detail']
    assert started == []  # refused before any data was taken in
    assert (hub.study / '10002 Statistik (Test)/Einheit 1/skript.md').read_bytes() == TEXT.encode()
    assert not [name for name in _tree(hub.study) if name.endswith('.part')]
    # A symbolic link of that name counts as existing too, even when it points nowhere.
    link = hub.study / '10002 Statistik (Test)/Einheit 1/lose.md'
    link.symlink_to(hub.study / 'gibt-es-nicht.md')
    assert _send(hub, 'lose.md', unit=1).status_code == 409 and link.is_symlink()


def test_a_file_that_appears_while_the_upload_runs_is_not_overwritten(hub, monkeypatch):
    target = hub.study / '10002 Statistik (Test)' / 'wettlauf.md'

    def token(size):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'von jemand anderem')  # appears after the first check, before the upload is placed
        return 'abc'
    monkeypatch.setattr(upload.secrets, 'token_hex', token)
    answer = _send(hub, 'wettlauf.md')
    assert answer.status_code == 409
    assert target.read_bytes() == b'von jemand anderem' and not [name for name in _tree(hub.study) if name.endswith('.part')]


@pytest.mark.parametrize('name', ['../x.pdf', 'a/b.pdf', '.versteckt.pdf', '/etc/x.pdf', 'a\\b.pdf', '..', '', ' ', 'x.pdf ',
                                  'ctl\x01.pdf', 'C:x.pdf', '~$sperre.docx', 'z' * 178 + '.pdf'])
def test_path_tricks_and_odd_names_are_refused_before_anything_is_written(hub, name):
    before = _tree(hub.study)
    answer = _send(hub, name, unit=1)
    assert answer.status_code == 400, (name, answer.text)
    assert _tree(hub.study) == before and hub.hub.module(hub.module)['directory'] == ''


def test_name_length_limit_is_exact_and_extensions_are_checked(hub):
    assert _send(hub, 'z' * 176 + '.md').status_code == 200  # 180 characters
    for name in ('x.exe', 'x.sh', 'x', 'x.pdf.exe', 'x.zip', 'x.pdf.'):
        answer = _send(hub, name)
        assert answer.status_code == 400 and 'Dateityp' in answer.json()['detail'], name
    assert _send(hub, 'Folien.PDF', content=b'%PDF-1.4 kaputt').status_code == 200
    assert _send(hub, 'vorlesung.mp4', content=b'\x00\x00\x00\x18ftypmp42').status_code == 200


def test_bad_units_and_unknown_modules(hub):
    for unit in ('0', '1000', 'x', '1e2', '-1', '１２', '../..', '3_0'):
        assert _send(hub, 'a.md', unit=unit).status_code == 400, unit
    assert _send(hub, 'a.md', module='M-00000').status_code == 404
    assert _tree(hub.study) == []


def test_size_limit_is_enforced_while_reading_and_leaves_nothing(hub, monkeypatch):
    monkeypatch.setattr(upload, 'MAX_UPLOAD_BYTES', 10)
    # Declared too large: refused before the body is read.
    assert _send(hub, 'gross.md', content=b'x' * 11, unit=1).status_code == 413

    def chunks():
        for _ in range(5):
            yield b'abc'
    # Without a declared length the stream is counted chunk by chunk.
    streamed = hub.post('/api/documents/upload', params={'module_id': hub.module, 'filename': 'gross.md', 'unit': 1}, content=chunks(),
                        headers={'Content-Type': 'application/octet-stream'})
    assert streamed.status_code == 413
    assert _tree(hub.study) == [] and hub.hub.module(hub.module)['directory'] == ''
    assert _send(hub, 'genau.md', content=b'x' * 10).status_code == 200


def test_empty_file_is_refused_and_leaves_nothing(hub):
    answer = _send(hub, 'leer.md', content=b'', unit=3)
    assert answer.status_code == 400 and 'leer' in answer.json()['detail']
    assert _tree(hub.study) == [] and hub.hub.module(hub.module)['directory'] == ''


def test_existing_module_folder_is_used_and_kept_on_refusal(hub):
    (hub.study / '10002 Statistik (Test)').mkdir()
    hub.hub.patch_module(hub.module, {'directory': '10002 Statistik (Test)'})
    assert _send(hub, 'a.md', unit=4).status_code == 200
    assert _send(hub, 'b.exe', unit=4).status_code == 400
    assert _tree(hub.study) == ['10002 Statistik (Test)', '10002 Statistik (Test)/Einheit 4',
                                '10002 Statistik (Test)/Einheit 4/a.md']


def test_targets_outside_the_study_folder_or_inside_the_program_folder_are_refused(hub, tmp_path):
    outside = tmp_path / 'ausserhalb'
    outside.mkdir()
    (hub.study / 'Verlinkt').symlink_to(outside, target_is_directory=True)
    hub.hub.patch_module(hub.module, {'directory': 'Verlinkt'})
    assert _send(hub, 'a.md', unit=1).status_code == 403
    assert list(outside.iterdir()) == []
    # A unit folder that is a link to the outside is caught as well.
    real = hub.study / 'Echt'
    real.mkdir()
    (real / 'Einheit 1').symlink_to(outside, target_is_directory=True)
    hub.hub.patch_module(hub.module, {'directory': 'Echt'})
    assert _send(hub, 'a.md', unit=1).status_code == 403 and list(outside.iterdir()) == []
    hub.hub.patch_module(hub.module, {'directory': '../elsewhere'})
    assert _send(hub, 'a.md').status_code == 403 and not (hub.study.parent / 'elsewhere').exists()


def test_the_program_folder_never_receives_uploads(tmp_path):
    study = tmp_path / 'Studium'
    project = study / 'programm'  # misconfigured: program folder inside the study folder
    project.mkdir(parents=True)
    app = create_app(study, tmp_path / 'data', project, start_watch=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        module = app.state.hub.add_module({'name': 'Statistik (Test)', 'number': '10002', 'directory': 'programm'})['id']
        for unit in (None, 2):
            answer = client.post('/api/documents/upload', params={'module_id': module, 'filename': 'a.md', **({} if unit is None else {'unit': unit})},
                                 content=b'text', headers={'Content-Type': 'application/octet-stream'})
            assert answer.status_code == 403
    assert _tree(project) == []


def test_default_folder_name_is_cleaned(hub):
    from backend.upload import default_directory
    assert default_directory({'number': '10002', 'name': 'Statistik (Test)'}) == '10002 Statistik (Test)'
    assert default_directory({'number': '', 'name': 'A/B\\C:*?"<>|  D'}) == 'A B C D'
    assert default_directory({'name': '..'}) == 'Modul'
    assert len(default_directory({'number': '1', 'name': 'x' * 300})) <= 100


def test_answer_reports_the_unit_the_scan_found_not_only_the_requested_folder():
    import io
    from pypdf import PdfWriter
    with TemporaryDirectory() as folder:
        study, project = Path(folder) / 'Studium', Path(folder) / 'hub'
        study.mkdir()
        project.mkdir()
        app = create_app(study, project / 'data', project, start_watch=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            mid = client.post('/api/modules', json={'name': 'Statistik', 'number': '10002', 'unit_count': 3}).json()['id']
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            buffer = io.BytesIO()
            writer.write(buffer)
            answer = client.post('/api/documents/upload', params={'module_id': mid, 'filename': '10002-01-S#1-x.pdf', 'unit': '3'},
                                 content=buffer.getvalue()).json()
            assert (answer['unit'], answer['requested_unit']) == (1, 3)
            plain = client.post('/api/documents/upload', params={'module_id': mid, 'filename': 'skript.pdf', 'unit': '2'},
                                content=buffer.getvalue()).json()
            assert (plain['unit'], plain['requested_unit']) == (2, 2)
