#!/usr/bin/env python3
"""Resume a local, source-frozen model comparison during an idle night window.

No learner data or provider selection is changed. Shared runtimes must become
idle first. Each response is fsynced independently so interruption is recoverable.
"""
import argparse
import fcntl
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import bench_tutor_models as bench

MODELS = [('bonsai', 'prism-ml/Ternary-Bonsai-2-27B-mlx-2bit'),
          ('ollama', 'qwen3.8:27b-mlx'), ('ollama', 'qwen3.5:9b')]


def get(url):
    with bench.OPENER.open(url, timeout=10) as response:
        return json.load(response)


def append(path, value):
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        output.flush()
        os.fsync(output.fileno())


def save(path, value):
    pending = path.with_suffix('.pending')
    with pending.open('w', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    pending.replace(path)


def records(path):
    if not path.exists():
        return []
    # A partial trailing line is an interrupted write, never a completed response.
    rows = []
    for raw in path.read_text().splitlines():
        try:
            rows.append(json.loads(raw))
        except ValueError:
            raise RuntimeError('Incomplete JSONL record. Preserve and repair before resuming: ' + str(path))
    return rows


def completed(rows):
    return {(row['model'], row['question_id'], row['repetition']) for row in rows
            if row.get('type') == 'result' and not row.get('error') and row.get('answer')}


class NightRun:
    def __init__(self, args):
        self.args = args
        self.suite = json.loads(args.suite.read_text())
        self.digest = hashlib.sha256(args.suite.read_bytes()).hexdigest()
        self.path = args.output / 'responses.jsonl'
        self.events = args.output / 'events.jsonl'
        self.owned_ollama = None
        self.owned_bonsai = False
        self.expected_expiry = None
        self.last_bonsai_request = None

    def event(self, kind, **data):
        item = {'time': datetime.now().astimezone().isoformat(), 'event': kind, **data}
        append(self.events, item)
        print(json.dumps(item, ensure_ascii=False), flush=True)

    def check_deadline(self):
        if datetime.now().astimezone() >= self.args.deadline:
            raise TimeoutError('Night window ended. Completed responses remain resumable.')

    def wait_for_idle(self):
        """Wait for Ollama's natural unload and five minutes without Bonsai work."""
        reported = False
        while True:
            self.check_deadline()
            try:
                ollama = get(bench.OLLAMA + '/api/ps')['models']
                metrics = get(bench.BONSAI + '/metrics')
                summary = metrics['summary']
                last = summary.get('last_request_at') or 0
                idle_since = last == self.last_bonsai_request or time.time() - last >= 300
                if not ollama and summary.get('in_flight') == 0 and idle_since:
                    self.event('runtimes_idle')
                    return
                if not reported:
                    self.event('waiting_for_other_apps', ollama_models=[m['name'] for m in ollama],
                               bonsai_in_flight=summary.get('in_flight'))
                    reported = True
            except (OSError, ValueError, KeyError) as error:
                if not reported:
                    self.event('waiting_for_runtime', error=str(error))
                    reported = True
            time.sleep(30)

    def assert_exclusive(self):
        self.check_deadline()
        models = get(bench.OLLAMA + '/api/ps')['models']
        if self.owned_ollama:
            if any(model['name'] != self.owned_ollama for model in models):
                raise RuntimeError('Another Ollama model appeared. Shared runtime left untouched.')
            if models and self.expected_expiry is not None and models[0].get('expires_at') != self.expected_expiry:
                raise RuntimeError('Another Ollama request changed model activity. Shared runtime left untouched.')
        elif models:
            raise RuntimeError('Another app loaded Ollama. Shared runtime left untouched.')
        metrics = get(bench.BONSAI + '/metrics')['summary']
        if metrics.get('in_flight') != 0:
            raise RuntimeError('Bonsai is serving another request. Shared runtime left untouched.')
        if self.last_bonsai_request is not None and metrics.get('last_request_at') != self.last_bonsai_request:
            raise RuntimeError('Another Bonsai request was detected. Shared runtime left untouched.')

    def unload(self):
        self.assert_exclusive()
        if self.owned_ollama:
            with bench.post(bench.OLLAMA + '/api/generate', {'model': self.owned_ollama, 'keep_alive': 0}) as response:
                result = json.load(response)
            if result.get('done') is not True:
                raise RuntimeError('Ollama unload was not confirmed')
            self.owned_ollama = None
            self.expected_expiry = None
        loaded = get(bench.BONSAI + '/health').get('loaded_model')
        expected = str(bench.bonsai_runtime() / 'models/Ternary-Bonsai-2-27B-mlx-2bit')
        if loaded and loaded not in (expected, MODELS[0][1], Path(expected).name):
            raise RuntimeError('Another model occupies the Bonsai server. Shared runtime left untouched.')
        if self.owned_bonsai or loaded:
            with bench.post(bench.BONSAI + '/unload', {}) as response:
                result = json.load(response)
            if result.get('status') not in ('success', 'no_model_loaded'):
                raise RuntimeError('Bonsai unload was not confirmed')
            self.owned_bonsai = False
        self.event('models_unloaded')

    def infer(self, provider, model, messages, limit):
        self.assert_exclusive()
        result = bench.run_bonsai(messages, limit) if provider == 'bonsai' else bench.run_ollama(model, messages, limit)
        if provider == 'ollama':
            self.owned_ollama = model
            models = get(bench.OLLAMA + '/api/ps')['models']
            self.expected_expiry = next((m.get('expires_at') for m in models if m['name'] == model), None)
        else:
            self.owned_bonsai = True
        self.last_bonsai_request = get(bench.BONSAI + '/metrics')['summary'].get('last_request_at')
        return result

    def comparison(self):
        done = completed(records(self.path))
        questions = self.suite['questions']
        for start in range(0, len(questions), 3):
            # Rotate model order between topics to distribute thermal/order effects.
            offset = (start // 3) % len(MODELS)
            for provider, model in MODELS[offset:] + MODELS[:offset]:
                pending = [(question, repetition) for question in questions[start:start + 3]
                           for repetition in (1, 2) if (model, question['id'], repetition) not in done]
                if not pending:
                    continue
                self.wait_for_idle()
                self.last_bonsai_request = None
                self.unload()
                previous_question = None
                for question, repetition in pending:
                    identical_repeat = repetition == 2 and previous_question == question['id']
                    if not identical_repeat:
                        self.unload()
                    self.event('request_started', model=model, question=question['id'], repetition=repetition)
                    row = {'type': 'result', 'provider': provider, 'model': model,
                           'question_id': question['id'], 'category': question['category'],
                           'repetition': repetition, 'prompt_sha256': question['prompt_sha256'],
                           'cache_condition': 'identical_repeat' if identical_repeat else 'after_unload',
                           'quality_review': None, 'thermal_before': bench.thermal_snapshot()}
                    row.update(self.infer(provider, model, question['messages'], 1400))
                    row['thermal_after'] = bench.thermal_snapshot()
                    append(self.path, row)
                    previous_question = question['id']
                    self.report('running')
                    self.event('request_completed', model=model, question=question['id'], repetition=repetition,
                               first=row['first'], truncated=row['truncated'])
                    time.sleep(self.args.cooldown)
                self.unload()

    def hub_smoke(self):
        """Verify the actual tutor stream after other apps have released memory."""
        path = self.args.output / 'hub-smoke.json'
        if path.exists():
            return
        base = 'http://127.0.0.1:8000'
        if get(base + '/api/tutor/status').get('provider') != 'bonsai':
            self.event('hub_smoke_skipped', reason='User selected another provider')
            return
        self.wait_for_idle()
        with bench.post(base + '/api/tutor/retry', {}) as response:
            json.load(response)
        while True:
            self.check_deadline()
            status = get(base + '/api/tutor/status')
            if status.get('provider') != 'bonsai':
                raise RuntimeError('User changed the hub provider during verification')
            if status.get('readiness') == 'ready':
                break
            if status.get('readiness') == 'error':
                raise RuntimeError('Hub failed to prepare Bonsai: ' + status.get('message', ''))
            time.sleep(10)
        final = None
        with bench.post(base + '/api/tutor/chat/stream', self.suite['questions'][0]['request']) as response:
            for raw in response:
                if not raw.strip():
                    continue
                event = json.loads(raw)
                if event.get('type') == 'error':
                    raise RuntimeError('Hub verification failed: ' + event.get('detail', ''))
                if event.get('type') == 'done':
                    final = event
        if not final or not final.get('answer') or not isinstance(final.get('performance'), dict):
            raise RuntimeError('Hub stream did not finish with an answer and performance values')
        save(path, final)
        self.owned_bonsai = True
        self.last_bonsai_request = get(bench.BONSAI + '/metrics')['summary'].get('last_request_at')
        self.event('hub_smoke_completed', provider=final.get('provider'), model=final.get('model'))

    def preload(self):
        path = self.args.output / 'preload.jsonl'
        previous = {(row['pair'], row['preloaded']) for row in records(path)}
        question = self.suite['questions'][0]
        model = 'qwen3.8:27b-mlx'
        for pair in range(3):
            # Alternate treatment order, with a fresh model and cache for each arm.
            for preloaded in ((False, True) if pair % 2 == 0 else (True, False)):
                if (pair, preloaded) in previous:
                    continue
                self.wait_for_idle()
                self.last_bonsai_request = None
                self.unload()
                self.infer('ollama', model, [{'role': 'user', 'content': 'Hallo'}], 1)
                preload_result = None
                if preloaded:
                    preload_result = self.infer('ollama', model, question['messages'][:-1], 1)
                result = self.infer('ollama', model, question['messages'], 1400)
                append(path, {'pair': pair, 'preloaded': preloaded, 'model': model,
                              'question_id': question['id'], 'preload': preload_result, 'result': result})
                self.unload()
                time.sleep(self.args.cooldown)

    def report(self, state, error=None):
        rows = [row for row in records(self.path) if row.get('type') == 'result']
        summary = []
        for provider, model in MODELS:
            selected = [row for row in rows if row.get('model') == model]
            times = [row['first'] for row in selected if isinstance(row.get('first'), (int, float))]
            summary.append({'model': model, 'responses': len(selected),
                            'truncated': sum(bool(row.get('truncated')) for row in selected),
                            'median_first_seconds': statistics.median(times) if times else None})
        save(self.args.output / 'status.json', {'state': state, 'error': error,
             'time': datetime.now().astimezone().isoformat(), 'completed_responses': len(rows),
             'expected_responses': len(self.suite['questions']) * 2 * len(MODELS),
             'models': summary, 'quality_review': 'pending source-grounded human/agent review',
             'limits': 'Other applications may race with idle checks. Inspect events and raw timings before comparing.'})
        if state in ('scheduled', 'running', 'waiting'):
            return
        # Keep the evaluator package separate from provider labels and leave scores blank.
        import random
        blinded = [{key: row[key] for key in ('question_id', 'repetition', 'answer', 'truncated')} for row in rows]
        random.Random(self.digest).shuffle(blinded)
        save(self.args.output / 'blinded-review.json', {'rubric': self.suite['rubric'],
             'questions': self.suite['questions'], 'responses': blinded,
             'review_status': 'unscored; original sources must be checked'})

    def run(self):
        self.args.output.mkdir(parents=True, exist_ok=True)
        manifest = self.args.output / 'manifest.json'
        if manifest.exists():
            if json.loads(manifest.read_text())['suite_sha256'] != self.digest:
                raise ValueError('Suite changed. Use a new output directory.')
        else:
            save(manifest, {'suite_sha256': self.digest, 'suite': str(self.args.suite),
                 'not_before': self.args.not_before.isoformat(), 'deadline': self.args.deadline.isoformat(),
                 'cooldown_seconds': self.args.cooldown, 'max_tokens': 1400, 'repeats': 2,
                 'sampling': {'temperature': 0.7, 'thinking': False, 'ollama_seed': 42, 'bonsai_seed': None},
                 'cold_bonsai': 'model unloaded via API; native server process retained'})
        self.report('scheduled')
        self.event('scheduled', not_before=self.args.not_before.isoformat(), deadline=self.args.deadline.isoformat())
        while datetime.now().astimezone() < self.args.not_before:
            self.check_deadline()
            time.sleep(30)
        try:
            while True:
                self.check_deadline()
                try:
                    self.report('running')
                    self.hub_smoke()
                    self.comparison()
                    self.preload()
                    break
                except (RuntimeError, OSError) as error:
                    if isinstance(error, TimeoutError):
                        raise
                    self.event('yielding_to_other_apps', error=str(error))
                    self.report('waiting', str(error))
                    self.owned_ollama = None
                    self.owned_bonsai = False
                    self.expected_expiry = None
                    self.last_bonsai_request = None
                    time.sleep(30)
            self.report('measurements_complete')
            self.event('measurements_complete')
        except Exception as error:
            # Preserve other apps' work when interference is detected.
            self.report('interrupted', str(error))
            self.event('interrupted', error=str(error))
            raise
        finally:
            # Restore the currently selected hub provider only after our work has finished.
            if not self.owned_ollama and not self.owned_bonsai:
                try:
                    request = Request('http://127.0.0.1:8000/api/tutor/retry', data=b'{}',
                                      headers={'Content-Type': 'application/json'})
                    with bench.OPENER.open(request, timeout=10) as response:
                        self.event('hub_retry', status=json.load(response))
                except Exception as error:
                    self.event('hub_retry_failed', error=str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--not-before', type=datetime.fromisoformat, required=True)
    parser.add_argument('--deadline', type=datetime.fromisoformat, required=True)
    parser.add_argument('--cooldown', type=float, default=30)
    args = parser.parse_args()
    if args.not_before.tzinfo is None or args.deadline.tzinfo is None or args.cooldown < 0:
        parser.error('Use timezone-aware ISO timestamps and a nonnegative cooldown.')
    if args.not_before >= args.deadline:
        parser.error('The deadline must follow the start of the night window.')
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        NightRun(args).run()


if __name__ == '__main__':
    main()
