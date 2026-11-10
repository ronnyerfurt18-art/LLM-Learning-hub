"""Test helper: imports/seed.json names the packages that load at start."""
import json

APPROVED = [f'digitale_diversitaet_einheit{unit}.json' for unit in range(1, 9)] + ['business_intelligence_metadaten.json']


def write_seed_list(project, names=APPROVED):
    imports = project / 'imports'
    imports.mkdir(parents=True, exist_ok=True)
    (imports / 'seed.json').write_text(json.dumps(list(names)), encoding='utf-8')
