#!/usr/bin/env python3
"""Demo-Modul „Lernen lernen“ einrichten.

  python3 tools/install_demo.py                      # Studienordner aus tutor.local.json, sonst ~/LearningHub/Studium
  python3 tools/install_demo.py --study-folder PFAD  # anderer Studienordner

Kopiert die Demo-Unterlagen in den Studienordner und die aufbereiteten Inhalte nach content/ und imports/.
Vorhandene Dateien werden nie überschrieben. Die Startliste imports/seed.json und die Lernziele in
content/tutor/goals.json werden ergänzt, nicht ersetzt. Der Aufruf ist beliebig oft wiederholbar.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.local_model import study_folder  # noqa: E402

MERGED = {Path('imports/seed.json'), Path('content/tutor/goals.json')}


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _merge(source, target):
    """Add demo entries to an existing list file; returns how many were added."""
    new = _read(source)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(new, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return len(new)
    old = _read(target)
    if not isinstance(old, list):
        raise ValueError(f'{target} ist keine Liste und wird nicht verändert.')
    known = {item['id'] if isinstance(item, dict) else item for item in old}
    added = [item for item in new if (item['id'] if isinstance(item, dict) else item) not in known]
    if added:
        target.write_text(json.dumps(old + added, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return len(added)


def install(project=ROOT, study=None, demo=None):
    """Copy the demo into place; returns the copied, skipped and merged relative paths and the study folder."""
    project, demo = Path(project), Path(demo or ROOT / 'demo')
    study = Path(study) if study else study_folder(project)
    study = study.expanduser().resolve()
    if study == project.resolve() or project.resolve() in study.parents:
        raise ValueError(f'Der Studienordner darf nicht im Programmordner liegen: {study}')
    copied, skipped, merged = [], [], []
    for base, target_root in ((demo / 'study', study), (demo / 'content', project / 'content'), (demo / 'imports', project / 'imports')):
        for source in sorted(path for path in base.rglob('*') if path.is_file() and not path.name.startswith('.')):
            relative = source.relative_to(demo)
            target = target_root / source.relative_to(base)
            if base.name != 'study' and Path(base.name) / source.relative_to(base) in MERGED:
                if _merge(source, target):
                    merged.append(relative.as_posix())
                continue
            if target.exists():
                skipped.append(relative.as_posix())
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(relative.as_posix())
    return copied, skipped, merged, study


def main():
    parser = argparse.ArgumentParser(description='Demo-Modul „Lernen lernen“ einrichten.')
    parser.add_argument('--study-folder', help='Studienordner; Standard: tutor.local.json, sonst ~/LearningHub/Studium')
    args = parser.parse_args()
    try:
        copied, skipped, merged, study = install(study=args.study_folder)
    except (ValueError, OSError) as exc:
        print(f'Demo konnte nicht eingerichtet werden: {exc}')
        return 1
    print(f'Studienordner: {study}')
    print(f'{len(copied)} Dateien kopiert, {len(skipped)} bereits vorhanden, {len(merged)} Listen ergänzt.')
    for name in skipped:
        print(f'  vorhanden, nicht überschrieben: {name}')
    print('Beim nächsten Start des Hubs erscheint das Modul „Lernen lernen (Demo)“.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
