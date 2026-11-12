"""Development as a conversation: one task in, one verdict out.

`ask` files a request and lets the hub carry it as far as it can alone: draft the order, rate it, and (if local) have the model propose
the change. After the person approved the change, `verify` runs fixed commands (never anything the model wrote) and records whether the
interface builds and the tests of the touched code pass. Whether a change is done is then read off `development.outcome`.
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import HTTPException

from .development import MODEL_NEEDED, OUTPUT_TOKENS, SCHEMA, _now, logged, ollama_generator, local_json
from .development_change import OUTPUT_TOKENS as CHANGE_TOKENS, SCHEMA as CHANGE_SCHEMA, WORKING

COMMAND_SECONDS = 170
TAIL_CHARS = 1200
BUILDING = 'Der Hub baut die Oberfläche (npm run build) …'
TESTING = 'Der Hub lässt die Tests der geänderten Dateien laufen …'
EXTERNAL = 'Das lässt sich nicht lokal lösen. Der Prompt für eine externe KI liegt bereit.'


def run_command(command, cwd, timeout=COMMAND_SECONDS):
    """(exit code, last lines of output). Only called with the fixed commands below."""
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f'Abgebrochen nach {timeout} Sekunden.'
    except OSError as exc:
        return 127, f'Befehl nicht gestartet: {exc}'
    return done.returncode, ((done.stdout or '') + (done.stderr or '')).strip()[-TAIL_CHARS:]


class Flow:
    def __init__(self, app, job, change):
        self.app, self.job, self.change = app, job, change

    def _runner(self):
        return getattr(self.app.state, 'development_run', None) or run_command

    def run_flow(self, request_id, model, generate, gate=None):
        """Job body: order, rating, and for a local order the proposal. `generate` is the pair (order model, change model)."""
        job = self.job
        order_generate, change_generate = generate
        job.run(request_id, model, order_generate, gate)
        if job.status()['state'] == 'error':
            return job.status()
        if job.get(request_id)['order']['route'] != 'local':
            job._update(state='done', finished_at=_now(), message=EXTERNAL)
            return job.status()
        try:
            self.change.check(request_id)
        except (HTTPException, ValueError) as exc:
            job._update(state='error', finished_at=_now(), message=getattr(exc, 'detail', None) or str(exc))
            return job.status()
        job._update(state='running', message=WORKING)
        return self.change.run(request_id, model, change_generate, gate)

    def verify_run(self, request_id, model=None, generate=None, gate=None):
        """Job body: build and test what the approved change touched, fixed commands only."""
        job, run = self.job, self._runner()
        try:
            request = job.get(request_id)
            proposal = request.get('proposal') or {}
            paths = [item['path'] for item in proposal.get('applied_files') or []]
            steps = []
            if any(path.startswith('frontend/') for path in paths):
                job._update(message=BUILDING)
                if shutil.which('npm') is None and getattr(self.app.state, 'development_run', None) is None:
                    steps.append({'name': 'Oberfläche bauen', 'ok': False, 'detail': 'Der Befehl „npm“ wurde nicht gefunden.'})
                else:
                    code, tail = run(['npm', 'run', 'build'], Path(job.project) / 'frontend')
                    steps.append({'name': 'Oberfläche bauen', 'ok': code == 0, 'detail': '' if code == 0 else tail})
            if any(path.endswith('.py') for path in paths):
                job._update(message=TESTING)
                tests = [path for path in (request.get('order') or {}).get('tests') or []
                         if str(path).endswith('.py') and (Path(job.project) / path).is_file()] or ['tests']
                if importlib.util.find_spec('pytest') is None and getattr(self.app.state, 'development_run', None) is None:
                    steps.append({'name': 'Tests', 'ok': None, 'detail': 'pytest ist hier nicht installiert, die Tests sind nicht gelaufen.'})
                else:
                    code, tail = run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests], job.project)
                    steps.append({'name': 'Tests', 'ok': code == 0, 'detail': '' if code == 0 else tail})
            if not steps:
                steps.append({'name': 'Prüfung', 'ok': None, 'detail': 'Für diese Dateien gibt es nichts zu bauen oder zu testen.'})
            words = {True: 'bestanden', False: 'fehlgeschlagen', None: 'nicht geprüft'}
            event = 'Prüfung: ' + '; '.join(f"{step['name']} {words[step['ok']]}" for step in steps)
            failed = any(step['ok'] is False for step in steps)
            job.change(request_id, lambda stored: {**stored, **logged(stored, event), 'updated_at': _now(),
                                                   'proposal': {**stored['proposal'], 'verify': {'at': _now(), 'steps': steps}}})
            job._update(state='error' if failed else 'done', finished_at=_now(),
                        message='Die Prüfung ist fehlgeschlagen.' if failed else 'Die Prüfung ist durchgelaufen.')
        except Exception as exc:
            message = str(exc).strip("'") if isinstance(exc, (ValueError, KeyError)) else f'Unerwarteter Fehler: {type(exc).__name__}'
            job._update(state='error', finished_at=_now(), message=message)
        return job.status()


def register_development_flow_routes(app, project_root):
    """Needs the routes of `development` and `development_change`."""
    job, change = app.state.development, app.state.development_change
    flow = app.state.development_flow = Flow(app, job, change)

    @app.post('/api/development/ask', status_code=202)
    def development_ask(value: dict):
        tutor = app.state.tutor
        if not (tutor.provider == 'ollama' and tutor.configured):
            raise HTTPException(503, MODEL_NEEDED)
        order_generate = getattr(app.state, 'development_generate', None)
        change_generate = getattr(app.state, 'development_change_generate', None)
        try:
            order_generate = order_generate or ollama_generator(tutor.model, local_json, SCHEMA, OUTPUT_TOKENS)
            change_generate = change_generate or ollama_generator(tutor.model, local_json, CHANGE_SCHEMA, CHANGE_TOKENS)
        except ValueError as exc:
            raise HTTPException(503, str(exc))
        except OSError:
            raise HTTPException(503, 'Ollama ist nicht erreichbar. Bitte „Start.command“ öffnen und erneut versuchen.')
        status = job.status()
        if status['state'] == 'running':
            raise HTTPException(409, 'Der Hub arbeitet gerade an einer anderen Aufgabe. Bitte warte, bis sie fertig ist.')
        request = job.add({'text': value.get('text', '')})
        job.start(request['id'], tutor.model, (order_generate, change_generate), tutor._generation, run=flow.run_flow, kind='flow',
                  message='Das KI-Modell liest deine Aufgabe …')
        return {'id': request['id'], 'job': job.status()}

    @app.post('/api/development/requests/{request_id}/verify', status_code=202)
    def development_verify(request_id: str):
        if (job.get(request_id).get('proposal') or {}).get('state') != 'applied':
            raise HTTPException(409, 'Es gibt keine übernommene Änderung, die sich prüfen lässt.')
        job.start(request_id, '', None, None, run=flow.verify_run, kind='verify', message='Der Hub prüft die Änderung …')
        return job.status()
