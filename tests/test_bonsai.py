import io,json
import pytest
from unittest.mock import Mock, MagicMock
from fastapi import HTTPException
from backend.bonsai import StreamAdapter, MODEL
from backend.tutor import TutorService
from backend import bonsai

@pytest.mark.parametrize('data,expected', [([], False), ([{'id': MODEL}], True)])
def test_model_list_distinguishes_unloaded_from_ready(monkeypatch, data, expected):
    monkeypatch.setattr(bonsai, 'runtime_json', lambda path: {'data': data})
    assert bonsai.model_list() is expected

@pytest.mark.parametrize('data', [[{'id': 'other-model'}], None, ['invalid']])
def test_model_list_rejects_foreign_or_invalid_models(monkeypatch, data):
    monkeypatch.setattr(bonsai, 'runtime_json', lambda path: {'data': data})
    with pytest.raises(ValueError):
        bonsai.model_list()

@pytest.mark.parametrize('loaded', [False, True])
def test_start_reuses_verified_runtime_without_owning_it(monkeypatch, loaded):
    monkeypatch.setattr(bonsai, '_PROCESS', None)
    monkeypatch.setattr(bonsai, 'model_list', lambda: loaded)
    verify = Mock()
    monkeypatch.setattr(bonsai, 'verify_existing_runtime', verify)
    spawn = Mock()
    monkeypatch.setattr(bonsai.subprocess, 'Popen', spawn)
    bonsai.start_runtime()
    verify.assert_called_once()
    bonsai.stop_runtime()
    spawn.assert_not_called()
    assert bonsai._PROCESS is None

def test_start_rejects_unverified_listener(monkeypatch):
    monkeypatch.setattr(bonsai, '_PROCESS', None)
    monkeypatch.setattr(bonsai, 'model_list', lambda: False)
    monkeypatch.setattr(bonsai, 'verify_existing_runtime', Mock(side_effect=ValueError('Unverified')))
    spawn = Mock()
    monkeypatch.setattr(bonsai.subprocess, 'Popen', spawn)
    with pytest.raises(ValueError, match='Unverified'):
        bonsai.start_runtime()
    spawn.assert_not_called()

@pytest.mark.parametrize('change', ['', 'python', 'model', 'host', 'port'])
def test_existing_runtime_checks_native_loader_and_binding(monkeypatch, change):
    python = str(bonsai.RUNTIME / '.venv-vlm/bin/python')
    model = str(bonsai.MODEL_PATH)
    args = {'python': python, 'model': model, 'host': '127.0.0.1', 'port': '8081'}
    if change:
        args[change] = 'other'
    command = '{python} -m mlx_vlm.server --model {model} --host {host} --port {port} --max-tokens 8192'.format(**args)
    run = Mock(side_effect=[Mock(stdout='p55524\n'), Mock(stdout=command)])
    monkeypatch.setattr(bonsai.subprocess, 'run', run)
    if change:
        with pytest.raises(ValueError, match='nicht als eingerichteter Bonsai-Server'):
            bonsai.verify_existing_runtime()
    else:
        bonsai.verify_existing_runtime()

def test_unloaded_runtime_is_warmed_before_ready(monkeypatch):
    monkeypatch.setattr(bonsai, 'memory_available', lambda: True)
    monkeypatch.setattr(bonsai, 'start_runtime', Mock())
    monkeypatch.setattr(bonsai, 'model_list', Mock(side_effect=[False, True]))
    warm = Mock(return_value={})
    monkeypatch.setattr(bonsai, 'runtime_json', warm)
    model = bonsai.BonsaiModel()
    model._stop = Mock(is_set=Mock(return_value=False), wait=Mock(side_effect=[False, True]))
    model._run()
    assert model.snapshot()['readiness'] == 'ready'
    path, body = warm.call_args.args
    assert path == '/v1/chat/completions' and body['model'] == str(bonsai.MODEL_PATH)
    assert body['max_tokens'] == 1 and not body['enable_thinking']

def test_cancelled_warmup_never_becomes_ready(monkeypatch):
    monkeypatch.setattr(bonsai, 'memory_available', lambda: True)
    monkeypatch.setattr(bonsai, 'start_runtime', Mock())
    monkeypatch.setattr(bonsai, 'model_list', Mock(side_effect=[False, True]))
    model = bonsai.BonsaiModel()
    monkeypatch.setattr(bonsai, 'runtime_json', lambda *args, **kwargs: model._stop.set())
    model._run()
    assert model.snapshot()['readiness'] != 'ready'

@pytest.mark.parametrize('size,expected', [(20 * 1024**3, False), (6 * 1024**3, True)])
def test_parallel_model_memory_budget(monkeypatch, size, expected):
    monkeypatch.setattr(bonsai, 'local_json', lambda path: {'models': [{'size_vram': size}]})
    monkeypatch.setattr(bonsai.subprocess, 'run', Mock(return_value=Mock(stdout=str(32 * 1024**3))))
    model_path = MagicMock()
    model_path.__truediv__.return_value.stat.return_value.st_size = 8_600_000_000
    monkeypatch.setattr(bonsai, 'MODEL_PATH', model_path)
    assert bonsai.memory_available() is expected

def test_bonsai_waits_for_other_app_without_starting(monkeypatch):
    monkeypatch.setattr(bonsai, 'memory_available', lambda: False)
    start = Mock()
    monkeypatch.setattr(bonsai, 'start_runtime', start)
    model = bonsai.BonsaiModel()
    model._stop = Mock(wait=Mock(return_value=True))
    model._run()
    assert model.snapshot()['message'] == bonsai.MEMORY_MESSAGE
    start.assert_not_called()

def test_gpu_memory_failure_has_a_specific_safe_error():
    error = {'error': {'message': '[METAL] Insufficient Memory secret response content'}}
    with pytest.raises(bonsai.BonsaiMemoryError, match='Arbeitsspeicher') as caught:
        list(StreamAdapter(io.BytesIO(b'data: ' + json.dumps(error).encode() + b'\n')))
    assert 'secret' not in str(caught.value)

def test_memory_failure_stops_monitor_so_retry_can_restart():
    model = bonsai.BonsaiModel()
    model.set('error', 'Speicher fehlt')
    assert model._stop.is_set()

def test_chat_rejects_known_memory_conflict_before_inference(monkeypatch):
    monkeypatch.setattr('backend.tutor.memory_available', lambda: False)
    service = TutorService({'MLH_TUTOR_PROVIDER': 'bonsai', 'MLH_TUTOR_MODEL': MODEL}, transport=Mock())
    service.local = bonsai.BonsaiModel()
    with pytest.raises(HTTPException) as caught:
        service._local_check()
    assert caught.value.status_code == 503
    assert caught.value.detail == bonsai.MEMORY_MESSAGE
    assert service.local.snapshot()['readiness'] == 'error'
    service._transport.assert_not_called()

def line(delta=None, reason=None):
    return b'data: '+json.dumps({'choices':[{'delta':delta or {},'finish_reason':reason}]}).encode()+b'\n\n'

def test_stream_separates_thinking_and_text():
    raw=io.BytesIO(line({'reasoning_content':'Prüfen.'})+line({'content':'Antwort.'})+line(reason='stop')+b'data: [DONE]\n')
    adapter=StreamAdapter(raw)
    events=[json.loads(x) for x in adapter]
    assert events[0]['message']['thinking']=='Prüfen.'
    assert events[1]['message']['content']=='Antwort.' and events[-1]['done']
    adapter.close();assert raw.closed

@pytest.mark.parametrize('tail',[b'',line(reason='length'),b'data: [DONE]\n',b'data: {"error":"oops"}\n'])
def test_truncated_answer_never_completes(tail):
    with pytest.raises(ValueError):list(StreamAdapter(io.BytesIO(line({'content':'Halbe Antwort'})+tail)))

def test_bonsai_payload_is_loopback_and_keeps_context_bounded():
    service=TutorService({'MLH_TUTOR_PROVIDER':'bonsai','MLH_TUTOR_MODEL':MODEL},transport=Mock())
    service.local=Mock(thinking=True)
    request,shortened=service._prepare({'context_text':'ä'*24000},'Frage',[],stream=True,think=True)
    body=json.loads(request.data)
    assert request.full_url=='http://127.0.0.1:8081/v1/chat/completions'
    assert request.get_header('Authorization') is None
    assert body['enable_thinking'] and body['thinking_budget']==2048
    assert 'options' not in body and 'keep_alive' not in body
    assert shortened and sum(len(m['content'].encode()) for m in body['messages'])+body['max_tokens']+1024<=32768
    request,_=service._prepare({'context_text':'Text'},'Frage',[],think=False)
    assert not json.loads(request.data)['enable_thinking']

def test_incomplete_nonstream_is_rejected():
    service=TutorService({'MLH_TUTOR_PROVIDER':'bonsai','MLH_TUTOR_MODEL':MODEL},transport=Mock())
    with pytest.raises(HTTPException):service._answer({'choices':[{'finish_reason':'length','message':{'content':'Halbe Antwort'}}]})
    assert service._answer({'choices':[{'finish_reason':'stop','message':{'content':'Fertig'}}]})=='Fertig'

def test_bonsai_rejects_arbitrary_model():
    service=TutorService({'MLH_TUTOR_PROVIDER':'bonsai','MLH_TUTOR_MODEL':'some-other-model'},transport=Mock())
    assert not service.configured

class TestSwitch:
    def test_switch_does_not_unload_shared_ollama(self,tmp_path,monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.tutor import register_tutor_routes
        app=FastAPI();app.state.tutor=TutorService({'MLH_TUTOR_PROVIDER':'ollama','MLH_TUTOR_MODEL':'qwen'})
        model=tmp_path/'model';model.mkdir();(model/'model.safetensors').touch()
        monkeypatch.setattr('backend.tutor.BONSAI_PATH',model)
        monkeypatch.setattr(TutorService,'start',Mock())
        monkeypatch.setattr(TutorService,'stop',Mock())
        request=Mock()
        monkeypatch.setattr('backend.local_model.local_json',request)
        register_tutor_routes(app,None,tmp_path,tmp_path)
        response=TestClient(app).post('/api/tutor/model',json={'provider':'bonsai'})
        assert response.status_code==200
        request.assert_not_called()

    def test_busy_switch_does_not_change_configuration(self,tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.tutor import register_tutor_routes
        app=FastAPI();old=TutorService({'MLH_TUTOR_PROVIDER':'ollama','MLH_TUTOR_MODEL':'old'},transport=Mock())
        app.state.tutor=old
        register_tutor_routes(app,None,tmp_path,tmp_path)
        old._generation.acquire()
        response=TestClient(app).post('/api/tutor/model',json={'provider':'bonsai'})
        assert response.status_code==409
        assert not (tmp_path/'tutor.local.json').exists()
        old._generation.release()

    def test_switch_preserves_ollama_choice_and_persists(self,tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from backend.tutor import register_tutor_routes
        app=FastAPI();app.state.tutor=TutorService({'MLH_TUTOR_PROVIDER':'none'},transport=Mock())
        config=tmp_path/'tutor.local.json';config.write_text(json.dumps({'enabled':True,'model':'my-qwen'}))
        model=tmp_path/'model';model.mkdir();(model/'model.safetensors').touch()
        register_tutor_routes(app,None,tmp_path,tmp_path)
        client=TestClient(app)
        with patch('backend.tutor.BONSAI_PATH',model),patch('backend.tutor.TutorService.start'),patch('backend.tutor.TutorService.stop'):
            response=client.post('/api/tutor/model',json={'provider':'bonsai'})
            assert response.status_code==200 and response.json()['provider']=='bonsai'
            assert json.loads(config.read_text())['ollama_model']=='my-qwen'
            response=client.post('/api/tutor/model',json={'provider':'ollama'})
            assert response.json()['model']=='my-qwen'
        assert client.post('/api/tutor/model',json={'provider':'https://other-host'}).status_code==400
