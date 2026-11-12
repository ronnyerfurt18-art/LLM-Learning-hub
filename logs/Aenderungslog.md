# Änderungslog – Learning Hub (Rohfassung)

## 12.11.2026 – Modellwechsel nach fehlgeschlagener Frage freigeben

Der Modellschalter in `LearningTutor.tsx` war auch nach einer fehlgeschlagenen Anfrage durch den für Wiederholungen behaltenen Gesprächsbeitrag gesperrt. Er bleibt nun bei tatsächlich laufender Anfrage, Modellwechsel oder Sprachverarbeitung gesperrt. Nach einem Fehler kann das Modell gewechselt und dieselbe Frage erneut gesendet werden. Zwei Tests prüfen direkt den Sperrausdruck des verwendeten Auswahlfelds. Rückweg ist die Wiederherstellung der vorherigen Sperrbedingung und ein neuer Frontend-Build.

## 12.11.2026 – Speicherprüfung für gleichzeitig verwendete Modelle

Eine echte Tutorfrage brach bei parallel geladenem Qwen und Bonsai mit einem nativen Metal-Speicherfehler ab. Bonsai prüft nun vor Laden und Anfrage den geschätzten Speicherbedarf gegen die geladenen Ollama-Gewichte und den physischen Arbeitsspeicher. Der Start wartet bei einem Konflikt und läuft nach dessen Ende automatisch weiter. Fehler im Stream erhalten eine konkrete Speichermeldung und beenden den Statusmonitor, damit „Erneut prüfen“ erneut starten kann. Die Prüfung verwendet vorsorglich 1,6-fache Bonsai-Gewichte und 4 GiB Systemreserve. Die tatsächliche GPU-Belegung bleibt dynamisch.

Betroffen sind `backend/bonsai.py`, `backend/tutor.py`, `tests/test_bonsai.py` und `docs/bonsai.md`. 58 gezielte Tests bestanden. Der vorherige vollständige Lauf ohne den separat bestätigten bestehenden OCR-Fehler ergab 501 bestandene Tests. Rückweg ist die gezielte Wiederherstellung aus der Sicherung vor dieser Übernahme.

## 12.11.2026 – Bonsai nach Entladen wieder erreichbar

Die leere Modellliste eines laufenden Bonsai-Servers wurde als fremdes Modell behandelt. Der Hub prüft jetzt den Listener und dessen Startbefehl gegen die konfigurierte native Laufzeit, verwendet einen passenden Server weiter und lädt das lokale Modell mit einer kurzen Anfrage. Er beendet weiterhin ausschließlich eigene Prozesse. Der Wechsel zu Bonsai entlädt das gemeinsam genutzte Ollama-Modell künftig nicht mehr. Neue Regressionstests decken entladene und unbekannte Server, Nachladen, Abbruch und den Wechsel mit gemeinsam genutztem Ollama ab.

Betroffen sind `backend/bonsai.py`, `backend/tutor.py`, `tests/test_bonsai.py` und `docs/bonsai.md`. Rückweg ist die gezielte Wiederherstellung dieser Änderungen aus der Sicherung vor Übernahme. Vorherige Performance-Erweiterungen bleiben erhalten.

Die geprüften Änderungen und die vorherigen Performance-Erweiterungen wurden mit Sicherung unter `data/backups/bonsai-deploy-20261112-183321/` in den privaten Hub übernommen. Dessen Konfiguration blieb dabei erhalten. Ein eigener lokaler Nachtlauf `tools/overnight_tutor_benchmark.py` sammelt den vollständigen Vergleich mit Zwischenständen, Leerlaufprüfungen, rotierender Modellreihenfolge und gepaarten Vorladeversuchen. Seine Ergebnisse liegen unter `data/benchmarks/2026-11-12-overnight/`. Rückweg für den Nachtlauf ist das Beenden seines eigenen Prozesses. Bereits gemessene Antworten bleiben erhalten.

Die Rohfassung ist am 10.11.2026 aus dem privaten Master Learning Hub abgezweigt. Das Änderungslog des privaten Hubs bleibt dort.

---

## 12.11.2026 – Stand vom 11.11.2026 aus dem privaten Hub übernommen

**Anlass:** Am 11.11.2026 wurde im privaten Hub weiterentwickelt. Diese Fassung erhält denselben Programmstand; Lerninhalte, Daten und Einstellungen bleiben außen vor.

**Neu:**
- **Entwicklung, Stufe 1 und Chat:** Kleine Aufträge setzt das lokale KI-Modell nach Freigabe um (`backend/development_change.py`), mit Sicherung und „Zurücknehmen“. Ein Chat-Fenster führt eine Aufgabe in einem Lauf bis zum Urteil „erledigt / nicht erledigt“; der Hub baut und testet selbst (`backend/development_flow.py`, `frontend/src/DevChat.tsx`). Jede Anforderung zeigt Stand, Prüfpunkte und Verlauf.
- **„KI fragen“ auf jeder Seite:** kleines Chat-Fenster, das den Inhalt der aktuellen Seite kennt (`backend/quick_chat.py`, `frontend/src/AskAi.tsx`, `pageContext.ts`). „Entwicklung“ liegt als Symbol in der Kopfleiste.
- **Lernchat:** Quellenauswahl anhand der Frage, genannte Seiten und Abbildungen haben Vorrang. Mit „Länger nachdenken“ gehen belegte PDF-Seiten vollständig und bis zu zwei Abbildungen als Bild an das Modell (`backend/pdf_figures.py`); der Modul-Import beschreibt Abbildungen einmal lokal.
- **Texterkennung (OCR):** Gescannte PDFs ohne Textebene werden lokal mit RapidOCR gelesen (`backend/ocr.py`). Neue Pakete in `requirements.txt` (`pypdfium2`, `pillow`, `rapidocr`, `onnxruntime`).
- **Aufbereiten:** neues Modul direkt anlegen, Dokumentart je Datei wählbar, Klausuren und Übungen werden mit aufbereitet, freie Modulangaben (Modulnummer optional, freie Einheitenbezeichnungen).
- **Dokumente:** Spalte „Stand“ statt „Zur Prüfung“, Entfernen verschiebt in `data/papierkorb/` (`backend/document_trash.py`).

**Tests:** 453 automatische Tests bestanden (ohne die OCR-Pakete, in einer Arbeitskopie). Der Bau der Oberfläche wurde für diese Übernahme nicht erneut ausgeführt.

**Hinweis:** Nach dem Aktualisieren einmal `Installation.command` ausführen (neue Pakete, Oberfläche bauen).

---

## 11.11.2026 – Dateierkennung lässt Kopien des Programms im Studienordner aus

**Anlass:** Beim Umzug eines älteren Hubs auf diese Fassung liegt der alte Programmordner weiter im Studienordner. Seine Anleitungen, Logs und Sicherungen wären als Lernunterlagen eingelesen worden.

**Änderung (`backend/documents.py`):** Ein Ordner, der `launcher.py`, `backend/main.py` und einen Ordner `frontend` enthält, wird beim Einlesen als Ganzes übersprungen. Der laufende Programmordner war schon bisher ausgenommen.

**Tests:** `tests/test_documents.py` um einen Fall ergänzt.

**Rückgängig machen:** `_is_hub_copy` und seinen Aufruf in `scan_documents` entfernen.

---

## 11.11.2026 – Abzweig „Entwicklung“: Anforderungen, Auftrag durch das KI-Modell, Einstufung, Übergabe-Prompt

**Anlass:** Änderungen am Hub sollen im Hub selbst erfasst und mit dem lokalen KI-Modell vorbereitet werden. Reicht das lokale KI-Modell nicht, soll ein fertiger Prompt für eine externe KI entstehen.

**Server (`backend/development.py`, `backend/main.py`, `backend/local_model.py`):** Neuer Baustein `development` mit `GET /api/development`, `POST /api/development/requests`, `GET/PATCH /api/development/requests/{id}` und `POST /api/development/requests/{id}/order`. Das KI-Modell sieht Anforderung, Dateiindex des Programms und einen Auszug aus dem Architekturlog, aber keinen Quelltext und keine Lerninhalte. Der Hub übernimmt nur belegte Dateien, ergänzt zugehörige Tests, stuft nach festen Regeln als „lokal machbar“ oder „extern übergeben“ ein und baut den Prompt selbst. Anforderungen liegen in der Datenbank unter `development:requests`.

**Regeln (`docs/entwicklungsregeln.md`):** Neue Datei; ihr Inhalt geht in jeden Prompt. Ohne die Datei gelten fünf eingebaute Standardregeln.

**Oberfläche (`frontend/src/Development.tsx`, `development.css`, `App.tsx`, `components.tsx`, `types.ts`):** Neue Seite „Entwicklung“ mit Anforderung erfassen, Liste mit Status, Auftrag, Einstufung und Prompt zum Kopieren. Der Menüpunkt erscheint nur bei aktivem Baustein. Neues Symbol `code`.

**Abschaltliste:** `features` kennt jetzt `development`. Wer in `tutor.local.json` eine eigene Liste führt, muss `development` ergänzen, sonst bleibt die Seite ausgeblendet.

**Nicht enthalten:** Das lokale KI-Modell ändert keinen Code; „lokal machbar“ ist nur eine Einstufung. Keine Spracheingabe auf der Seite. Keine Ausarbeitung mit Bonsai.

**Tests:** Neu `tests/test_development.py`. `tests/test_features.py` an den vierten Baustein angepasst.

**Geprüft:** Automatische Tests und ein Durchlauf im Browser mit einem Platzhalter für Ollama, in normaler Breite und auf 390 Pixel. Nicht geprüft: Lauf mit einem echten KI-Modell, Lauf auf einem Mac.

**Rückgängig machen:** `backend/development.py`, `frontend/src/Development.tsx`, `frontend/src/development.css`, `docs/entwicklung.md`, `docs/entwicklungsregeln.md` und `tests/test_development.py` löschen; die Anmeldung in `backend/main.py`, `development` in `FEATURES` (`backend/local_model.py`), Menüpunkt und Seite in `App.tsx` sowie die Typen in `types.ts` entfernen; `tests/test_features.py` zurücksetzen. Gespeicherte Anforderungen bleiben in der Datenbank und stören nicht.

---

## 11.11.2026 – Aufbereiten in der Homepage: Upload, Start pro Einheit, Veröffentlichen, Big Picture

**Veröffentlichen pro Einheit (`backend/module_import.py`, `backend/content_files.py`):** Gibt es für ein Modul schon Lernseiten, übernimmt das Veröffentlichen nur Einheiten, die dort fehlen, und ergänzt Modulüberblick und Lernpfad. Vorher wird geprüft und gesichert (`data/backups/`).

**Upload (`backend/upload.py`):** `POST /api/documents/upload` legt Unterlagen im Modulordner des Studienordners ab. Grenzen: 300 MB, nur bekannte Dateitypen und `.mp4`, kein Überschreiben, keine Pfade.

**Übersicht (`backend/module_import.py`):** `GET /api/module-import/overview` nennt je Einheit die Unterlagen, ob sie verwertbar sind, und den Stand (Entwurf, veröffentlicht). Vorschau und Übersicht nutzen dieselbe Regel.

**Big Picture (`backend/big_picture.py`, `backend/local_generation.py`, `backend/learning_pages.py`):** Neuer Baustein mit `GET/POST /api/big-picture` und `POST /api/big-picture/publish`. Ein vorhandenes Big Picture wird nur auf ausdrückliche Bestätigung ersetzt. Neue optionale Felder `units` und `generated_by`.

**Quellenwahl (`backend/module_import.py`):** PDFs, die der Hub weder als Lehrbrief noch als Folien erkennt, werden aufbereitet, wenn die Einheit nichts Besseres hat. Bisher blieben sie außen vor, was hochgeladene Dateien mit freiem Namen ausschloss.

**Abschaltliste (`backend/local_model.py`, `backend/main.py`, `launcher.py`):** `features` in `tutor.local.json`; `/api/settings` nennt die aktiven Bausteine.

**Fehler behoben (`backend/tutor.py`):** Der Modellwechsel im Lernchat entfernte `study_folder` aus `tutor.local.json`. Er behält jetzt alle Einstellungen außer Anbieter und KI-Modell.

**Oberfläche (`frontend/src/ModuleImport.tsx`, `module-import.css`, `App.tsx`, `Documents.tsx`, `types.ts`, `ModuleBigPicture.tsx`):** Neue Seite „Aufbereiten“ mit den Schritten Modul wählen, Unterlagen hochladen, Einheiten, Aufbereiten und Big Picture. Der Menüpunkt erscheint nur bei aktivem Baustein. Ein erzeugtes Big Picture trägt auf der Lernseite den Vermerk zu Herkunft und Stand.

**Geprüft:** Automatische Tests und ein Durchlauf im Browser mit einem Platzhalter statt eines KI-Modells. Nicht geprüft: echter Lauf mit Ollama, Lauf auf einem Mac.

**Rückgängig machen:** `backend/upload.py`, `backend/big_picture.py`, `backend/content_files.py`, `backend/local_generation.py`, `frontend/src/ModuleImport.tsx` und `module-import.css` löschen und die Anmeldung der Routen in `backend/main.py` sowie den Menüpunkt in `App.tsx` entfernen; für das Veröffentlichen `publish()` in `backend/module_import.py` auf den Stand vom 10.11. zurücksetzen.

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


## 12.11.2026 - Live-Modellmessungen fortgesetzt

**Was:** Zugriff auf die lokalen Laufzeiten geprüft; 18 Pilotantworten mit echten Token-/Cache-/Zeitwerten gespeichert. Separaten Hub mit Datenbankkopie für den vollständigen Anfrageweg gestartet. Ergebnisse und offene Abnahme in `docs/llm-live-pilot-2026-11-12.md`; bisherige Performance-Dokumente um aktuellen Status und eingeschraenkte Cache-Aussagen ergänzt. Keine weitere Änderung am Anwendungscode oder an der Standardmodellauswahl.

**Warum:** Der vorherige Lauf war am Netzwerkzugriff gescheitert; Cache-Wirkung und Provider-Messwerte mussten im echten Betrieb geprüft werden.

**Daten:** `data/benchmarks/2026-11-12-live-resume/` enthält Prompts, Rohantworten, Laufzeitübergaenge, Messskripte und Code-Prüfsummen. Bestehende Messungen wurden nicht überschrieben.

**Rückweg:** Vorherige Dokumente sind in `data/benchmarks/2026-11-12-live-resume/docs-before.tar.gz` gesichert. Nur diese Dokumentationsfortsetzung zurücknehmen; vorherige uncommittierte Implementierungen beibehalten. Die Pilotmessungen ändern keine Lerninhalte.
