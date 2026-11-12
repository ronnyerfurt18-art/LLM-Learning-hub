"""Bonsai's pinned MLX runtime, loopback-only protocol adapter and owned process."""
import json
import os
import re
import subprocess
import threading
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from .local_model import NoRedirect, runtime_dir, local_json

BASE = 'http://127.0.0.1:8081'
MODEL = 'prism-ml/Ternary-Bonsai-2-27B-mlx-2bit'
RUNTIME = runtime_dir('bonsai-demo', 'MLH_BONSAI_RUNTIME')
MODEL_PATH = RUNTIME / 'models/Ternary-Bonsai-2-27B-mlx-2bit'
_PROCESS = None
_PROCESS_LOCK = threading.Lock()
MEMORY_MESSAGE = 'Bonsai wartet auf freien Arbeitsspeicher. Ein großes Ollama-Modell ist noch in einer anderen App geladen. Nach dessen Freigabe bitte erneut prüfen.'

class BonsaiMemoryError(ValueError):
    """A native GPU allocation failure, without exposing the provider response."""

def memory_available():
    """Leave room for native model buffers and macOS when Ollama is also loaded."""
    try:
        models = local_json('/api/ps').get('models', [])
        if not models:
            return True
        total = int(subprocess.run(['/usr/sbin/sysctl', '-n', 'hw.memsize'], check=True,
                                   capture_output=True, text=True, timeout=3).stdout.strip())
        used = sum(model.get('size_vram') or model.get('size') or 0 for model in models)
        # Weights alone exclude activation buffers, prefix cache and system memory.
        reserved = (MODEL_PATH / 'model.safetensors').stat().st_size * 1.6 + 4 * 1024 ** 3
        return used + reserved <= total
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return True  # Missing diagnostics must not require Ollama for Bonsai.

def runtime_json(path, body=None, timeout=3):
    request = Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw)>1024*1024: raise ValueError('Ungültige Modellliste.')
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('error'):
        raise ValueError('Die Bonsai-Laufzeit hat keine gültige Antwort geliefert.')
    return data

def model_list():
    data = runtime_json('/v1/models')
    if not isinstance(data.get('data'), list):
        raise ValueError('Ungültige Modellliste.')
    if not data['data']:
        return False
    ids = [m.get('id') for m in data.get('data',[]) if isinstance(m,dict)]
    if str(MODEL_PATH) not in ids and MODEL not in ids and MODEL_PATH.name not in ids:
        raise ValueError('Auf dem Bonsai-Port läuft ein anderes Modell. Bitte Port 8081 prüfen.')
    return True

def verify_existing_runtime():
    """Reuse only the configured native loader; a model name alone is insufficient."""
    try:
        listeners = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:8081', '-sTCP:LISTEN', '-Fp'],
                                   check=True, capture_output=True, text=True, timeout=3)
        pids = {line[1:] for line in listeners.stdout.splitlines() if line.startswith('p')}
        if len(pids) != 1:
            raise ValueError('Ambiguous listener')
        command = subprocess.run(['/bin/ps', '-ww', '-p', pids.pop(), '-o', 'command='],
                                 check=True, capture_output=True, text=True, timeout=3).stdout.strip()
        prefix = str(RUNTIME / '.venv-vlm/bin/python') + ' -m mlx_vlm.server '
        expected = {'model': str(MODEL_PATH), 'host': '127.0.0.1', 'port': '8081'}
        if not command.startswith(prefix) or not all(
                re.search(r'(?:^| )--' + key + ' ' + re.escape(value) + r'(?= --|$)', command)
                for key, value in expected.items()):
            raise ValueError('Unknown loader')
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError('Port 8081 ist belegt. Die dortige Laufzeit konnte nicht als eingerichteter Bonsai-Server bestätigt werden.')

def start_runtime():
    global _PROCESS
    with _PROCESS_LOCK:
        if _PROCESS and _PROCESS.poll() is None: return
        try:
            model_list()
            verify_existing_runtime()
            return
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
        if state == 'error':self._stop.set()
    def start(self):
        if self._thread and self._thread.is_alive():
            if not self._stop.is_set():return
            self._thread.join(timeout=4)
            if self._thread.is_alive():return
        self._stop.clear();self.set('starting','Bonsai wird lokal geladen …')
        self._thread=threading.Thread(target=self._run,daemon=True);self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=4)
        stop_runtime()
    def _run(self):
        try:
            while not memory_available():
                self.set('starting', MEMORY_MESSAGE)
                if self._stop.wait(10):return
            if self._stop.is_set():return
            start_runtime()
            for _ in range(150):
                if self._stop.is_set():return
                try:
                    if model_list():break
                except ValueError:raise
                except Exception:
                    if _PROCESS and _PROCESS.poll() is not None:raise ValueError('Bonsai konnte nicht starten. Bitte Laufzeitprotokoll prüfen.')
                    if self._stop.wait(2):return
                    continue
                if self._stop.is_set():return
                # Unload leaves the native server alive with an empty model list.
                runtime_json('/v1/chat/completions', {
                    'model': str(MODEL_PATH), 'messages': [{'role': 'user', 'content': 'Hallo'}],
                    'stream': False, 'max_tokens': 1, 'enable_thinking': False,
                }, timeout=300)
                if self._stop.wait(2):return
            else:raise ValueError('Bonsai benötigt zu lange zum Laden. Bitte erneut prüfen.')
            if self._stop.is_set():return
            self.set('ready','Bonsai ist bereit. Die Verarbeitung bleibt auf deinem Mac.')
            while not self._stop.wait(10):
                if not model_list():
                    raise ValueError('Bonsai wurde entladen. Bitte erneut prüfen, um das Modell wieder zu laden.')
        except Exception as exc:
            self.set('error',str(exc) if isinstance(exc,ValueError) else 'Bonsai ist nicht erreichbar. Bitte erneut prüfen.')

class StreamAdapter:
    """Convert the MLX SSE stream into the tutor's established NDJSON protocol.

    The closing line carries the runtime's own usage and timings, when it sent them."""
    def __init__(self,response):self.response=response
    def close(self):self.response.close()
    def __iter__(self):
        total=0;finished=False;stats={}
        for raw in self.response:
            total+=len(raw)
            if total>8*1024*1024:raise ValueError('Bonsai stream too large')
            line=raw.strip()
            if not line or line.startswith(b':'):continue
            if not line.startswith(b'data:'):continue
            data=line[5:].strip()
            if data==b'[DONE]':
                if not finished:raise ValueError('Missing completion reason')
                break
            event=json.loads(data)
            if event.get('error'):
                error = json.dumps(event['error']).lower()
                if any(marker in error for marker in ('insufficient memory', 'out of memory', 'outofmemory')):
                    raise BonsaiMemoryError('Bonsai benötigt mehr freien Arbeitsspeicher. Bitte das große Modell in der anderen App freigeben und erneut prüfen.')
                raise ValueError('Bonsai stream error')
            # Usage and timings follow the last text chunk in a chunk without choices.
            for key in ('usage','timings'):
                if isinstance(event.get(key),dict):stats[key]=event[key]
            choices=event.get('choices',[])
            if not choices or finished:continue
            choice=choices[0];delta=choice.get('delta') or {};reason=choice.get('finish_reason')
            if reason in ('length','content_filter','tool_calls'):raise ValueError('Bonsai answer incomplete')
            if reason not in (None,'stop'):raise ValueError('Unknown finish reason')
            finished=reason=='stop'
            message={'content':delta.get('content') or '', 'thinking':delta.get('reasoning_content') or delta.get('reasoning') or ''}
            if message['content'] or message['thinking']:
                yield json.dumps({'message':message,'done':False},ensure_ascii=False).encode()
        if not finished:raise ValueError('Bonsai stream ended before completion')
        yield json.dumps({'message':{'content':'','thinking':''},'done':True,**stats},ensure_ascii=False).encode()
