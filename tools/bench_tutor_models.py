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
import json, os, pathlib, socket, sys, time, urllib.parse, urllib.request
from urllib.error import HTTPError

ROOT = pathlib.Path(__file__).resolve().parent.parent


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


def run_ollama(model, msgs, max_tokens):
    payload = {'model': model, 'messages': msgs, 'stream': True, 'think': False, 'keep_alive': '15m',
               'options': {'num_ctx': 32768, 'num_predict': max_tokens, 'temperature': 0.7}}
    t0 = time.perf_counter()
    try:
        resp = post(OLLAMA + '/api/chat', payload)
    except HTTPError as e:
        if e.code != 400: raise
        payload.pop('think'); resp = post(OLLAMA + '/api/chat', payload)
    first = None; final = {}; text = []
    with resp:
        for line in resp:
            if not line.strip(): continue
            ev = json.loads(line)
            m = ev.get('message') or {}
            text.append(m.get('content') or '')
            if first is None and (m.get('content') or m.get('thinking')): first = time.perf_counter() - t0
            if ev.get('done'): final = ev
    total = time.perf_counter() - t0
    pt, pd = final.get('prompt_eval_count', 0), final.get('prompt_eval_duration', 0) / 1e9
    ot, od = final.get('eval_count', 0), final.get('eval_duration', 0) / 1e9
    return {'answer': ''.join(text), 'first': first, 'total': total, 'load': final.get('load_duration', 0) / 1e9,
            'prompt_tokens': pt, 'prefill_tps': pt / pd if pd else None,
            'out_tokens': ot, 'decode_tps': ot / od if od else None}


def run_bonsai(msgs, max_tokens):
    model = str(bonsai_runtime() / 'models' / 'Ternary-Bonsai-2-27B-mlx-2bit')
    payload = {'model': model, 'messages': msgs, 'stream': True, 'max_tokens': max_tokens,
               'enable_thinking': False, 'thinking_budget': 0, 'temperature': 0.7, 'top_p': 0.8,
               'top_k': 20, 'stream_options': {'include_usage': True}}
    t0 = time.perf_counter(); first = None; last = None; chunks = 0; usage = {}; done = False; other = []; answer = []
    with post(BONSAI + '/v1/chat/completions', payload) as resp:
        for raw in resp:
            line = raw.strip()
            if not line.startswith(b'data:'):
                if line: other.append(line.decode('utf-8', 'replace')[:300])
                continue
            data = line[5:].strip()
            if data == b'[DONE]': done = True; break
            ev = json.loads(data)
            if ev.get('error'): raise RuntimeError('Server meldet Fehler: ' + json.dumps(ev['error'], ensure_ascii=False)[:500])
            usage = ev.get('usage') or usage
            for ch in ev.get('choices', []):
                d = ch.get('delta') or {}
                answer.append(d.get('content') or '')
                if d.get('content') or d.get('reasoning_content') or d.get('reasoning'):
                    now = time.perf_counter() - t0
                    if first is None: first = now
                    last = now; chunks += 1
    total = time.perf_counter() - t0
    if not done and not chunks:
        raise RuntimeError(f'Verbindung nach {total:.1f} s ohne Antwort beendet – Server vermutlich abgestürzt.'
                           + (' Zusatzausgabe: ' + ' | '.join(other[:3]) if other else ''))
    pt = usage.get('prompt_tokens', 0); ot = usage.get('completion_tokens') or chunks
    gen = (last - first) if first and last and last > first else None
    return {'answer': ''.join(answer), 'first': first, 'total': total, 'load': 0.0, 'prompt_tokens': pt,
            'prefill_tps': pt / first if pt and first else None,
            'out_tokens': ot, 'decode_tps': (ot - 1) / gen if gen else None}


def fmt(v, unit=''):
    return '–' if v is None else (f'{v:,.1f}{unit}'.replace(',', 'X').replace('.', ',').replace('X', '.'))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('ollama', 'bonsai'):
        print(__doc__); sys.exit(1)
    which = sys.argv[1]
    limit = int(sys.argv[sys.argv.index('--bytes') + 1]) if '--bytes' in sys.argv else 24000
    cfg = json.loads((ROOT / 'tutor.local.json').read_text())
    model = cfg.get('ollama_model') or 'qwen3.8:27b-mlx'
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
            return
        print(f'{label:32} {fmt(r["first"], " s"):>9} {fmt(r["total"], " s"):>9} {r["prompt_tokens"] or "–":>11} '
              f'{fmt(r["prefill_tps"]):>12} {r["out_tokens"]:>9} {fmt(r["decode_tps"]):>16}')
    print('\nLauf 2/3 deutlich schneller als Lauf 1 = Prompt-Cache wirkt. Lauf 3 entspricht einer Folgefrage im Lernchat.')


if __name__ == '__main__':
    main()
