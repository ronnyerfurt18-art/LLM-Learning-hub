# LLM Learning Hub

Lokale Lernplattform für Studium und Schule. Die Oberfläche läuft im Browser (React, TypeScript), der Server auf dem eigenen Mac (FastAPI, SQLite). Als Tutor dient ein lokales KI-Modell (LLM) über Ollama oder Bonsai. Lernunterlagen, Fragen und Lernstände bleiben auf dem Gerät.

**Stand November 2026: Arbeitsstand.** Der Hub ist ohne Lerninhalte lauffähig und enthält ein Demo-Modul. Ein Installationsskript mit automatischer Wahl des KI-Modells nach Arbeitsspeicher fehlt noch; die Schritte unten ersetzen es. Auf 16 GB ist bisher nichts gemessen.

## Funktionen

- Lernseiten mit Quellenbelegen und Big Picture je Modul
- Fragen üben in acht Aufgabentypen, Wiederholungsplanung nach SM-2, Fehlerfragen, Probeklausuren
- Auswertungen: Fortschritt, Erfolgsquote, schwache Themen, Abdeckung
- Lernchat mit lokalem KI-Modell über die eigenen Unterlagen, auf Wunsch mit Mikrofon und Sprachausgabe
- Einsendearbeiten als Übung und als Gespräch Frage für Frage
- Lernplanung mit Terminen, Lernblöcken und Kalenderexport
- Aufbereiten: Unterlagen in der Homepage hochladen; das lokale KI-Modell entwirft daraus je Einheit Lernseiten und Fragen und auf Wunsch ein Big Picture. Veröffentlicht wird erst nach deiner Prüfung
- Qualitätsprüfung der KI-Antworten
- Entwicklung: Anforderungen an den Hub festhalten; das lokale KI-Modell arbeitet einen Auftrag aus, der Hub stuft ihn ein und schreibt den Prompt für eine externe KI

## Voraussetzungen

- Mac mit Apple-Silicon-Chip, ab 16 GB Arbeitsspeicher
- Python 3.9 oder neuer, Node.js 18 oder neuer, Git
- [Ollama](https://ollama.com) mit einem lokal geladenen KI-Modell
- 30 bis 50 GB freier Speicherplatz, je nach KI-Modell

## Installation

```bash
git clone https://github.com/ronnyerfurt18-art/LLM-Learning-hub.git
cd LLM-Learning-hub
bash Installation.command                      # Python-Umgebung und Oberfläche
ollama pull qwen3:14b                          # KI-Modell nach Tabelle unten wählen
cp tutor.local.example.json tutor.local.json   # danach KI-Modell und Kontext eintragen
python3 tools/install_demo.py                  # optional: Demo-Modul
bash Start.command                             # öffnet http://localhost:8000
```

Der Hub legt beim ersten Start den Studienordner `~/LearningHub/Studium` an. Dorthin gehören die eigenen Unterlagen.

### KI-Modell nach Arbeitsspeicher

| Arbeitsspeicher | KI-Modell (Beispiel) | `context_tokens` | Stand |
|---|---|---|---|
| 16 GB | `llama3.1:8b` oder `qwen3:8b` | 8192 | Richtwert, nicht gemessen |
| 24 GB | `qwen3:14b` | 16384 | Richtwert, nicht gemessen |
| 32 GB und mehr | `qwen3.8:27b-mlx` | 32768 | im Einsatz erprobt |

Es sollte immer nur ein großes KI-Modell geladen sein. Arbeitsspeicher lässt sich bei Apple-Silicon-Macs nicht nachrüsten; wer mehr braucht, wählt ein kleineres KI-Modell oder einen kleineren Kontext.

## Einstellungen in `tutor.local.json`

| Schlüssel | Bedeutung |
|---|---|
| `provider` | `ollama` oder `bonsai` |
| `model`, `ollama_model` | Name des KI-Modells in Ollama |
| `context_tokens` | Kontextfenster des lokalen KI-Modells, 8192 bis 131072 |
| `study_folder` | Ordner mit den Lernunterlagen. Standard: `~/LearningHub/Studium`. Der Hub liest ihn vollständig ein; er darf nicht im Programmordner liegen. |
| `bonsai_runtime` | Ordner der Bonsai-Laufzeit. Standard: `~/.learning-hub/runtimes/bonsai-demo` |
| `voice_runtime` | Ordner der Sprach-Laufzeit. Standard: `~/.learning-hub/runtimes/voice` |
| `features` | Liste der aktiven Bausteine: `voice`, `module_import`, `big_picture`, `development`. Ohne den Schlüssel sind alle aktiv. |

Umgebungsvariablen: `MLH_PORT`, `MLH_DATA_DIR`, `MLH_SOURCE_ROOT`, `MLH_LOCAL_CONTEXT_CHARS`, `MLH_CONTEXT_TOKENS`, `MLH_BONSAI_RUNTIME`, `MLH_VOICE_RUNTIME`.

Bonsai und die Sprachfunktion sind optional und brauchen eigene Laufzeiten: `setup/README.md`.

## Eigene Lerninhalte

Die Anleitung steht in [`docs/inhalte-einbinden.md`](docs/inhalte-einbinden.md): Studienordner, Module, Unterlagen einlesen, Fragen und Lernseiten erzeugen, Einsendearbeiten, Lernziele, Termine. Das Demo-Modul in `demo/` dient als Vorlage für jedes Dateiformat.

Eigene Inhalte, Einstellungen und Daten liegen in `content/`, `imports/`, `planning/`, `data/` und `tutor.local.json`. Diese Pfade sind in `.gitignore` ausgeschlossen.

## Installation durch einen KI-Agenten

Wer den Hub von einem KI-Agenten mit Zugriff auf den eigenen Mac einrichten lässt (zum Beispiel Claude oder ChatGPT im Arbeitsmodus), kann diesen Auftrag verwenden:

```text
Richte den LLM Learning Hub auf diesem Mac ein. Arbeite die Schritte der Reihe nach ab und
melde nach jedem Schritt kurz das Ergebnis. Brich ab und frage nach, wenn ein Schritt scheitert.

Regeln:
- Arbeite nur im Zielordner ~/LLM-Learning-hub und im Studienordner ~/LearningHub/Studium.
  Lies, ändere oder lösche nichts außerhalb davon.
- Installiere Systemsoftware (Python, Node.js, Git, Ollama) nur nach meiner Zustimmung.
- Lade kein KI-Modell über 20 GB ohne Rückfrage. Verwende keine Cloud-Modelle und keine API-Schlüssel.
- Überschreibe keine vorhandene tutor.local.json und keine Dateien in content/, imports/, data/.

Schritte:
1. Prüfe: Apple-Silicon-Chip (uname -m ergibt arm64), Arbeitsspeicher (sysctl -n hw.memsize),
   freier Speicherplatz (mindestens 30 GB), python3 ab 3.9, node ab 18, git, ollama.
   Nenne mir, was fehlt, und warte auf meine Entscheidung.
2. Klone https://github.com/ronnyerfurt18-art/LLM-Learning-hub.git nach ~/LLM-Learning-hub.
   Ist der Ordner schon vorhanden, aktualisiere ihn mit git pull.
3. Führe im Ordner "bash Installation.command" aus.
4. Wähle das KI-Modell nach Arbeitsspeicher: bis 16 GB "llama3.1:8b" mit context_tokens 8192,
   bis 24 GB "qwen3:14b" mit 16384, ab 32 GB "qwen3.8:27b-mlx" mit 32768.
   Zeige mir die Wahl und die Downloadgröße, dann lade es mit "ollama pull <KI-Modell>".
5. Lege tutor.local.json aus tutor.local.example.json an. Trage das KI-Modell (model und ollama_model)
   und context_tokens ein. Entferne die Zeilen bonsai_runtime und voice_runtime.
6. Führe "python3 tools/install_demo.py" aus, damit ein Demo-Modul vorhanden ist.
7. Führe die Tests aus: ".venv/bin/python -m pip install -r requirements-dev.txt" und
   ".venv/bin/python -m pytest -q". Melde die Zahl bestandener und fehlgeschlagener Tests.
8. Starte den Hub im Hintergrund mit "MLH_NO_BROWSER=1 .venv/bin/python launcher.py" und prüfe
   mit "curl -s http://localhost:8000/api/health", dass "status":"ok" und mindestens 14 Fragen
   gemeldet werden. Prüfe mit "curl -s http://localhost:8000/api/tutor/status" den Tutor.
9. Fasse zusammen: gewähltes KI-Modell, Ort des Studienordners, Testergebnis, Adresse des Hubs und
   wie ich ihn künftig starte (Start.command doppelklicken) und beende (Ctrl+C im Startfenster).
```

Der Agent braucht dafür Zugriff auf ein Terminal des Macs. Bonsai und die Sprachfunktion richtet der Auftrag nicht ein.

## Tests

```bash
bash Tests.command
```

## Dokumentation

| Datei | Inhalt |
|---|---|
| `docs/inhalte-einbinden.md` | Eigene Lerninhalte einbinden |
| `docs/import-format.md` | Format der Fragenpakete |
| `docs/modul-import.md` | Modul-Import mit dem lokalen KI-Modell |
| `docs/entwicklung.md`, `docs/entwicklungsregeln.md` | Seite „Entwicklung“ und die Regeln, die in jeden Übergabe-Prompt gehen |
| `docs/api-contract.md` | Schnittstellen und Format der Lernseiten |
| `docs/architecture.md`, `logs/Architekturlog.md` | Aufbau und Entscheidungen |
| `docs/bonsai.md`, `setup/README.md` | Bonsai und Sprach-Laufzeit |
| `logs/Aenderungslog.md` | Änderungen |

## Lizenz

Noch nicht festgelegt. Bis dahin gelten die gesetzlichen Regeln: Ansehen ja, Weiterverwenden nur mit Zustimmung.
