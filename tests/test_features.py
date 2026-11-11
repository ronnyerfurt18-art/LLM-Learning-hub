"""Switch-off list `features`: launcher check, routes of a disabled feature, /api/settings, and a model switch keeping settings."""
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import launcher
from backend.local_model import FEATURES, active_features, check_features
from backend.main import create_app
from backend.tutor import TutorService, register_tutor_routes

NOT_FOUND = {'detail': 'Not Found'}  # the answer for an address that has no route at all


def _config(tmp_path, **values):
    (tmp_path / 'tutor.local.json').write_text(json.dumps({'model': 'test:1b', **values}), encoding='utf-8')


def test_launcher_accepts_known_features_and_hands_them_on(tmp_path):
    with patch.object(launcher, 'PROJECT', tmp_path), patch.dict(os.environ):
        os.environ.pop('MLH_FEATURES', None)
        _config(tmp_path)
        launcher.configure()
        assert 'MLH_FEATURES' not in os.environ  # no key: every feature stays on
        _config(tmp_path, features=['big_picture', 'voice', 'voice'])
        launcher.configure()
        assert os.environ['MLH_FEATURES'] == 'voice,big_picture'
        _config(tmp_path, features=[])
        launcher.configure()
        assert os.environ['MLH_FEATURES'] == ''
        _config(tmp_path, features=list(FEATURES))
        launcher.configure()
        assert os.environ['MLH_FEATURES'] == 'voice,module_import,big_picture'


@pytest.mark.parametrize('bad', [['voice', 'chat'], ['Voice'], 'voice', [1], None, {'voice': True}, ['voice', None]])
def test_launcher_refuses_unknown_or_malformed_features(tmp_path, bad):
    with patch.object(launcher, 'PROJECT', tmp_path), patch.dict(os.environ):
        os.environ.pop('MLH_FEATURES', None)
        _config(tmp_path, features=bad)
        with pytest.raises(ValueError, match='features in tutor.local.json'):
            launcher.configure()
        assert 'MLH_FEATURES' not in os.environ


def test_unknown_value_is_named_in_the_error():
    with pytest.raises(ValueError, match='chat'):
        check_features(['voice', 'chat'])
    assert check_features(['big_picture', 'voice']) == ['voice', 'big_picture']


def test_environment_variable_defaults_to_all_features():
    assert active_features({}) == list(FEATURES)
    assert active_features({'MLH_FEATURES': ''}) == []
    assert active_features({'MLH_FEATURES': ' big_picture , voice'}) == ['voice', 'big_picture']
    with pytest.raises(ValueError, match='MLH_FEATURES'):
        active_features({'MLH_FEATURES': 'voice,nope'})


def _app(tmp_path, monkeypatch, features):
    if features is None:
        monkeypatch.delenv('MLH_FEATURES', raising=False)
    else:
        monkeypatch.setenv('MLH_FEATURES', features)
    study, project = tmp_path / 'Studium', tmp_path / 'hub'
    study.mkdir()
    project.mkdir()
    app = create_app(study, project / 'data', project, start_watch=False)
    return app, TestClient(app, base_url='http://127.0.0.1')


def _probe(client):
    """What each feature answers when it is switched on: not 'Not Found' (an unknown module is a different 404)."""
    upload = client.post('/api/documents/upload', params={'module_id': 'M-0', 'filename': 'a.md'}, content=b'x')
    return {
        'module_import': (client.get('/api/module-import/preview', params={'module_id': 'M-0'}).json() != NOT_FOUND,
                          client.get('/api/module-import').json() != NOT_FOUND,
                          client.get('/api/module-import/overview', params={'module_id': 'M-0'}).json() != NOT_FOUND,
                          client.post('/api/module-import/cancel', json={}).json() != NOT_FOUND,
                          upload.status_code != 405 and upload.json() != NOT_FOUND),
        'big_picture': (client.get('/api/big-picture', params={'module_id': 'M-0'}).json() != NOT_FOUND,
                        client.post('/api/big-picture', json={}).json() != NOT_FOUND,
                        client.post('/api/big-picture/publish', json={}).json() != NOT_FOUND),
        'voice': (client.get('/api/tutor/voice/status').json() != NOT_FOUND,)}


def test_every_feature_is_on_when_nothing_is_configured(tmp_path, monkeypatch):
    app, client = _app(tmp_path, monkeypatch, None)
    with client:
        assert {name: all(flags) for name, flags in _probe(client).items()} == {'module_import': True, 'big_picture': True, 'voice': True}
        assert client.get('/api/settings').json()['features'] == ['voice', 'module_import', 'big_picture']


@pytest.mark.parametrize('on', [[], ['voice'], ['module_import'], ['big_picture'], ['voice', 'big_picture'], ['module_import', 'big_picture']])
def test_a_disabled_feature_has_no_routes_and_the_rest_keeps_running(tmp_path, monkeypatch, on):
    app, client = _app(tmp_path, monkeypatch, ','.join(on))
    with client:
        probe = _probe(client)
        assert {name: all(flags) for name, flags in probe.items()} == {name: name in on for name in FEATURES}
        # Nothing of a disabled feature is half there.
        assert all(not any(flags) for name, flags in probe.items() if name not in on)
        assert client.get('/api/settings').json()['features'] == [name for name in FEATURES if name in on]
        assert client.get('/api/modules').status_code == 200 and client.get('/api/documents').status_code == 200
        assert client.get('/api/tutor/status').status_code == 200 and client.get('/api/health').json()['status'] == 'ok'
        assert client.get('/api/learning-pages').status_code == 200


def test_disabled_upload_writes_nothing(tmp_path, monkeypatch):
    app, client = _app(tmp_path, monkeypatch, 'voice,big_picture')
    with client:
        module = app.state.hub.add_module({'name': 'Statistik', 'number': '10002'})['id']
        answer = client.post('/api/documents/upload', params={'module_id': module, 'filename': 'a.md'}, content=b'text')
        assert answer.status_code in (404, 405) and not answer.is_success
        assert list((tmp_path / 'Studium').iterdir()) == []


def test_model_switch_keeps_study_folder_features_and_machine_settings(tmp_path):
    kept = {'study_folder': '/data/Studium', 'features': ['voice', 'big_picture'], 'context_tokens': 16384,
            'bonsai_runtime': '/opt/bonsai', 'voice_runtime': '/opt/voice'}
    app = FastAPI()
    app.state.tutor = TutorService({'MLH_TUTOR_PROVIDER': 'none'}, transport=Mock())
    config = tmp_path / 'tutor.local.json'
    config.write_text(json.dumps({'enabled': True, 'model': 'my-qwen', **kept}))
    model = tmp_path / 'model'
    model.mkdir()
    (model / 'model.safetensors').touch()
    register_tutor_routes(app, None, tmp_path, tmp_path)
    client = TestClient(app)
    with patch('backend.tutor.BONSAI_PATH', model), patch('backend.tutor.TutorService.start'), patch('backend.tutor.TutorService.stop'):
        for provider in ('bonsai', 'ollama', 'bonsai'):
            assert client.post('/api/tutor/model', json={'provider': provider}).status_code == 200
            saved = json.loads(config.read_text())
            assert {key: saved[key] for key in kept} == kept, provider
            assert (saved['provider'], saved['ollama_model']) == (provider, 'my-qwen')
    # What the switch wrote is still a configuration the launcher accepts, and the study folder is still found.
    with patch.object(launcher, 'PROJECT', tmp_path), patch.dict(os.environ), patch.object(launcher.local_model, 'CONTEXT_TOKENS', 32768):
        os.environ.pop('MLH_SOURCE_ROOT', None)
        launcher.configure()
        assert os.environ['MLH_FEATURES'] == 'voice,big_picture' and os.environ['MLH_SOURCE_ROOT'] == '/data/Studium'
