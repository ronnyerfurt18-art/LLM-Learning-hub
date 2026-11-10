# Änderungslog – Learning Hub (Rohfassung)

Die Rohfassung ist am 10.11.2026 aus dem privaten Master Learning Hub abgezweigt. Das Änderungslog des privaten Hubs bleibt dort.

---

## 10.11.2026 – Eigener Studienordner, Demo-Modul, Anleitung für Inhalte, Dokumente bereinigt

**Studienordner (`backend/local_model.py`, `backend/main.py`, `launcher.py`, `tools/import_module.py`):** Bisher galt der Ordner über dem Projekt als Studienordner und wurde vollständig eingelesen. Jetzt gilt `study_folder` aus `tutor.local.json` (oder `MLH_SOURCE_ROOT`), sonst `~/LearningHub/Studium`. Der Standardordner wird beim Start angelegt; ein Ordner im Programmordner wird abgelehnt.

**Demo-Modul (`demo/`, `tools/install_demo.py`, `Demo.command`):** Modul „Lernen lernen“ mit zwei selbst geschriebenen Lehrbriefen und einem Aufgabenblatt als PDF, vier Lernseiten mit Big Picture, 14 Fragen, einer Übungsarbeit und drei Lernzielen. Das Einrichten überschreibt nichts und ergänzt `imports/seed.json` und `content/tutor/goals.json`.

**Anleitung:** Neu `docs/inhalte-einbinden.md`. README neu geschrieben, mit Modellwahl nach Arbeitsspeicher und einem Auftrag für die Installation durch einen KI-Agenten.

**Dokumente bereinigt:** Entfernt wurden `docs/planung-und-kalender.md`, `docs/einsendearbeiten.md`, `docs/lernprotokoll.md` und `docs/lokaler-tutor-start.md`, weil sie persönliche Termine, Ordnerpfade und Kursbezüge enthielten; ihr allgemeiner Inhalt steht in der neuen Anleitung. Beispiele in den übrigen Dokumenten und Werkzeugen verwenden jetzt das Demo-Modul.

**Tests:** Neu `tests/test_demo.py`. Der bisher übersprungene Test in `tests/test_api.py` nutzt das Demo-Paket.

**Rückgängig machen:** `demo/`, `tools/install_demo.py`, `Demo.command`, `docs/inhalte-einbinden.md` und `tests/test_demo.py` löschen; für den Studienordner `study_folder()` in `backend/local_model.py` entfernen und in `backend/main.py` den alten Standard einsetzen.

---

## 10.11.2026 – Rohfassung ohne Inhalte abgezweigt; Code von Modulen und festen Pfaden gelöst

**Nicht übernommen:** `content/`, `content-fragments/`, `imports/`, `planning/`, `data/`, `docs/quellen/`, `docs/screenshots/`, inhaltsbezogene Dokumente unter `docs/`, doppelte Dateien („… 2.py“, „… 2.tsx“), `tutor.local.json`.

**Einsendearbeiten (`backend/assignments.py`, `backend/main.py`, `backend/tutor_assignments.py`, `frontend/src/Assignments.tsx`):** Alle Dateien in `content/assignments/` werden geladen und über das neue Pflichtfeld `module_number` dem Modul zugeordnet. Die feste Form (12 Fragen, 5 Aussagen, mindestens eine wahr, Punktetabelle) steht jetzt optional in `rules` der Datei. Ohne Punktetabelle zählt der Anteil korrekt beurteilter Aussagen.

**Startpakete (`backend/main.py`):** Welche Fragenpakete beim Start automatisch geladen werden, steht in `imports/seed.json` statt im Code. Ohne diese Datei wird nichts automatisch geladen.

**Bezeichnung der Lerneinheiten (`backend/core.py`, `backend/search.py`, `frontend/src/unitLabel.ts` und sieben Seiten):** Je Modul einstellbar (Einheit, Session, Kapitel, Lektion, Woche), gespeichert in der Metadaten-Tabelle unter `module_unit_labels`. Ersetzt die feste Abfrage einer Modulnummer.

**Laufzeiten und Kontext (`backend/local_model.py`, `backend/bonsai.py`, `backend/voice.py`, `launcher.py`, `backend/tutor.py`, `tools/bench_tutor_models.py`):** Ordner für Bonsai und Sprache über `bonsai_runtime` und `voice_runtime` in `tutor.local.json` oder über Umgebungsvariablen; Standard `~/.learning-hub/runtimes/…`. Kontextfenster über `context_tokens`. Ein Modellwechsel im Lernchat erhält diese Einstellungen.

**Sprach-Laufzeit (`setup/`):** `worker.py` und die Paketliste der geprüften Installation liegen jetzt im Projekt; `setup/README.md` beschreibt den Aufbau beider Laufzeiten.

**Lernprotokoll (`backend/learning_memory.py`):** Hinweistext wird aus den vorhandenen Lernzielen gebildet.

**Tests:** Neu `tests/test_generic_setup.py` und `tests/seedlist.py`. Entfernt, weil sie eigene Kursunterlagen prüfen: `tests/test_seed.py`, `tests/test_model_search.py`, Klasse `Session2SeedSourceTests`. Ein Test in `tests/test_api.py` wurde zunächst übersprungen (siehe Eintrag oben).

**Übernahme vorhandener Inhalte aus einer älteren Fassung:** In jeder Einsendearbeit `module_number` und bei fester Form `rules` ergänzen; `imports/seed.json` mit den bisherigen Startpaketen anlegen; je Modul die Bezeichnung der Lerneinheiten wählen; in `tutor.local.json` Studienordner und Laufzeitordner eintragen.

**Offen:** `install.sh` mit RAM-Profilen, Ollama-Adresse einstellbar, einheitliches Standardmodell, Modellbezeichnung „Qwen · Ollama“ im Lernchat, Messungen auf 16 GB.
