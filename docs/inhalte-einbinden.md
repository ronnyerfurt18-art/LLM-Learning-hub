# Eigene Lerninhalte einbinden

Diese Anleitung führt vom leeren Hub zum eigenen Modul. Als Vorlage dient das Demo-Modul „Lernen lernen“ im Ordner `demo/`; jede hier beschriebene Datei gibt es dort als vollständiges Beispiel.

## Überblick

| Was | Wo es liegt | Wie es entsteht |
|---|---|---|
| Originalunterlagen (PDF, Word, PowerPoint, Excel, Text, Markdown, MP4) | Studienordner | Du legst sie ab |
| Module | Datenbank | Automatisch aus dem Ordnernamen oder unter „Meine Module“ |
| Fragen | `imports/*.json` | Modul-Import, externe KI oder von Hand |
| Lernseiten und Big Picture | `content/*.json` | Modul-Import, externe KI oder von Hand |
| Einsendearbeiten | `content/assignments/*.json` | Externe KI oder von Hand |
| Lernziele für das Lernprotokoll | `content/tutor/goals.json` | Von Hand |
| Feste Termine | `planning/study-events.json` | Von Hand |

Der Hub prüft jede Datei beim Laden. Er zeigt nur Inhalte an, deren Quellenangaben auf vorhandene Dateien und Seiten im Studienordner verweisen. Fehler erscheinen mit Dateiname und Stelle auf der betroffenen Seite.

## 1. Studienordner festlegen

Der Studienordner enthält deine Originalunterlagen. Der Hub liest ihn nur und ändert dort nichts.

- Standard: `~/LearningHub/Studium`. Der Ordner wird beim ersten Start angelegt.
- Anderer Ordner: in `tutor.local.json` den Schlüssel `"study_folder"` setzen, zum Beispiel `"~/Documents/Studium"`.
- Der Studienordner darf nicht im Programmordner liegen.

Der Hub liest den Studienordner vollständig ein, mit allen Unterordnern. Wähle deshalb einen Ordner, der nur Lernunterlagen enthält.

## 2. Modul anlegen

**Automatisch:** Lege im Studienordner je Modul einen Ordner an, dessen Name mit einer fünfstelligen Modulnummer beginnt, zum Beispiel `10001 Lernen lernen`. Beim Einlesen entsteht daraus das Modul.

**Von Hand:** Unter „Meine Module“ → „Modul hinzufügen“ Name, fünfstellige Modulnummer, Anzahl der Einheiten und das Dokumentenverzeichnis (Pfad innerhalb des Studienordners) eintragen.

Im selben Fenster legst du fest, wie die nummerierten Teile des Moduls heißen: Einheit, Session, Kapitel, Lektion oder Woche.

## 3. Unterlagen ablegen und einlesen

1. Dateien in den Modulordner legen. Oder in der Homepage unter „Aufbereiten“ hochladen: Modul wählen, Dateien auswählen, auf Wunsch die Einheit wählen. Der Hub legt sie im Modulordner ab, bei gewählter Einheit im Unterordner `Einheit <n>`. Vorhandene Dateien überschreibt er nie; je Datei sind höchstens 300 MB möglich.
2. Im Hub „Dokumente“ öffnen und synchronisieren. Der Hub prüft den Ordner außerdem alle 30 Sekunden.
3. Zuordnung prüfen: Jedes Dokument zeigt Modul, Einheit und Art.

Die Einheit erkennt der Hub aus dem Namen:

| Muster | Beispiel | Ergebnis |
|---|---|---|
| `<Modulnummer>-<Einheit>-…` | `10001-02-S#1-demo.pdf` | Einheit 2 |
| Wort und Zahl im Dateinamen | `Einheit 3 Folien.pdf`, `Session4.pdf`, `KE 1.pdf` | Einheit 3, 4, 1 |
| Wort und Zahl im Ordnernamen | `Lektion 5/skript.pdf` | Einheit 5 |

Passt nichts, ordnest du die Einheit unter „Dokumente“ von Hand zu.

## 4. Fragen und Lernseiten erzeugen

Es gibt drei Wege. Sie lassen sich mischen.

### Weg A: Aufbereiten mit dem lokalen KI-Modell

Das lokale KI-Modell liest die PDF-Unterlagen und entwirft Lernseiten und Fragen. Der Hub prüft jedes Zitat gegen den Seitentext und setzt die Seitenzahlen selbst.

In der Homepage unter „Aufbereiten“:

1. Modul wählen. Die Seite zeigt je Einheit die Unterlagen und den Stand.
2. Einheiten ankreuzen und „Vorschau“ wählen. Die Vorschau nennt die Dateien, die Zahl der Abschnitte, die geschätzte Dauer und was ausgelassen wird.
3. „Aufbereitung starten“. Der Lauf zeigt den Fortschritt und lässt sich abbrechen; fertige Abschnitte bleiben erhalten.
4. „Lernseiten veröffentlichen“. Sind für das Modul schon Lernseiten veröffentlicht, kommen nur die neuen Einheiten dazu. Die Fragen bestätigst du unter „Dokumente“.
5. „Big Picture erstellen“. Das KI-Modell schlägt Leitfrage, Bausteine und Beziehungen vor; der Hub ordnet Lernseiten und Quellen zu. Du siehst den Entwurf und veröffentlichst ihn selbst. Kommt später eine Einheit dazu, meldet die Seite das Big Picture als veraltet und bietet „erneuern“ an.

Welche Dateien verwendet werden: je Einheit zuerst Lehrbriefe, sonst Folien, sonst andere PDFs. Als Lehrbrief gilt eine Datei mit dem Namensmuster `<Modulnummer>-<Einheit>-…` oder mit „Skript“, „Kurseinheit“ oder „Studienbrief“ im Namen, als Folien eine mit „Folien“, „Vorlesung“ oder „Slides“. Dateien, deren Name auf Klausur, Lösung, Übung oder Zusammenfassung hindeutet, und alles außer PDF werden nicht aufbereitet.

Dieselben Schritte im Terminal:

```bash
.venv/bin/python tools/import_module.py --module 10001 --preview   # zeigt, was gelesen würde
.venv/bin/python tools/import_module.py --module 10001 --unit 1    # Probelauf mit einer Einheit
.venv/bin/python tools/import_module.py --module 10001             # alle Einheiten
.venv/bin/python tools/import_module.py --module 10001 --publish   # geprüften Lernseiten-Entwurf veröffentlichen
```

Die Fragen erscheinen unter „Dokumente“ als offener Import und werden erst nach deiner Bestätigung übernommen. Einzelheiten und Grenzen: `docs/modul-import.md`.

### Weg B: Eine externe KI erzeugt die Dateien

Gib der KI die Unterlagen einer Einheit, `docs/import-format.md` und die passende Demo-Datei als Vorlage. Auftrag zum Beispiel:

> Lies die beigefügte Unterlage für Modul 10001, Einheit 2. Erstelle belegte Übungsfragen im Format von docs/import-format.md nach dem Muster von demo/imports/lernen_lernen_einheit1.json. Jede Frage nennt Quelldatei und PDF-Seite. Setze `verified` auf false.

Die Ergebnisdatei legst du in `imports/` ab (Fragen) oder in `content/` (Lernseiten).

### Weg C: Von Hand

Kopiere die passende Demo-Datei, benenne sie um und ersetze die Inhalte.

## 5. Fragenpakete (`imports/*.json`)

- Format: `docs/import-format.md`. Beispiel: `demo/imports/lernen_lernen_einheit1.json`.
- Eine neue Datei erscheint unter „Dokumente“ mit Vorschau. Erst deine Bestätigung übernimmt die Fragen.
- Dateien, die in `imports/seed.json` stehen, werden beim Start ohne Rückfrage geladen. `seed.json` ist eine Liste von Dateinamen: `["lernen_lernen_einheit1.json"]`.
- Vorhandene Fragen-IDs werden übersprungen, ihr Lernfortschritt bleibt erhalten.
- Bilder zu Fragen liegen unter `imports/assets/`.

## 6. Lernseiten (`content/*.json`)

Eine Datei je Modul. Beispiel: `demo/content/lernen-lernen-learning-pages.json`.

| Feld | Inhalt |
|---|---|
| `schema_version` | `1` |
| `module_number`, `module_title` | Fünfstellige Modulnummer als Text und Titel |
| `overview` | Titel, Absätze, Quellen, Liste der Einheiten, Lernpfad, optional `big_picture` |
| `overview.big_picture` | Leitfrage, Bausteine (`nodes`) und Beziehungen (`connections`); Bausteine verweisen über `lesson_ids` auf Lernseiten. Optional `units` (Liste der eingeflossenen Einheiten) und `generated_by` (Herkunft); beide setzt der Hub, wenn er das Big Picture erstellt |
| `lessons` | Je Lernseite: `id`, `unit`, Titel, Zusammenfassung, Lernziele, Abschnitte, `exercise_ids` |
| `lessons[].sections` | `id`, Titel, Absätze, optional `bullets`, `table`, `note`; mindestens eine Quelle |

Jede Quelle nennt `path` (relativ zum Studienordner), `title`, `pdf_page` und optional `chapter`, `pdf_page_end`, `printed_page`. Videos verwenden `kind: "video"` mit `timestamp_seconds`. `exercise_ids` verknüpft Fragen aus den Fragenpaketen mit der Lernseite.

Die genaue Schnittstelle steht in `docs/api-contract.md`.

## 7. Einsendearbeiten (`content/assignments/*.json`)

Eine Datei je Arbeit. Beispiel: `demo/content/assignments/lernen-lernen-uebung1.json`. Jede Frage besteht aus Aussagen, die als wahr oder falsch zu beurteilen sind.

| Feld | Inhalt |
|---|---|
| `id` | Eindeutig; Kleinbuchstaben, Ziffern, Bindestriche |
| `module_number` | Modulnummer des zugehörigen Moduls |
| `title`, `due_date` | Titel und Abgabedatum (`JJJJ-MM-TT`) |
| `source` | Das Aufgabenblatt als PDF im Studienordner: `path`, `title`, `pdf_page` |
| `solution_note` | Hinweis zur Herkunft der Lösungen |
| `questions[]` | `id` (beginnt mit der ID der Arbeit und `-q`), `number` (fortlaufend ab 1), `title`, `prompt`, `source_page`, `options` |
| `options[]` | `id` (A, B, C …), `text`, `is_correct`, `explanation`, `sources` |
| `rules` (optional) | Feste Form: `question_count`, `option_count`, `min_true`, `points` |

Regeln, die der Hub prüft:

- Je Frage zwei bis acht Aussagen. Jede Aussage braucht eine Erklärung und mindestens eine Quelle.
- Die Quelle einer Aussage muss eine andere Datei sein als das Aufgabenblatt. Sie belegt die Theorie.
- `points` ist eine Punktetabelle mit einem Wert je Anzahl korrekt beurteilter Aussagen, zum Beispiel `[0, 1, 10, 30, 60, 100]` bei fünf Aussagen. Ohne Tabelle zählt der Anteil korrekt beurteilter Aussagen.

Die Arbeiten erscheinen auf der Lernseite des Moduls im Reiter „Einsendearbeiten“. Im Lernchat genügt „Bereite mich auf Einsendearbeit 1 vor“; der Hub führt dann Frage für Frage durch die Arbeit. Der KI-Planer berücksichtigt die Arbeiten bei Lernstrecken.

## 8. Lernziele (`content/tutor/goals.json`)

Eine Liste für alle Module. Beispiel: `demo/content/tutor/goals.json`.

| Feld | Inhalt |
|---|---|
| `id` | Eindeutig |
| `module_id` | `M-` und Modulnummer, zum Beispiel `M-10001` |
| `lesson_id`, `section_id` | Lernseite und Abschnitt, zu denen das Ziel gehört |
| `title`, `question` | Titel und Prüffrage |
| `criteria` | Antwortkriterien für die Selbsteinschätzung |
| `sources` | Quellen wie bei den Lernseiten |

Die Ziele erscheinen im Lernchat. Nach deiner Antwort gleichst du sie mit den Kriterien ab und speicherst deine Selbsteinschätzung. Der Hub plant die Wiederholung.

## 9. Feste Termine (`planning/study-events.json`)

Eigene Lernblöcke und Fristen trägst du direkt unter „Planung“ ein. Die Datei ist nur für Termine gedacht, die mit Quelle belegt vorgegeben werden sollen.

```json
{
  "schema_version": 1,
  "notes": [],
  "events": [{
    "id": "lernen-lernen-klausur",
    "module_id": "M-10001",
    "title": "Klausur Lernen lernen",
    "kind": "exam",
    "start": "2030-12-31T10:00:00+01:00",
    "end": "2030-12-31T12:00:00+01:00",
    "all_day": false,
    "description": ""
  }]
}
```

- `kind`: `deadline`, `exam`, `teaching`, `phase` oder `study`. Fristen können `category` tragen: `submission`, `registration`, `reenrollment`, `other`.
- Ganztägige Termine: `"all_day": true` und Datum ohne Uhrzeit (`"2030-12-31"`); ein Enddatum ist exklusiv.
- Uhrzeiten brauchen eine Zeitzonenangabe. Die Planung rechnet in Europe/Berlin.
- Optional: `location`, `date_note`, `source` (Quelle im Studienordner).

## 10. Prüfen

1. Hub neu starten. Lernseiten und Einsendearbeiten liest der Hub bei jedem Aufruf frisch; Startpakete und Lernziele nur beim Start.
2. „Meine Module“: Das Modul zeigt die erwartete Zahl an Fragen und Einheiten.
3. „Lernpages“: Die Lernseiten öffnen sich; jeder Quellenlink springt zur richtigen PDF-Seite.
4. „Dokumente“: keine Einträge mit Fehlerstatus.

Zum Vergleich lässt sich jederzeit das Demo-Modul einrichten: `python3 tools/install_demo.py`.
