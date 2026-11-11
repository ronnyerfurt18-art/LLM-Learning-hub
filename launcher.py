"""Double-click launcher: one Hub, local model service, owned-process cleanup."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import webbrowser

import uvicorn
from backend import local_model
from backend.local_model import local_json, NoRedirect
from urllib.request import build_opener, ProxyHandler

PROJECT = Path(__file__).resolve().parent
LAUNCHER_VERSION = 1

def project_id(project=PROJECT):
    return hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:24]

def hub_status(port):
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(f'http://127.0.0.1:{port}/api/health', timeout=2) as response:
            return json.loads(response.read(8192))
    except Exception:
        return {}

def is_our_hub(status):
    return (isinstance(status, dict) and status.get('application') == 'master-learning-hub'
            and status.get('project_id') == project_id()
            and status.get('launcher_version') == LAUNCHER_VERSION)

def configure():
    config_path = PROJECT / 'tutor.local.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config, dict) or set(config) - {'model', 'enabled', 'provider', 'ollama_model', 'context_tokens', 'bonsai_runtime', 'voice_runtime', 'study_folder', 'features'}:
        raise ValueError('tutor.local.json enthält unbekannte Einstellungen.')
    model = config.get('model', 'llama3.1:8b')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('In tutor.local.json fehlt ein gültiger Modellname.')
    if not isinstance(config.get('enabled', True), bool):
        raise ValueError('enabled muss true oder false sein.')
    provider = config.get('provider', 'ollama')
    if provider not in ('ollama', 'bonsai'): raise ValueError('Nur lokale Anbieter Ollama oder Bonsai sind erlaubt.')
    os.environ['MLH_TUTOR_PROVIDER'] = provider if config.get('enabled', True) else 'none'
    os.environ['MLH_TUTOR_MODEL'] = model
    os.environ['MLH_LAUNCHER_VERSION'] = str(LAUNCHER_VERSION)
    for key, variable in (('bonsai_runtime', 'MLH_BONSAI_RUNTIME'), ('voice_runtime', 'MLH_VOICE_RUNTIME'), ('study_folder', 'MLH_SOURCE_ROOT')):
        if key in config:
            if not isinstance(config[key], str) or not config[key].strip():
                raise ValueError(f'{key} in tutor.local.json muss ein Ordnerpfad sein.')
            os.environ[variable] = config[key]
    if 'features' in config:
        os.environ['MLH_FEATURES'] = ','.join(local_model.check_features(config['features'], 'features in tutor.local.json'))
    if 'context_tokens' in config:
        if type(config['context_tokens']) is not int or not 8192 <= config['context_tokens'] <= 131072:
            raise ValueError('context_tokens in tutor.local.json muss zwischen 8192 und 131072 liegen.')
        os.environ['MLH_CONTEXT_TOKENS'] = str(config['context_tokens'])
        # backend.local_model is already imported by this launcher; the hub modules read the value afterwards.
        local_model.CONTEXT_TOKENS = config['context_tokens']

def ensure_study_folder():
    """The default study folder is created on first start; a configured one must already exist."""
    configured = bool(os.environ.get('MLH_SOURCE_ROOT'))
    folder = local_model.study_folder(PROJECT).resolve()
    if folder == PROJECT.resolve() or PROJECT.resolve() in folder.parents:
        raise ValueError(f'Der Studienordner darf nicht im Programmordner liegen: {folder}')
    if not folder.is_dir():
        if configured and folder != (Path.home() / 'LearningHub' / 'Studium').resolve():
            raise ValueError(f'Studienordner nicht gefunden: {folder}. Bitte study_folder in tutor.local.json prüfen.')
        folder.mkdir(parents=True)
        print(f'Studienordner angelegt: {folder}', flush=True)
    os.environ['MLH_SOURCE_ROOT'] = str(folder)
    return folder

def ensure_ollama(log):
    try:
        if local_json('/api/version').get('version'):
            print('Vorhandenes Ollama wird verwendet.', flush=True)
            return None
    except Exception:
        pass
    binary = next((str(p) for p in [Path('/Applications/Ollama.app/Contents/Resources/ollama'),
                                   Path('/usr/local/bin/ollama'), Path('/opt/homebrew/bin/ollama')]
                   if p.is_file()), None) or shutil.which('ollama')
    if not binary:
        print('Ollama wurde nicht gefunden. Die Lernseiten starten ohne verfügbaren Tutor.', flush=True)
        return None
    env = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11434', 'OLLAMA_NO_CLOUD': '1', 'OLLAMA_NUM_PARALLEL': '1'}
    child = subprocess.Popen([binary, 'serve'], stdout=log, stderr=log, env=env, start_new_session=True)
    for _ in range(60):
        if child.poll() is not None:
            print('Ollama konnte nicht gestartet werden. Die Lernseiten bleiben nutzbar.', flush=True)
            return None
        try:
            if local_json('/api/version').get('version'):
                print('Ollama wurde gestartet.', flush=True)
                return child
        except Exception:
            time.sleep(.25)
    print('Ollama startet noch. Den Tutorstatus findest du auf der Lernseite.', flush=True)
    return child

def open_when_ready(port, stop):
    while not stop.wait(.5):
        if is_our_hub(hub_status(port)):
            webbrowser.open(f'http://localhost:{port}')
            return

def main():
    child = None
    stop = threading.Event()
    sock = None
    try:
        configure()
        print(f'Studienordner: {ensure_study_folder()}', flush=True)
        port = int(os.environ.get('MLH_PORT', '8000'))
        if not 1024 <= port <= 65535:
            raise ValueError('MLH_PORT muss zwischen 1024 und 65535 liegen.')
        lock_dir = Path(tempfile.gettempdir()) / f'master-learning-hub-{os.getuid()}'
        lock_dir.mkdir(mode=0o700, exist_ok=True)
        with (lock_dir / f'{project_id()}-{port}.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print('Die Lernseite läuft bereits oder startet gerade.', flush=True)
                for _ in range(20):
                    if is_our_hub(hub_status(port)):
                        if not os.environ.get('MLH_NO_BROWSER'):
                            webbrowser.open(f'http://localhost:{port}')
                        return 0
                    time.sleep(.5)
                print('Bitte das vorhandene Startfenster prüfen.', flush=True)
                return 0
            if is_our_hub(hub_status(port)):
                if not os.environ.get('MLH_NO_BROWSER'):
                    webbrowser.open(f'http://localhost:{port}')
                print('Vorhandene Lernseite geöffnet.', flush=True)
                return 0
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                raise ValueError(f'Port {port} ist bereits belegt. Bitte die bisherige Lernseite in ihrem Startfenster beenden und erneut starten. Andere Programme werden nicht beendet.')
            log_dir = Path(os.environ.get('MLH_DATA_DIR', str(PROJECT / 'data'))) / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / 'ollama-start.log').open('a') as log:
                if os.environ['MLH_TUTOR_PROVIDER'] == 'ollama':
                    child = ensure_ollama(log)
                print(f'\nLernseite: http://localhost:{port}\nZum Beenden in diesem Fenster Ctrl+C drücken.\nDas Modell wird im Hintergrund vorbereitet.', flush=True)
                if not os.environ.get('MLH_NO_BROWSER'):
                    threading.Thread(target=open_when_ready, args=(port, stop), daemon=True).start()
                server = uvicorn.Server(uvicorn.Config('backend.main:app', host='127.0.0.1', port=port, log_level='info'))
                server.run(sockets=[sock])
            return 0
    except (ValueError, OSError) as exc:
        print(f'Start nicht möglich: {exc}', flush=True)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        if sock:
            sock.close()
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)

if __name__ == '__main__':
    raise SystemExit(main())
