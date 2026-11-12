#!/usr/bin/env python3
"""Misst Prefill (Lesen des Lernkontexts) und Antwortgeschwindigkeit getrennt.

Immer nur EIN großes Modell geladen lassen, sonst verfälscht Swap die Werte.
  python3 tools/bench_tutor_models.py ollama   # qwen über Ollama (Bonsai-Server aus)
  python3 tools/bench_tutor_models.py bonsai   # Bonsai auf Port 8081 (Ollama-Modell entladen)
Optional: --bytes 8000  (Kontextgröße, Standard 24000 wie im Hub)
          --hub strategie-prozess  (echten Kontext dieses Lernziels vom laufenden Hub holen;
                                    --hub overview = Modulüberblick; Modul über MLH_BENCH_MODULE, Standard M-10001)
Lauf 3 ist eine echte Folgefrage: Antwort aus Lauf 1 plus neue Frage, wie im Lernchat.
"""
import argparse, hashlib, json, os, pathlib, socket, subprocess, sys, time, urllib.parse, urllib.request
from urllib.error import HTTPError

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.tutor_metrics import Stopwatch, bonsai_stats, memory_snapshot, ollama_stats, performance


def bonsai_runtime():
    """Same lookup as the hub: tutor.local.json, then MLH_BONSAI_RUNTIME, then ~/.learning-hub/runtimes."""
    try:
        configured = json.loads((ROOT / 'tutor.local.json').read_text()).get('bonsai_runtime')
    except (OSError, ValueError):
        configured = None
    return pathlib.Path(configured or os.environ.get('MLH_BONSAI_RUNTIME')
                        or pathlib.Path.home() / '.learning-hub' / 'runtimes' / 'bonsai-demo').expanduser()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OLLAMA = 'http://127.0.0.1:11434'
BONSAI = 'http://127.0.0.1:8081'
MAX_TOKENS = 300
SYSTEM = 'Du bist ein Lernbegleiter. Antworte auf Deutsch, knapp und nur anhand der Lerndaten.'
Q1 = 'Erkläre in fünf Sätzen den Unterschied zwischen OLAP und Data Mining.'
Q2 = 'Welche Kriterien muss ein gefundenes Muster erfüllen? Antworte in drei Sätzen.'


def context(limit):
    texts = []
    def walk(x):
        if isinstance(x, str): texts.append(x)
        elif isinstance(x, dict): [walk(v) for v in x.values()]
        elif isinstance(x, list): [walk(v) for v in x]
    for p in sorted((ROOT / 'content').glob('*.json')):
        walk(json.loads(p.read_text(encoding='utf-8')))
    text = '\n'.join(texts) or 'Kein Lernstoff gefunden.'
    while len(text.encode()) < limit: text += '\n' + text
    return text.encode()[:limit].decode('utf-8', 'ignore')


def hub_messages(goal):
    """System prompt and context exactly as the hub builds them for a goal (or the module overview)."""
    port = int(os.environ.get('MLH_PORT', '8000'))
    if goal == 'overview':
        params = {'module_id': os.environ.get('MLH_BENCH_MODULE', 'M-10001')}
    else:
        goals = {g['id']: g for g in json.loads((ROOT / 'content/tutor/goals.json').read_text(encoding='utf-8'))}
        if goal not in goals:
            print('Unbekanntes Lernziel. Verfügbar:', ', '.join(goals)); sys.exit(1)
        params = {'module_id': goals[goal]['module_id'], 'goal_id': goal}
    url = f'http://127.0.0.1:{port}/api/tutor/context?' + urllib.parse.urlencode(params)
    try:
        with OPENER.open(url, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        print('Lernhub nicht erreichbar oder Kontext nicht ladbar:', e); sys.exit(1)
    print('Hub-Kontext:', len(data['context_text']), 'Zeichen ·', data.get('notice', '')[:160])
    return lambda q: [{'role': 'system', 'content': data['instructions']},
                      {'role': 'user', 'content': data.get('context_preamble', '') + data['context_text']},
                      {'role': 'user', 'content': q}]


def messages(ctx, q):
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': 'LERNDATEN:\n' + ctx},
            {'role': 'user', 'content': q}]


def post(url, payload):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    return OPENER.open(req, timeout=900)


def port_open(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def loaded_ollama_models():
    try:
        with OPENER.open(OLLAMA + '/api/ps', timeout=3) as r:
            return [m['name'] for m in json.load(r).get('models', [])]
    except Exception:
        return []


def _measured(provider, model, watch, final, answer, reason):
    total = watch.elapsed()
    stats = ollama_stats(final) if provider == 'ollama' else bonsai_stats(final.get('usage'), final.get('timings'))
    record = performance(provider, model, watch, stats, memory_snapshot(provider, model))
    record['total_seconds'] = total  # exclude the post-request memory probes
    return {'answer': ''.join(answer), 'first': watch.first_visible, 'total': total,
            'load': stats['load_seconds'], 'prompt_tokens': stats['prompt_tokens'],
            'prefill_tps': stats['prefill_tokens_per_second'], 'out_tokens': stats['output_tokens'],
            'decode_tps': stats['decode_tokens_per_second'], 'performance': record,
            'done_reason': reason, 'truncated': reason == 'length', 'raw_stats': final}


def run_ollama(model, msgs, max_tokens):
    payload = {'model': model, 'messages': msgs, 'stream': True, 'think': False, 'keep_alive': '15m',
               'options': {'num_ctx': 32768, 'num_predict': max_tokens, 'temperature': 0.7, 'seed': 42}}
    watch = Stopwatch()
    final = None; text = []
    # Do not silently change thinking/parameters after an error: comparisons must be explicit.
    with post(OLLAMA + '/api/chat', payload) as resp:
        for line in resp:
            if not line.strip(): continue
            ev = json.loads(line)
            if ev.get('error'): raise RuntimeError(str(ev['error']))
            m = ev.get('message') or {}
            content = m.get('content') or ''
            if m.get('thinking'): watch.token(visible=False)
            if content: watch.token(visible=bool(content.strip()))
            text.append(content)
            if ev.get('done') is True:
                final = ev; break
    if final is None: raise RuntimeError('Ollama stream ended without completion statistics')
    return _measured('ollama', model, watch, final, text, final.get('done_reason'))


def run_bonsai(msgs, max_tokens):
    model = str(bonsai_runtime() / 'models' / 'Ternary-Bonsai-2-27B-mlx-2bit')
    payload = {'model': model, 'messages': msgs, 'stream': True, 'max_tokens': max_tokens,
               'enable_thinking': False, 'thinking_budget': 0, 'temperature': 0.7, 'top_p': 0.8,
               'top_k': 20, 'min_p': 0.0, 'presence_penalty': 1.5,
               'stream_options': {'include_usage': True}}
    watch = Stopwatch(); final = {}; reason = None; answer = []; done = False
    with post(BONSAI + '/v1/chat/completions', payload) as resp:
        for raw in resp:
            line = raw.strip()
            if not line.startswith(b'data:'): continue
            data = line[5:].strip()
            if data == b'[DONE]': done = True; break
            ev = json.loads(data)
            if ev.get('error'): raise RuntimeError(str(ev['error']))
            for key in ('usage', 'timings'):
                if isinstance(ev.get(key), dict): final[key] = ev[key]
            for ch in ev.get('choices', []):
                d = ch.get('delta') or {}
                if d.get('reasoning_content') or d.get('reasoning'): watch.token(visible=False)
                content = d.get('content') or ''
                if content: watch.token(visible=bool(content.strip()))
                answer.append(content)
                if ch.get('finish_reason'): reason = ch['finish_reason']
    if not done or reason not in ('stop', 'length'):
        raise RuntimeError('Bonsai stream incomplete or unsupported finish reason')
    return _measured('bonsai', model, watch, final, answer, reason)


def thermal_snapshot():
    try:
        result = subprocess.run(['/usr/bin/pmset', '-g', 'therm'], capture_output=True, text=True, timeout=3)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def run_suite(args):
    suite_path = pathlib.Path(args.suite)
    suite = json.loads(suite_path.read_text())
    questions = suite['questions']
    if not questions: raise ValueError('No questions in suite')
    if args.cold and args.provider != 'ollama':
        raise ValueError('Cold Bonsai requires a controlled runtime restart; automatic reset is unsupported')
    run = (lambda msgs, limit: run_ollama(args.model, msgs, limit)) if args.provider == 'ollama' else run_bonsai
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive output creation prevents overwriting earlier measurements.
    with output.open('x', encoding='utf-8') as log:
        def save(item):
            log.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n'); log.flush(); os.fsync(log.fileno())
        save({'type': 'manifest', 'suite': str(suite_path), 'suite_sha256': hashlib.sha256(suite_path.read_bytes()).hexdigest(),
              'provider': args.provider, 'model': args.model if args.provider == 'ollama' else str(bonsai_runtime()),
              'repeats': args.repeat, 'cooldown_seconds': args.cooldown, 'max_tokens': args.max_tokens,
              'sampling': {'temperature': 0.7, 'think': False, 'ollama_seed': 42, 'bonsai_seed': None},
              'measurement_path': 'direct provider; frozen prompts captured from real hub routes',
              'quality': 'pending manual review using suite rubric', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z')})
        for question in questions:
            for repetition in range(args.repeat):
                record = {'type': 'result', 'question_id': question['id'], 'category': question['category'],
                          'repetition': repetition + 1, 'cache_condition': 'uncontrolled' if repetition == 0 else 'identical_repeat',
                          'quality_review': None, 'thermal_before': thermal_snapshot()}
                try:
                    if args.cold and repetition == 0:
                        with post(OLLAMA + '/api/generate', {'model': args.model, 'keep_alive': 0}) as response:
                            reset = json.load(response)
                        if reset.get('done') is not True or reset.get('error'):
                            raise RuntimeError('Model unload not confirmed')
                        record['cache_condition'] = 'after_unload'
                    record.update(run(question['messages'], args.max_tokens))
                    record['thermal_after'] = thermal_snapshot()
                    save(record)
                    print(question['id'], repetition + 1, 'TTFT', fmt(record['first'], ' s'), flush=True)
                except Exception as exc:
                    save({**record, 'error': str(exc), 'status': 'failed'})
                    raise
                if args.cooldown: time.sleep(args.cooldown)


def fmt(v, unit=''):
    return '–' if v is None else (f'{v:,.1f}{unit}'.replace(',', 'X').replace('.', ',').replace('X', '.'))


def main():
    if '--suite' in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('provider', choices=['ollama', 'bonsai'])
        parser.add_argument('--suite', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--model', default='qwen3.8:27b-mlx')
        parser.add_argument('--repeat', type=int, default=2)
        parser.add_argument('--max-tokens', type=int, default=1400)
        parser.add_argument('--cooldown', type=float, default=30)
        parser.add_argument('--cold', action='store_true')
        args = parser.parse_args()
        if args.repeat < 1 or args.max_tokens < 1 or args.cooldown < 0: parser.error('Invalid limits')
        run_suite(args)
        return
    if len(sys.argv) < 2 or sys.argv[1] not in ('ollama', 'bonsai'):
        print(__doc__); sys.exit(1)
    which = sys.argv[1]
    limit = int(sys.argv[sys.argv.index('--bytes') + 1]) if '--bytes' in sys.argv else 24000
    cfg = json.loads((ROOT / 'tutor.local.json').read_text())
    model = sys.argv[sys.argv.index('--model') + 1] if '--model' in sys.argv else cfg.get('ollama_model') or 'qwen3.8:27b-mlx'
    other = loaded_ollama_models() if which == 'bonsai' else (['Bonsai (Port 8081)'] if port_open(8081) else [])
    if other:
        print('WARNUNG: Zusätzlich geladen:', ', '.join(other), '– Messwerte werden durch Swap verfälscht.')
    if which == 'bonsai' and not port_open(8081):
        print('Bonsai-Server läuft nicht. Im Lernchat Bonsai wählen und auf „bereit“ warten.'); sys.exit(1)
    build = hub_messages(sys.argv[sys.argv.index('--hub') + 1]) if '--hub' in sys.argv else (lambda q: messages(context(limit), q))
    run = (lambda m, n: run_ollama(model, m, n)) if which == 'ollama' else run_bonsai
    print(f'Modell: {model if which == "ollama" else "Bonsai 2 27B (mlx-vlm)"} · Kontext: {"Lernhub" if "--hub" in sys.argv else str(limit) + " Bytes"} · max {MAX_TOKENS} Tokens\n')
    print('Aufwärmen …'); w = run([{'role': 'user', 'content': 'Hallo'}], 1)
    print(f'  Ladezeit Modell: {fmt(w["load"], " s") if which == "ollama" else "– (Server war bereits geladen)"}\n')
    first_msgs = build(Q1); first_answer = ''
    rows = [('1 Neue Frage mit Lernkontext', lambda: first_msgs),
            ('2 Gleiche Anfrage nochmal', lambda: first_msgs),
            ('3 Folgefrage im Chatverlauf', lambda: first_msgs + [{'role': 'assistant', 'content': first_answer},
                                                                  {'role': 'user', 'content': Q2}])]
    print(f'{"Lauf":32} {"1. Wort":>9} {"Gesamt":>9} {"Prompt-Tok":>11} {"Lesen tok/s":>12} {"Antw-Tok":>9} {"Schreiben tok/s":>16}')
    for label, msgs in rows:
        try:
            r = run(msgs(), MAX_TOKENS)
            if label.startswith('1'): first_answer = r['answer']
        except Exception as e:
            print(f'{label:32} FEHLER: {e}')
            if which == 'bonsai':
                print(f'\nLog ansehen: tail -n 60 "{bonsai_runtime() / "logs" / "learning-hub.log"}"')
            raise SystemExit(1)
        print(f'{label:32} {fmt(r["first"], " s"):>9} {fmt(r["total"], " s"):>9} {r["prompt_tokens"] or "–":>11} '
              f'{fmt(r["prefill_tps"]):>12} {r["out_tokens"] if r["out_tokens"] is not None else "–":>9} {fmt(r["decode_tps"]):>16}')
        print("  Cache:", r["performance"]["cached_tokens"], "/", r["prompt_tokens"], "Tokens (None = unbekannt)")
    print('\nCache-Nachweis nur über cached_tokens; kürzere Wartezeit allein belegt keinen Treffer. Lauf 3 ist eine Folgefrage.')


if __name__ == '__main__':
    main()
