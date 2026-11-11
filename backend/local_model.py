"""Local-only Ollama readiness; no downloads, proxies or redirects."""
import json
import os
import threading
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

BASE = 'http://127.0.0.1:11434'
DEFAULT_CONTEXT_TOKENS = 32768


def context_tokens(value=None):
    """Context window for local models; MLH_CONTEXT_TOKENS lowers it on machines with little memory."""
    raw = os.environ.get('MLH_CONTEXT_TOKENS', '') if value is None else value
    try:
        number = int(str(raw).strip()) if str(raw).strip() else DEFAULT_CONTEXT_TOKENS
    except ValueError:
        return DEFAULT_CONTEXT_TOKENS
    return max(8192, min(131072, number))


def runtime_dir(name, variable):
    """Folder of an optional local runtime (Bonsai, voice): environment variable or ~/.learning-hub/runtimes."""
    return Path(os.environ.get(variable) or Path.home() / '.learning-hub' / 'runtimes' / name).expanduser()


def study_folder(project=None):
    """Folder with the study documents: MLH_SOURCE_ROOT, then study_folder in tutor.local.json, then ~/LearningHub/Studium.

    It is never derived from where the project happens to be stored, so a fresh copy cannot index neighbouring folders.
    """
    configured = os.environ.get('MLH_SOURCE_ROOT')
    if not configured and project is not None:
        try:
            value = json.loads((Path(project) / 'tutor.local.json').read_text(encoding='utf-8')).get('study_folder')
            configured = value if isinstance(value, str) and value.strip() else None
        except (OSError, ValueError, AttributeError):
            configured = None
    return Path(configured or Path.home() / 'LearningHub' / 'Studium').expanduser()


FEATURES = ('voice', 'module_import', 'big_picture', 'development')


def check_features(items, where='features'):
    """Known feature names in a fixed order; anything else is an error the person can read."""
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError(f'{where} muss eine Liste von Namen sein. Bekannt: {", ".join(FEATURES)}.')
    unknown = sorted({item for item in items if item not in FEATURES})
    if unknown:
        raise ValueError(f'{where} enthält unbekannte Werte: {", ".join(unknown)}. Bekannt: {", ".join(FEATURES)}.')
    return [name for name in FEATURES if name in items]


def active_features(environ=None):
    """Features the hub offers: MLH_FEATURES (comma separated, set by the launcher); not set means all of them."""
    raw = (os.environ if environ is None else environ).get('MLH_FEATURES')
    if raw is None:
        return list(FEATURES)
    return check_features([item.strip() for item in raw.split(',') if item.strip()], 'MLH_FEATURES')


CONTEXT_TOKENS = context_tokens()
KEEP_ALIVE = '15m'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def local_json(path, body=None, timeout=3):
    request = Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Ollama response too large')
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get('error'):
        raise ValueError('Invalid Ollama response')
    return result

def local_model_info(model, request=local_json):
    models = request('/api/tags').get('models', [])
    match = next((item for item in models if isinstance(item, dict) and item.get('name') == model), None)
    if not match:
        raise ValueError('Das gewählte Modell ist nicht lokal vorhanden. Bitte den Modellnamen in tutor.local.json prüfen.')
    info = request('/api/show', {'model': model})
    if match.get('remote_model') or match.get('remote_host') or info.get('remote_model') or info.get('remote_host'):
        raise ValueError('Dieser Starter verwendet ausschließlich lokale Modelle. Bitte ein heruntergeladenes Modell wählen.')
    if 'completion' not in info.get('capabilities', []):
        raise ValueError('Das gewählte Modell unterstützt keinen Text-Lernchat.')
    return info

class LocalModel:
    def __init__(self, model, request=local_json):
        self.model, self.request = model, request
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.state, self.message = 'starting', 'Das lokale Modell wird vorbereitet …'
        self.thinking = False

    def snapshot(self):
        with self._lock:
            return {'readiness': self.state, 'message': self.message, 'thinking': self.thinking}

    def set(self, state, message):
        with self._lock:
            self.state, self.message = state, message

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self.state, self.message = 'starting', 'Das lokale Modell wird geladen. Die Lernseiten kannst du bereits nutzen.'
            self._thread = threading.Thread(target=self._run, name='local-tutor-model', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            info = local_model_info(self.model, self.request)
            self.thinking = 'thinking' in info.get('capabilities', [])
            payload = {'model': self.model, 'messages': [], 'stream': False,
                       'keep_alive': KEEP_ALIVE, 'options': {'num_ctx': CONTEXT_TOKENS}}
            if self.thinking:
                payload['think'] = False
            result = self.request('/api/chat', payload, timeout=180)
            if result.get('done') is not True:
                raise ValueError('Das Modell konnte nicht vollständig geladen werden. Bitte erneut prüfen.')
            self.set('ready', 'Tutor bereit. Deine Fragen und der ausgewählte Lernkontext werden lokal verarbeitet.')
        except ValueError as exc:
            self.set('error', str(exc) if str(exc).startswith(('Das ', 'Dieser ')) else 'Ollama hat keine gültige Antwort geliefert. Bitte erneut prüfen.')
            return
        except Exception:
            self.set('error', 'Ollama ist nicht erreichbar oder das Laden dauerte zu lange. Bitte „Start.command“ öffnen und erneut prüfen.')
            return
        while not self._stop.wait(10):
            try:
                version = self.request('/api/version')
                models = self.request('/api/tags').get('models', [])
                if not version.get('version') or not any(m.get('name') == self.model for m in models):
                    raise ValueError('Model unavailable')
            except Exception:
                self.set('error', 'Die lokale Modellverbindung ist unterbrochen. Bitte Ollama starten und erneut prüfen.')
                return
