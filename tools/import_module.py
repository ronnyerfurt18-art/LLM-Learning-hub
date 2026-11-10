#!/usr/bin/env python3
"""Neues Modul mit dem lokalen Ollama-Modell aufbereiten (Lernseiten-Entwurf und Übungsfragen).

Im Projektordner ausführen; der Hub darf dabei laufen, der Lernchat sollte währenddessen ruhen:
  .venv/bin/python tools/import_module.py --list                      # Module und ihre Nummern
  .venv/bin/python tools/import_module.py --module 10001 --preview    # was gelesen würde, ohne Modellaufruf
  .venv/bin/python tools/import_module.py --module 10001 --unit 1     # eine Kurseinheit als Probelauf
  .venv/bin/python tools/import_module.py --module 10001              # alle Kurseinheiten
  .venv/bin/python tools/import_module.py --module 10001 --publish    # geprüften Lernseiten-Entwurf veröffentlichen

Ergebnis: Fragen als imports/<modul>_einheit<N>_lokal.json (im Hub unter „Dokumente“ prüfen und importieren)
und ein Lernseiten-Entwurf unter imports/entwuerfe/. Fertige Abschnitte werden zwischengespeichert; ein
abgebrochener Lauf setzt beim nächsten Start dort fort.
"""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.core import Hub  # noqa: E402
from backend.local_model import study_folder  # noqa: E402
from backend.module_import import ModuleImport, ollama_generator, preview  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Modul lokal aufbereiten')
    parser.add_argument('--module', help='Modulnummer oder Modul-ID')
    parser.add_argument('--unit', type=int, action='append', help='Kurseinheit; mehrfach möglich')
    parser.add_argument('--model', help='Ollama-Modell; Standard aus tutor.local.json')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()

    source = study_folder(ROOT).resolve()
    data = Path(os.environ.get('MLH_DATA_DIR', str(ROOT / 'data'))).resolve()
    hub = Hub(data / 'learning.sqlite3')
    modules = hub.modules()
    if args.list or not args.module:
        for module in modules:
            print(f"{module.get('number') or '-':>6}  {module['id']:<12} {module['name']}")
        return 0
    module = next((item for item in modules if args.module in (item.get('number'), item['id'])), None)
    if not module:
        print('Modul nicht gefunden. Mit --list die erfassten Module anzeigen.')
        return 2
    job = ModuleImport(hub, ROOT, source, data)
    if args.publish:
        try:
            print(json.dumps(job.publish(module['id']), ensure_ascii=False, indent=1))
            return 0
        except (ValueError, KeyError) as exc:
            print(str(exc).strip("'"))
            return 1
    plan = preview(hub, module['id'], args.unit)
    for item in plan['sources']:
        print(f"Kurseinheit {item['unit']}: {item['path']} · {item['pages']} Seiten · {item['windows']} Abschnitte")
    for item in plan['skipped']:
        print(f"Nicht verwendet: {item['path']} – {item['reason']}")
    print(f"{plan['windows']} Modellaufrufe, grob {plan['estimated_minutes']} Minuten.")
    if args.preview or not plan['windows']:
        return 0

    config_path = ROOT / 'tutor.local.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    model = args.model or config.get('ollama_model') or config.get('model')
    if not model:
        print('Kein Modell angegeben und keines in tutor.local.json gefunden.')
        return 2
    try:
        generate = ollama_generator(model)
    except ValueError as exc:
        print(exc)
        return 1
    except OSError:
        print('Ollama ist nicht erreichbar. Bitte Ollama starten.')
        return 1

    worker = threading.Thread(target=job.run, args=(module['id'], args.unit, model, generate), daemon=True)
    worker.start()
    shown = 0
    try:
        while worker.is_alive():
            time.sleep(2)
            state = job.status()
            for message in state['messages'][shown:]:
                print(f"[{state.get('done', 0)}/{state.get('total', 0)}] {message}")
            shown = len(state['messages'])
    except KeyboardInterrupt:
        print('Abbruch angefordert; der laufende Abschnitt wird noch beendet …')
        job.cancel()
        worker.join()
    state = job.status()
    for message in state['messages'][shown:]:
        print(message)
    print(json.dumps({key: state.get(key) for key in ('state', 'counts', 'outputs')}, ensure_ascii=False, indent=1))
    return 0 if state['state'] == 'done' else 1


if __name__ == '__main__':
    sys.exit(main())
