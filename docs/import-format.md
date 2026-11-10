# Fragenimport Version 1

JSON-Dateien werden als UTF‑8 gespeichert. Vollständiges Beispiel: `demo/imports/lernen_lernen_einheit1.json`. Wie die Dateien eingebunden werden, steht in `docs/inhalte-einbinden.md`.

```json
{
  "schema_version": 1,
  "module": {"name": "Beispielmodul", "number": "12345", "unit_count": 1},
  "originals": [],
  "questions": [{
    "id": "12345-E1-001", "unit": 1, "topic": "Begriff",
    "type": "flashcard", "question": "Was bedeutet der Begriff?",
    "source": "12345 Beispiel/Einheit1/uebungen.md", "source_page": 1,
    "original_question": "Was bedeutet der Begriff?",
    "original_solution": "Originaldefinition aus der Quelle.",
    "model_answer": "Originaldefinition aus der Quelle.",
    "explanation": "Eine klar definierte Karteikarte auf Basis der Quelle.",
    "keywords": ["Originaldefinition"], "checklist": ["Definition nennen"],
    "difficulty": 1, "verified": false, "generated_by": "Eigene Ausarbeitung"
  }],
  "coverage": []
}
```

Pflichtfelder jeder Frage: ID, Einheit ab 1, Thema, Typ, Fragestellung, Quellenpfad, ursprüngliche Frage und Lösung, Musterantwort, Erklärung, Schwierigkeit 1–3, Prüfstatus als Boolean und Herkunft. Für PDFs sind `source_page` echte Seiten; für DOCX/XLSX/TXT sind es logische Abschnitte, Tabellenblätter oder Textabschnitte. Optionale `correction_note` enthält einen gesonderten fachlichen Hinweis, ohne `original_solution` zu ändern. `originals` speichert die vollständigen Originalübungen zusätzlich und ist kein Ersatz für die Quellenangaben jeder Variante.

Neu entwickelte Übungen auf Grundlage eines Lehrbriefs können `source_kind: "course_material"` verwenden. Die Oberfläche nennt ihren Quellenbereich dann **Quellen & Herleitung**, statt Originalfrage und offizielle Originalmusterlösung zu behaupten. Die Pflichtfelder `original_question` und `original_solution` erklären in diesem Fall ausdrücklich die eigene Entwicklung und die fehlende offizielle Originallösung. Sie dürfen keine erfundene offizielle Vorlage enthalten.

Optionale `theory_sources` belegen die Erklärung unabhängig von der Ursprungsaufgabe. PDF-Einträge haben `path` (relativ zum Studienverzeichnis), `title`, `pdf_page` (ab 1) sowie optional `kind: "pdf"`, `chapter`, `pdf_page_end` und `printed_page` (Text, z. B. `"10–12"`). Die Startseite eines Bereichs wird direkt geöffnet. Beispiel:

```json
{"path":"10001 Lernen lernen (Demo)/10001-01-S#1-demo.pdf","title":"Lernen lernen · Kurseinheit 1","chapter":"1.2 Ein klassischer Befund","pdf_page":2,"pdf_page_end":2,"printed_page":"2"}
```

Videobelege haben `kind: "video"`, einen relativen MP4-Pfad, `title`, `timestamp_seconds` und optional `timestamp_end_seconds` sowie `chapter`. Zeitmarken sind endliche Zahlen ab 0; ein Ende darf nicht vor dem Anfang liegen. PDF-Seitenfelder gehören nicht in Videobelege. Beispiel:

```json
{"kind":"video","path":"10001 Lernen lernen (Demo)/Videos/einheit1-video1.mp4","title":"Einheit 1 · Video 1","chapter":"Abrufübung","timestamp_seconds":237,"timestamp_end_seconds":325}
```

Dieselbe Quellenstruktur gilt für Lernseiten. Videos werden lokal geöffnet, ohne sie beim Serverstart vollständig in den Arbeitsspeicher zu laden. Video-Fragen verwenden `source_page: null`; ihre genaue Stelle steht im Videobeleg.

Theorie-Lernpages liegen unabhängig von der Fragenbank unter `content/`. Das vollständige Beispiel `demo/content/lernen-lernen-learning-pages.json` enthält Modulüberblick, Einheiten, Lernziele, Abschnitte mit Quellen und verknüpfte `exercise_ids`. Reine Lesezugriffe importieren keine neuen Fragen und ändern keinen Lernfortschritt.

| Typ | Zusätzliche Felder | Antwortformat |
|---|---|---|
| single_choice | options (mindestens 2), correct_answers (ein Index) | Liste von Indizes |
| multiple_choice | options, correct_answers (mehrere möglich) | Liste von Indizes |
| matching | pairs mit term/definition | Objekt Begriff → Definition |
| cloze | text mit ___, answers, optional synonyms (Liste pro Lücke) | Textliste |
| flashcard | model_answer | Selbstbewertung 0/3/4/5 |
| free_text | keywords, checklist | Text + mögliche Selbstbewertung |
| case_analysis | Szenario in question, keywords, checklist | Text + mögliche Selbstbewertung |
| exam_question | Originalfrage in question, keywords, checklist | Text + mögliche Selbstbewertung |

IDs dürfen im Import nicht doppelt vorkommen. Vorhandene IDs werden beim Import übersprungen, ihr Lernfortschritt bleibt erhalten. IDs eines anderen Moduls werden abgelehnt. Neue Fragen erhalten neue IDs. `verified` bedeutet menschlich geprüft; generierte Varianten tragen zunächst false. Fragen werden entweder über **Dokumente → JSON importieren** oder eine Datei in `imports/` angeboten und nach Bestätigung importiert. Eine Vorschau zeigt Fehler vor dem Import.

Originalabbildungen können zusätzlich in `original_question_images` und `original_solution_images` gespeichert werden. Jedes Element hat `path` (z. B. `assets/einheit2/uebung-16-frage.png`), `caption` und `source_page`. Die tatsächliche PNG-/JPG-/WebP-Datei liegt relativ dazu unter `imports/`. Fragebilder dürfen keine Lösung enthalten. Lösungsbilder erscheinen erst nach Abgabe bzw. Aufdecken der Karteikarte. Der Text der Originalmusterlösung bleibt daneben unverändert erhalten; ergänzende Beschreibungen der Diagramme werden als Aufbereitung gekennzeichnet.

Verweist eine Originalaufgabe auf ein Beispiel aus dem Lehrbrief, kann `question_context` die belegte Ausgangssituation enthalten. `question_context_source` hat dafür `path` und `source_page`. Dieser Kontext enthält die Fallangaben, keine Lösungshinweise, und wird auch in einer laufenden Klausur angezeigt. Die Originalfragestellung bleibt separat unverändert gespeichert.

Abdeckungseinträge: `topic`, `coverage` (complete/partial/missing), `method` (keyword/gpt_work/manual), `notes`, `keywords`, `source`, `summary_source`, `unit` (Standard 1 für alte Importe). Automatische Schlagwortsuche kann nur Hinweise auf teilweise/fehlende Abdeckung liefern und vergleicht ausschließlich zu derselben Session zugeordnete Zusammenfassungen. Menschliche Bestätigung wird als eigener Datensatz gespeichert.

Beispiel eines Arbeitsauftrags an eine KI: „Lies die Unterlagen für Modul 10001, Einheit 2. Erstelle belegte Fragen nach docs/import-format.md und speichere sie als imports/lernen_lernen_einheit2.json.“ Die Datei erscheint danach unter „Dokumente“ zur Prüfung.
