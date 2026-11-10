"""Bonsai's pinned MLX runtime, loopback-only protocol adapter and owned process."""
import json
import os
import subprocess
import threading
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from .local_model import NoRedirect, runtime_dir

BASE = 'http://127.0.0.1:8081'
MODEL = 'prism-ml/Ternary-Bonsai-2-27B-mlx-2bit'
RUNTIME = runtime_dir('bonsai-demo', 'MLH_BONSAI_RUNTIME')
MODEL_PATH = RUNTIME / 'models/Ternary-Bonsai-2-27B-mlx-2bit'
_PROCESS = None
_PROCESS_LOCK = threading.Lock()

def model_list():
    request = Request(BASE + '/v1/models')
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=3) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw)>1024*1024: raise ValueError('Ungültige Modellliste.')
    data = json.loads(raw)
    ids = [m.get('id') for m in data.get('data',[]) if isinstance(m,dict)]
    if str(MODEL_PATH) not in ids and MODEL not in ids and MODEL_PATH.name not in ids:
        raise ValueError('Auf dem Bonsai-Port läuft ein anderes Modell. Bitte Port 8081 prüfen.')
    return True

def start_runtime():
    global _PROCESS
    with _PROCESS_LOCK:
        if _PROCESS and _PROCESS.poll() is None: return
        try:
            model_list()
            raise ValueError('Port 8081 wird bereits verwendet. Bitte den dortigen Server beenden, damit die geprüfte Bonsai-Laufzeit starten kann.')
        except ValueError:
            raise
        except Exception:
            pass
        if not (MODEL_PATH/'model.safetensors').exists():
            raise ValueError('Bonsai ist noch nicht vollständig heruntergeladen.')
        python = RUNTIME/'.venv-vlm/bin/python'
        if not python.is_file(): raise ValueError('Die Bonsai-Laufzeit ist noch nicht installiert.')
        # Match the manufacturer's native loader and dependency set, never generic mlx-lm.
        subprocess.run([str(python),str(RUNTIME/'scripts/check_mlx_vlm.py')],check=True,timeout=20,capture_output=True)
        logs=RUNTIME/'logs';logs.mkdir(exist_ok=True)
        with (logs/'learning-hub.log').open('ab') as log:
            _PROCESS=subprocess.Popen(['sh',str(RUNTIME/'scripts/start_mlx_server.sh'),'--thinking-budget','2048','--max-tokens','8192'],cwd=RUNTIME,
                env={**os.environ,'PORT':'8081','BONSAI_MODEL':'27B','BONSAI_FAMILY':'bonsai2','HF_HUB_OFFLINE':'1',
                     # Prefix-Cache: Lernkontext bei Folgefragen wiederverwenden, statt ihn neu zu lesen.
                     # Checkpoints alle 512 Tokens (rekurrente Schichten lassen sich nur dort fortsetzen); nur im RAM.
                     'APC_ENABLED':'1','APC_CHECKPOINT_INTERVAL_TOKENS':'512','APC_DISK_ENABLED':'0'},stdout=log,stderr=log,start_new_session=True)

def stop_runtime():
    global _PROCESS
    with _PROCESS_LOCK:
        if _PROCESS and _PROCESS.poll() is None:
            _PROCESS.terminate()
            try: _PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired: _PROCESS.kill(); _PROCESS.wait(timeout=3)
        _PROCESS=None

class BonsaiModel:
    thinking=True
    def __init__(self):
        self._stop=threading.Event();self._thread=None;self._lock=threading.Lock()
        self.state='starting';self.message='Bonsai wird vorbereitet …'
    def snapshot(self):
        with self._lock:return {'readiness':self.state,'message':self.message,'thinking':True}
    def set(self,state,message):
        with self._lock:self.state,self.message=state,message
    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear();self.set('starting','Bonsai wird lokal geladen …')
        self._thread=threading.Thread(target=self._run,daemon=True);self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=4)
        stop_runtime()
    def _run(self):
        try:
            start_runtime()
            for _ in range(150):
                if self._stop.is_set():return
                try:model_list();break
                except ValueError:raise
                except Exception:
                    if _PROCESS and _PROCESS.poll() is not None:raise ValueError('Bonsai konnte nicht starten. Bitte Laufzeitprotokoll prüfen.')
                if self._stop.wait(2):return
            else:raise ValueError('Bonsai benötigt zu lange zum Laden. Bitte erneut prüfen.')
            self.set('ready','Bonsai ist bereit. Die Verarbeitung bleibt auf deinem Mac.')
            while not self._stop.wait(10):model_list()
        except Exception as exc:
            self.set('error',str(exc) if isinstance(exc,ValueError) else 'Bonsai ist nicht erreichbar. Bitte erneut prüfen.')

class StreamAdapter:
    """Convert the MLX SSE stream into the tutor's established NDJSON protocol."""
    def __init__(self,response):self.response=response
    def close(self):self.response.close()
    def __iter__(self):
        total=0;finished=False
        for raw in self.response:
            total+=len(raw)
            if total>8*1024*1024:raise ValueError('Bonsai stream too large')
            line=raw.strip()
            if not line or line.startswith(b':'):continue
            if not line.startswith(b'data:'):continue
            data=line[5:].strip()
            if data==b'[DONE]':
                if not finished:raise ValueError('Missing completion reason')
                return
            event=json.loads(data)
            if event.get('error'):raise ValueError('Bonsai stream error')
            choices=event.get('choices',[])
            if not choices:continue
            choice=choices[0];delta=choice.get('delta') or {};reason=choice.get('finish_reason')
            if reason in ('length','content_filter','tool_calls'):raise ValueError('Bonsai answer incomplete')
            if reason not in (None,'stop'):raise ValueError('Unknown finish reason')
            finished=reason=='stop'
            message={'content':delta.get('content') or '', 'thinking':delta.get('reasoning_content') or delta.get('reasoning') or ''}
            yield json.dumps({'message':message,'done':finished},ensure_ascii=False).encode()
            if finished:return
        if not finished:raise ValueError('Bonsai stream ended before completion')
