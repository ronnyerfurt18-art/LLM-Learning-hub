# Lokale KI-Modelle: Messungen und Ergebnisse

Stand: 12.11.2026, **Zwischenstand mit ergänztem Live-Pilot**. Aktuelle Messungen und Grenzen: [Live-Prüfung](llm-live-pilot-2026-11-12.md). Aufbau und Befund stehen in [llm-performance-architecture.md](llm-performance-architecture.md).

## Messumgebung

| | |
|---|---|
| Rechner | MacBook Air, Apple M4, 32 GB, ohne Lüfter, macOS 27.0.1 |
| Ollama | 0.35.0 |
| Modell | `qwen3.8:27b-mlx`, Format safetensors, Quantisierung `nvfp4`, 18,2 GB auf der Platte, 18,6 GB geladen |
| Weitere Modelle | `qwen3.5:9b` (GGUF, Q4_K_M, 6,6 GB), Bonsai 2 27B (MLX, 2 Bit, 8,6 GB, eigene Laufzeit) |
| Hub | dieser Checkout auf Port 8010 mit einer Kopie der Datenbank; der private Hub auf Port 8000 lief unverändert weiter |
| Störgrößen | Während der Baseline lief ein verwaister Bonsai-Server (8,5 GB) mit; Swap 20–23 GB belegt. Der Rechner wurde nebenbei benutzt. |

Rohdaten: `data/benchmarks/` (nicht im Repository, enthält Antworten zu eigenen Lerninhalten).

## 1. Baseline: Cache-Tests A–E vor jeder Änderung

Lauf vom 12.11.2026, Code-Stand `3bdca3e`, Anfragen über `POST /api/tutor/chat/stream`, ohne „Gründlich nachdenken“. „Erster Text“ ist am Client gemessen, die übrigen Werte stammen von Ollama.

| Test | Erster Text | Gesamt | Prompt-Tokens | aus Cache | Lesen | Lesetempo | Schreibtempo |
|---|---:|---:|---:|---:|---:|---:|---:|
| Modell laden (leere Anfrage) | – | 7,6 s | – | – | – | – | – |
| **A** kalt: Lernziel 1, Frage 1 | 73,6 s | 95,0 s | 3.441 | 0 | 72,6 s | 47,4 T/s | 11,0 T/s |
| **B** identisch wiederholt | 0,7 s | 22,6 s | 3.441 | 3.436 | 0,2 s | – | 10,9 T/s |
| **C** gleiches Lernziel, andere Frage, neues Gespräch | 76,3 s | 100,3 s | 3.443 | **0** | 75,2 s | 45,8 T/s | 10,5 T/s |
| C2 Folgefrage im Verlauf | 8,1 s | 51,5 s | 3.729 | 3.438 | 7,3 s | 39,7 T/s | 7,7 T/s |
| C3 zweite Folgefrage | 1,7 s | 34,7 s | 4.096 | 4.065 | 1,0 s | – | 9,2 T/s |
| **D1** Wechsel zu Lernziel 2 | 87,3 s | 113,1 s | 3.546 | 0 | 86,3 s | 41,1 T/s | 9,1 T/s |
| **D2** zurück zu Lernziel 1, Frage 1 | 0,7 s | 35,7 s | 3.441 | 3.440 | 0,0 s | – | 7,9 T/s |
| M1 Modulchat ohne Lernziel | 99,0 s | 109,5 s | 3.683 | 0 | 97,8 s | 37,7 T/s | 9,5 T/s |
| M2 Modulchat, Folgefrage | 4,5 s | 18,4 s | 3.812 | 3.678 | 3,7 s | 35,9 T/s | 9,7 T/s |
| **E** Modell entladen und neu geladen, dann Frage 1 | 85,6 s | 117,6 s | 3.441 | 0 | 84,6 s | 40,7 T/s | 10,5 T/s |

Lesetempo ist nur angegeben, wo mindestens 100 Tokens neu gelesen wurden.

### Was die Baseline zeigt

- Die Baseline zeigt Treffer bei identischen und fortgesetzten Anfragen (B, C2, C3, D2, M2). Test C teilt 13.524 von 13.612 Zeichen mit der vorigen Anfrage und wird trotzdem vollständig neu gelesen. Daraus folgt keine allgemeingültige Regel für alle Präfixe; siehe Vorladeexperiment.
- Mehrere frühere Zustände bleiben erhalten (D2 trifft nach fünf anderen Anfragen).
- Entladen und Neuladen löschte hier den Cache (E). Das ist noch kein vollständiger Wechsel Qwen → Bonsai/9B → Qwen.
- Das Lesetempo fiel im Lauf von 47 auf 36–38 Tokens/s, das Schreibtempo von 11 auf 8–10 Tokens/s (Wärme, Speicherdruck). Vergleiche zwischen einzelnen Zeilen sind deshalb nur grob möglich.

### Der Widerspruch 08.11. (152,6 s) gegen 09.11. (1,3–8,2 s)

Beide Werte sind mit unterschiedlichem Cache-/Kontextzustand vereinbar. Ein Messfehler lässt sich anhand der vorhandenen Daten nicht abschließend ausschließen:

- **09.11.:** `tools/bench_tutor_models.py` hängt die Folgefrage an genau denselben Prompt an. Das entspricht den Tests C2/C3/M2 (1,7–8,1 s).
- **08.11.:** Im Hub stand der Kontext mit bis zu 24.000 Zeichen (rund 7.200 Tokens, siehe Bonsai-Log vom 08.11.: `prompt_tokens=7230 cached_tokens=0`), und die Passagenauswahl hing von der Frage ab. Ändert sich dadurch der Kontext, wird alles neu gelesen: 7.200 Tokens bei 45–50 Tokens/s ergeben 145–160 s.

Nicht belegbar ist, welche der beiden Ursachen am 08.11. konkret griff (geänderte Passagen oder gleitend gekürzter Verlauf); die damalige Anfrage liegt nicht mehr vor.

### Wie oft ändert die Frage den Kontext? (ohne Modell geprüft)

Für alle 11 Lernziele wurde der Kontext mit 10 typischen Fragen gebaut und mit dem Kontext ohne Frage verglichen: 10 von 110 Kombinationen (9 %) ergeben einen anderen Text, verteilt auf 7 Lernziele. In diesen Fällen wäre die Frage kalt.

## 2. Vorladen: erzeugt eine Anfrage nur mit Kontext einen wiederverwendbaren Cache?

Gespeichertes Experiment aus Claudes Zwischenstand, **in dieser Fortsetzung nicht erneut ausgeführt**. Rohdaten: `data/benchmarks/2026-11-12-vorladen-experiment.log`; Skript unter `data/benchmarks/skripte/preload_probe.py`.

| Schritt | Erstes Stream-Token laut damaligem Skript | Prompt / Cache | Prefill |
|---|---:|---:|---:|
| X1: nur System + Kontext, 1 Ausgabe-Token | 81,09 s | 3483 / 0 | 80,16 s |
| X2: erste Frage danach | 61,90 s | 3498 / 1066 | 61,32 s |
| X3: andere Frage, neues Gespräch | 1,52 s | 3499 / 3476 | 1,19 s |
| X4: Kontext-Vorladen wiederholt | 0,75 s | 3483 / 3478 | 0,32 s |
| X6: zusätzlicher Auszug + Frage | 2,69 s | 3536 / 3478 | 2,35 s |
| X7: Folgefrage mit Verlauf | 1,29 s | 3577 / 3557 | 0,93 s |

Das damalige Skript fasst Thinking und Content für den ersten Zeitpunkt zusammen. Alle Antworten endeten am sehr kurzen Tokenlimit; daraus ist keine Qualitätsaussage möglich. Ein identischer kontrollierter Lauf ohne Vorladen, Wiederholungen und ein isolierter Ausgangscache fehlen. X3 wurde außerdem nach X2 gemessen: Sein Treffer kann nicht allein X1 zugeschrieben werden. **Kein belastbarer Nachweis eines reproduzierbaren Vorteils für die erste Frage; kein automatisches Vorladen implementiert/aktiviert.**

## 3. Fortsetzung: nachgewiesener Vorteil beim Kontextaufbau

Gemessen ohne Modell über die echte `/api/tutor/chat/stream`-Route im FastAPI-TestClient, mit SQLite-Backup des Entwicklungsbestands. Die Providerübergabe wurde durch Erfassung des fertigen Prompts ersetzt. Je Frage: Cache aus → Cache an/kalt → Cache an/warm. 30 Fragen aus zehn vorhandenen Lernzielen; drei Aufbauten pro Frage. Rohdaten: `data/benchmarks/2026-11-12-codex-suite/context-cache.json`.

| Zustand | Median Kontextaufbau | Minimum–Maximum |
|---|---:|---:|
| PDF-Textcache deaktiviert | 198,7 ms | 106,8–212,2 ms |
| PDF-Textcache aktiviert, leer | 194,2 ms | 110,2–220,2 ms |
| PDF-Textcache aktiviert, Treffer | 60,9 ms | 58,5–72,7 ms |

Die Differenz der Mediane beträgt **137,8 ms bzw. 69,4 %**. Alle 30 finalen Nachrichtenlisten waren in den drei Varianten identisch (SHA-256-Vergleich). Ein Regressionstest prüft zusätzlich Quellen, Auszüge und Metadaten an echten Test-PDFs. Die feste Messreihenfolge kann Dateisystem-Aufwärmeffekte enthalten; der Vergleich aus/aktiviert-kalt zeigt ähnliche Extraktionskosten. Dies ist eine Messung des Kontextaufbaus, **keine neue End-to-End-TTFT-Messung**. Der große Prefill-Anteil von 70–100 Sekunden wird dadurch nicht beseitigt.

Beim ersten Fortsetzungslauf waren neue Modellmessungen blockiert: Die damalige Ausführungsumgebung verweigerte TCP-Verbindungen zu `127.0.0.1:11434` mit `Operation not permitted`. Ein tatsächlicher Benchmarkversuch wurde als fehlgeschlagen gesichert: `2026-11-12-codex-live-attempt.jsonl` und `.log`. Der Listener war sichtbar, seine API aber nicht erreichbar. Es wurde keine erfolgreiche neue Modellintegration behauptet.

Die früheren **73,6 s kalt / 0,7 s identisch wiederholt** bleiben Baseline-Werte aus Claudes Lauf und sind kein Erfolg der neuen Änderungen.

## 4. Modellvergleich und Lernqualität (30 Fragen)

Vorbereitet: `data/benchmarks/2026-11-12-codex-suite/suite.json` enthält genau zehn Wissens-, zehn Transfer- und zehn Anwendungsfragen. Grundlage sind zehn bestehende IT-Governance-Lernziele. Erwartete Kernaussagen und Fundstellen stammen aus deren Kriterien und Quellen; eine unabhängige fachliche Validierung der Kriterien steht aus. Die Auswahl repräsentiert nicht sämtliche Module.

Für jede Frage sind Request, tatsächlich erzeugte Modellnachrichten, vollständiger Kontext, gewählte Quellen, UTF-16-Positionen der PDF-Auszüge, Prompt-Hash und Budgetkürzung gespeichert. Eine Rubrik bewertet Korrektheit, Vollständigkeit, Quellenbezug und Erklärung jeweils mit 0–2 Punkten und Begründung. Die Bewertung soll mit verdeckten Modellnamen erfolgen; es gibt keine automatische erfundene Qualitätsnote. `quality_review` ist bis zur Prüfung `null`.

Der Suite-Modus des Benchmarks verwendet dieselben eingefrorenen Prompts direkt an der jeweiligen Laufzeit. Dadurch sind die Inhalte zwischen Modellen vergleichbar; seine TTFT enthält **nicht** den Kontextaufbau oder Hub-/Browser-Transport. Die tatsächliche Hub-TTFT wird separat durch die neue Instrumentierung gemessen. Ausgabe-Limit 1400, Temperatur 0,7, Thinking aus; Ollama-Seed 42, für Bonsai kein nachgewiesener Seed-Parameter. Bonsai behält seine Laufzeitparameter. Beide Wege schreiben echte Statistiken statt Schätzungen. Abbrüche und abgeschnittene Antworten sind markiert.

`--repeat 2` misst unmittelbare identische Wiederholungen; `--cold` entlädt bei Ollama vor der ersten Wiederholung jeder Frage. Ohne Reset lautet der Zustand `uncontrolled`, nicht „kalt“. Kaltes Bonsai muss über einen getrennten, kontrollierten Laufzeitneustart untersucht werden. Jede Ergebniszeile wird sofort geschrieben und mit `fsync` gesichert; bestehende Ausgabedateien werden nicht überschrieben. Thermik-Ausgaben von `pmset` vor/nach jedem Lauf und die Abkühlpause werden protokolliert. Fehlende Thermikwerte bleiben unbekannt.

Beispiele (Python aus der vorhandenen Hub-Entwicklungsumgebung verwenden):

```bash
python tools/bench_tutor_models.py ollama --model qwen3.8:27b-mlx --suite data/benchmarks/2026-11-12-codex-suite/suite.json --output data/benchmarks/qwen27b-run1.jsonl --repeat 2 --cold --cooldown 30
python tools/bench_tutor_models.py ollama --model qwen3.5:9b --suite data/benchmarks/2026-11-12-codex-suite/suite.json --output data/benchmarks/qwen9b-run1.jsonl --repeat 2 --cold --cooldown 30
python tools/bench_tutor_models.py bonsai --suite data/benchmarks/2026-11-12-codex-suite/suite.json --output data/benchmarks/bonsai-run1.jsonl --repeat 2 --cooldown 30
```

Nacheinander und mit nur einem geladenen großen Modell ausführen; das Tool beendet keine fremden Laufzeitprozesse. Für einen kontrollierten Vergleich Modellreihenfolge über Wiederholungsblöcke wechseln und gleiche Ausgangsbedingungen dokumentieren. `--cold` greift in den Cache des ausgewählten Ollama-Modells ein; Messungen daher außerhalb aktiver Lernchats ausführen. **Diese drei vollständigen 30-Fragen-Vergleichsläufe wurden noch nicht ausgeführt. Ein separater Drei-Fragen-Pilot liegt jetzt vor. Antwortqualität insgesamt nicht freigegeben; keine Empfehlung für ein anderes Modell oder eine Quantisierung.**

## Offene Probleme und nicht Verifiziertes

- Bonsai: Prefix-Cache im anschließenden Live-Pilot nachgewiesen; vollständiger Qualitätsvergleich und Integration mit einer vom Hub gestarteten Laufzeit weiterhin offen.
- Die Ursache des 08.11.-Werts ist plausibel erklärt, aber nicht mit der Originalanfrage nachgestellt.
- Wie viele Zustände Ollama vorhält und wann es sie verdrängt, ist nicht dokumentiert; gemessen ist nur, dass fünf Anfragen dazwischen nicht schadeten.

## 5. Prüfung und gespeicherter Zwischenstand

- Übernommener Stand: 470 Tests bestanden, ein bestehender Fehler in `tests/test_ocr.py::FillTests::test_scanned_pdf_is_read_with_the_local_engine` (OCR liest die Testschrift als Nullen).
- Gesamte verbleibende Python-Suite nach den Erweiterungen: **478 bestanden, 1 gezielt abgewählt** (genau dieser bereits reproduzierte OCR-Test). Log: `data/benchmarks/2026-11-12-codex-tests-final.log`.
- Nach dem abschließenden Abgleich der Bonsai-Einheiten: Messadapter-/Benchmark-Tests separat erneut ausgeführt; Ergebnis im Log `2026-11-12-codex-metrics-final.log`.
- Drei React-Rendering-Tests prüfen fehlende Werte, echte Nullwerte, Thinking versus sichtbaren Text und getrennte Browser-/Hub-Zeiten. Log: `2026-11-12-codex-ui-tests.log`. Eine interaktive Browserprüfung steht aus.
- TypeScript/Vite-Build erfolgreich; bestehende Größenwarnung für das JavaScript-Bundle bleibt. Log: `2026-11-12-codex-build.log`.
- `git diff --check` und Python-Syntaxprüfung erfolgreich.

Zusätzlicher Befund aus dem installierten Bonsai-Code: `mlx_vlm/server/schemas.py:GenerationTimings.from_metrics` leitet `prompt_ms` aus der gesamten Promptlänge ab. Bei Cache-Treffern sind daher sowohl diese Dauer als auch die daraus gebildete Prefill-Rate hier absichtlich nicht verfügbar. `mlx_vlm/generate/dispatch.py` verwendet `mx.get_peak_memory() / 1e9`; die Umrechnung wurde von GiB auf dezimale GB korrigiert. Das ist anhand des installierten Codes geprüft, nicht durch einen neuen Bonsai-Lauf.

Die Verwendung der Ollama-Laufzeitfelder wurde zusätzlich mit der [offiziellen Beschreibung der API-Metriken](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx) abgeglichen. Die konkrete Cache-Feldverfügbarkeit für das hier eingesetzte Modell stammt weiterhin aus den lokal gespeicherten Rohdaten.

### Offene Arbeit nach diesem Zwischenstand

| Phase | Stand und nächste notwendige Prüfung |
|---|---|
| A Architektur | dokumentiert; damalige Prozess-/Speicheraufnahme nicht erneut vollständig prüfbar |
| B Messbarkeit | Backend, UI, Benchmark implementiert; direkter Live-Pilot beider Provider und zehn Ollama-Hub-Anfragen bestanden; Bonsai-Hub-Integration offen |
| C Modell-Cache | A–E im aktuellen Hub einschließlich zwischenzeitlicher Modellladung wiederholt; keine unbewiesene Promptumordnung |
| D Vorladen | nicht aktiviert; gepaarte Messungen mit identischen kalten Ausgangszuständen erforderlich |
| E RAG | PDF-Extraktion beschleunigt, identische Prompts; Qualitätsvergleich alternativer Retrieval-Verfahren offen |
| F Oberfläche | einklappbare Messansicht implementiert; Browserprüfung und Übernahme in privaten Hub offen |
| G Modellqualität | 30 Fragen vorbereitet; Drei-Fragen-Pilot mit allen drei Modellen und erster qualitativer Durchsicht abgeschlossen; vollständige Bewertung offen |
| H Quantisierung | zurückgestellt, bis Cache-/Qualitätsvergleich abgeschlossen ist |

Der Zugriff auf die lokalen Dienste ist inzwischen gegeben; aktuelle Live-Ergebnisse stehen im separaten Pilotbericht. Es wurden keine fremden Bonsai-Prozesse beendet, keine Modelle heruntergeladen, keine Modellgewichte konvertiert und keine privaten Lerninhalte geändert. Der behauptete allgemeine Cache-Mechanismus sowie die eindeutige thermische Ursache aus dem früheren Text wurden auf den tatsächlich belegbaren Befund eingegrenzt.

### Sicherung und Rücknahme

Rücksetzpunkt vor dieser Fortsetzung: `data/backups/performance-codex-20261112-083641/` enthält die zuvor vorhandenen Dateien, Git-Status und Diff. Er bewahrt auch Claudes uncommittierte Arbeiten. Ein aktuelles Gesamtarchiv mit Manifest liegt unter `data/backups/performance-codex-checkpoint-20261112/`.

Für die isolierte Rücknahme des PDF-Caches genügt zunächst `MLH_PDF_TEXT_CACHE=0` beim Start des Entwicklungs-Hubs. Für die vollständige Rücknahme dieser Fortsetzung die vorhandenen Dateien aus dem ersten Rücksetzpunkt wiederherstellen und ausschließlich die sechs hier neu hinzugefügten Dateien entfernen: `backend/pdf_text_cache.py`, `frontend/src/TutorPerformance.tsx`, `frontend/tests/tutor-performance.test.mjs`, `tests/test_pdf_text_cache.py`, `tests/test_bench_tutor_models.py`, `tools/prepare_tutor_benchmark.py`. Danach das Frontend neu bauen. Die bereits von Claude angelegten Metrikdateien und Dokumente nicht pauschal löschen oder auf HEAD zurücksetzen.

**Gesamtstatus: belastbarer Zwischenstand, Gesamtauftrag noch nicht abgeschlossen.** Die neue Beschleunigung betrifft den Kontextaufbau. Ein großer neuer TTFT-Gewinn und unveränderte generierte Antwortqualität sind noch nicht nachgewiesen.


## 6. Live-Fortsetzung nach Zugriffsfreigabe

18 vollständige Pilotantworten (3 Fragen x 2 Wiederholungen x 3 Modelle) und zehn erfolgreiche Chat-Anfragen über den aktuellen Hub liegen jetzt vor. Die Instrumentierung für Ollama ist live bestätigt; Bonsais Prefix-Cache ist im direkten Provider-Aufruf nachgewiesen. Die Standardmodellauswahl bleibt wegen der festgestellten Qualitätsgrenzen unverändert. Details und offene Abnahme: [Live-Prüfung](llm-live-pilot-2026-11-12.md).
