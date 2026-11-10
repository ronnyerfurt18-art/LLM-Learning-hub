import io,json
import pytest
from unittest.mock import Mock
from fastapi import HTTPException
from backend.bonsai import StreamAdapter, MODEL
from backend.tutor import TutorService

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
