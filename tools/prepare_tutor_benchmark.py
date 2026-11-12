#!/usr/bin/env python3
"""Freeze 30 source-grounded tutor requests offline, using a SQLite backup.

The real /api/tutor/chat/stream route builds each context, but capture replaces
inference before any provider call. Nothing is written to the learner database.
Run with the hub's development environment (FastAPI TestClient needs httpx).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Ten topics, three cognitive levels. Expected subject matter comes from the
# existing goal criteria, with source positions copied from the same goal.
QUESTIONS = {
 'strategie-zusammenhang': (
  'Welche Beziehung besteht zwischen Unternehmensziel, Geschäftsanforderungen und Informatikstrategie?',
  'Ein Händler will schneller liefern. Warum reicht der Kauf neuer Software allein nicht? Erkläre den Zusammenhang mit der Informatikstrategie.',
  'Ein Händler schwankt zwischen Lagerautomatisierung und einer neuen Bestell-App. Entwickle aus dem Ziel kürzerer Lieferzeiten eine begründete IT-Ausrichtung. Trenne Ziel, Anforderungen, strategische Entscheidung und Umsetzung; benenne fehlende Entscheidungsdaten.'),
 'strategie-prozess': (
  'Nenne die vier Phasen des IT-Strategieprozesses in ihrer Reihenfolge und jeweils ihre Aufgabe.',
  'Warum werden Unternehmensplanung und Informatikausrichtung aus der Situations- und Umfeldanalyse abgeleitet? Erläutere die Abhängigkeiten.',
  'Ein Händler möchte zuerst eine IT-Plattform auswählen und erst danach seinen Markt untersuchen. Entwirf einen korrigierten Ablauf anhand aller vier Phasen des Strategieprozesses und gib je Phase ein konkretes Arbeitsergebnis an.'),
 'strategie-analysemethoden': (
  'Welche Instrumente gehören zur Situationsanalyse und welche zur Umfeldanalyse? Nenne bei Porter die fünf Wettbewerbskräfte.',
  'Ein Unternehmen hat technisch veraltete Anwendungen und gleichzeitig neue digitale Wettbewerber. Welche Instrumente der Situations- und Umfeldanalyse helfen jeweils und warum?',
  'Ein Händler hat informationsintensive Abläufe, veraltete Anwendungen und mächtige Lieferanten. Entwirf einen Analyseplan mit Informationsintensitätenportfolio, Anwendungsbeurteilung und Porter. Ordne jedes Instrument einer Fragestellung zu und erläutere Grenzen der vorliegenden Informationen.'),
 'strategie-strategien': (
  'Nenne und unterscheide die drei strategischen Grundrichtungen Kostenführerschaft, Differenzierung und Konzentration.',
  'Ein Premiumanbieter investiert in individuelle Beratung. Warum passt diese IT-Ausrichtung eher zur Differenzierung als zur Kostenführerschaft?',
  'Ein Händler erwägt Preisführerschaft, persönlichen Premiumservice oder die Spezialisierung auf eine Nische. Vergleiche die drei Strategien, leite jeweils eine passende IT-Ausrichtung ab und begründe, welche zusätzlichen Informationen für eine Auswahl nötig sind.'),
 'strategie-kompetenzen': (
  'Welche zwei Achsen und vier Bereiche hat die Ressourcenanalysematrix? Wozu dienen Fokusgruppen und Benchmarking?',
  'Eine intern sehr gute Fähigkeit ist für Kunden kaum wichtig. Warum ist sie damit noch keine Kernstärke? Erläutere Bedeutung und relative Stärke.',
  'Ein Händler hat gegenüber Wettbewerbern starke, aber wenig wichtige Berichtsgrafiken und eine schwache, strategisch wichtige Lieferprognose. Ordne beide Ressourcen in die Matrix ein, leite Prioritäten ab und erläutere, wie Fokusgruppen und Benchmarking die Einschätzung prüfen könnten.'),
 'strategie-entscheidungen': (
  'Was bedeutet Make-or-Buy und welche Voraussetzungen sollte eine Entscheidung berücksichtigen?',
  'Ein günstiges Angebot für eine IT-Leistung liegt vor. Warum genügt der Preisvergleich für Make-or-Buy nicht? Beziehe Kern- und Supportprozesse ein.',
  'Ein Händler kann seine einzigartige Lieferprognose und den standardisierten IT-Support auslagern. Vergleiche beide Entscheidungen hinsichtlich Kernkompetenzen, langfristiger Strategie, Prozesskenntnis und Kosten. Formuliere eine bedingte Empfehlung und benenne offene Informationen.'),
 'heft-2-3-4-mbv': (
  'Welche Ausgangspunkte unterscheiden Market-based View und Resource-based View?',
  'Zwei Unternehmen erkennen dieselbe Marktchance, besitzen aber unterschiedliche Fähigkeiten. Wie erklären markt- und ressourcenorientierte Ansätze verschiedene Strategien?',
  'Ein Händler sieht eine attraktive Nische, besitzt aber noch keine passende Logistikkompetenz. Analysiere den Fall einmal markt- und einmal ressourcenorientiert. Verbinde beide Perspektiven zu einer begründeten, bedingten Entscheidung.'),
 'heft-2-3-4-kern': (
  'Welche drei Haupteigenschaften kennzeichnen Kernkompetenzen? Erläutere sie kurz.',
  'Ein Unternehmen beherrscht ein leicht kopierbares Werkzeug sehr gut. Warum folgt daraus noch keine Kernkompetenz? Prüfe die drei Haupteigenschaften.',
  'Ein Händler behauptet, seine kurzfristig erfolgreiche Lieferprognose sei eine Kernkompetenz. Entwickle für Wettbewerbsvorteil, Dauerhaftigkeit und Transferierbarkeit je eine Prüffrage und ein mögliches Gegenargument. Formuliere ein Urteil unter Vorbehalt fehlender Daten.'),
 'heft-2-3-4-aus': (
  'Was unterscheidet Auslagerung und Ausgliederung hinsichtlich organisatorischer Zuordnung und verbleibendem Einfluss?',
  'Ein Unternehmen überträgt IT-Aufgaben an eine eigene Einheit und ein anderes an einen externen Dienstleister. Erkläre den Unterschied und die Bedeutung des verbleibenden Einflusses.',
  'Ein Händler möchte seine IT organisatorisch verselbstständigen, aber Einfluss behalten. Vergleiche Ausgliederung und externe Auslagerung. Begründe eine bedingte Auswahl und benenne die Informationen, die vor der Entscheidung noch fehlen.'),
 'heft-2-3-4-omit': (
  'Welche Phasen umfasst das Outsourcing-Vorgehensmodell OMIT und welche Aufgabe hat jede Phase?',
  'Warum erhöht es das Risiko, beim Outsourcing direkt mit dem Betrieb zu beginnen und Analyse, Ausschreibung und Transition zu überspringen?',
  'Ein Händler plant die Auslagerung seines IT-Supports. Entwickle einen OMIT-Ablauf mit Analyse, Ausschreibung, Transition und Betrieb. Benenne pro Phase eine konkrete Aufgabe und erläutere, welches Risiko dadurch begrenzt werden soll.'),
}
CATEGORIES = ('knowledge', 'transfer', 'application')
RUBRIC = {
 'correctness': {'0': 'Wesentliche fachliche Fehler.', '1': 'Im Kern richtig, aber mit Ungenauigkeiten.', '2': 'Kernaussagen fachlich richtig; keine Widersprüche.'},
 'coverage': {'0': 'Zentrale gefragte Aspekte fehlen.', '1': 'Teilweise vollständig.', '2': 'Alle zur Frage passenden erwarteten Kernaussagen enthalten.'},
 'grounding': {'0': 'Falsche oder erfundene Belege.', '1': 'Teilweise belegt; Lücken nicht durchgehend markiert.', '2': 'Aussagen durch ausgewählte Passagen gedeckt; fehlende Belege transparent.'},
 'explanation': {'0': 'Unverständlich oder ohne nötige Begründung.', '1': 'Verständlich, aber Begründung lückenhaft.', '2': 'Klar, nachvollziehbar; bei Transfer/Anwendung korrekte Fallzuordnung und Grenzen.'},
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare(project, source, database, output):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.core import Hub
    from backend.learning_memory import register_memory_routes
    from backend.tutor import TutorService, register_tutor_routes
    from backend.pdf_text_cache import PageTextCache
    import backend.tutor_context as context_module

    goals = {goal['id']: goal for goal in json.loads((project / 'content/tutor/goals.json').read_text())}
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        copied = Path(temp) / 'learning.sqlite3'
        # backup() includes committed WAL data, unlike copying only the main file.
        with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(copied) as dst:
            src.backup(dst)
        app = FastAPI()
        hub = Hub(copied)
        register_memory_routes(app, hub, project)
        service = TutorService(environ={'MLH_TUTOR_PROVIDER': 'ollama', 'MLH_TUTOR_MODEL': 'benchmark-capture'})
        app.state.tutor = service
        register_tutor_routes(app, hub, project, source)
        captured = {}
        def capture(context, message, history, think=False, **kwargs):
            request, shortened = service._prepare(context, message, history, stream=True, think=think)
            captured.clear()
            captured.update(context=context, messages=json.loads(request.data)['messages'], shortened=shortened)
            return iter([json.dumps({'type': 'error', 'detail': 'Offline capture; no inference'}) + '\n'])
        service.stream_chat = capture
        questions, timings = [], []
        client = TestClient(app, base_url='http://127.0.0.1')
        old_flag = os.environ.get('MLH_PDF_TEXT_CACHE')
        old_cache = context_module.PAGE_TEXT_CACHE
        try:
            for topic, variants in QUESTIONS.items():
                goal = goals[topic]
                for category, question in zip(CATEGORIES, variants):
                    body = {'module_id': goal['module_id'], 'goal_id': topic, 'message': question, 'history': [], 'think': False}
                    results = []
                    context_module.PAGE_TEXT_CACHE = PageTextCache()
                    for phase, flag in (('disabled', '0'), ('enabled_cold', '1'), ('enabled_warm', '1')):
                        os.environ['MLH_PDF_TEXT_CACHE'] = flag
                        captured.clear()
                        started = time.perf_counter()
                        response = client.post('/api/tutor/chat/stream', json=body)
                        if response.status_code != 200 or not captured:
                            raise RuntimeError(response.text)
                        results.append({'phase': phase, 'route_seconds': time.perf_counter() - started,
                                        'context_seconds': captured['context']['build_seconds'],
                                        'prompt_sha256': digest(captured['messages'])})
                    if len({row['prompt_sha256'] for row in results}) != 1:
                        raise AssertionError('Cache changed prompt: ' + topic)
                    identifier = topic + '-' + category
                    context = captured['context']
                    questions.append({'id': identifier, 'category': category, 'request': body,
                                      'expected_core': goal['criteria'], 'expected_sources': goal['sources'],
                                      'messages': captured['messages'], 'prompt_sha256': results[0]['prompt_sha256'],
                                      'context_text': context['context_text'], 'selected_sources': context['sources'],
                                      'selected_excerpt_spans_utf16': context.get('excerpts', {}),
                                      'context_notice': context['notice'], 'shortened': captured['shortened'],
                                      'quality_review': None})
                    timings.append({'id': identifier, 'runs': results})
        finally:
            client.close()
            context_module.PAGE_TEXT_CACHE = old_cache
            if old_flag is None: os.environ.pop('MLH_PDF_TEXT_CACHE', None)
            else: os.environ['MLH_PDF_TEXT_CACHE'] = old_flag
    suite = {'schema_version': 1, 'prepared_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
             'scope': '10 existing IT Governance goals; not representative of every module',
             'criteria_provenance': 'Existing goal criteria; no independent subject-matter validation yet',
             'rubric': RUBRIC, 'review_method': 'Blind model labels; score each dimension 0–2 with evidence; truncated answers cannot pass coverage; no automatic score.',
             'quality_gate': 'No critical factual errors; compare per-question correctness/grounding with baseline before recommending a faster model.',
             'questions': questions}
    (output / 'suite.json').write_text(json.dumps(suite, ensure_ascii=False, indent=2))
    (output / 'context-cache.json').write_text(json.dumps(timings, ensure_ascii=False, indent=2))
    print(output / 'suite.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=ROOT)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.project.resolve(), args.source.resolve(), args.database, args.output)


if __name__ == '__main__': main()
