# Modul-Import mit dem lokalen KI-Modell

Neue Module lassen sich mit dem lokal angebundenen Ollama-Modell aufbereiten. Aus den erfassten Kursunterlagen entstehen ein **Lernseiten-Entwurf** und **Übungsfragen**. Nichts wird still übernommen: Fragen warten als Importdatei auf die Prüfung unter „Dokumente“, Lernseiten bleiben ein Entwurf, bis sie ausdrücklich veröffentlicht werden.

## Ablauf

In der Homepage führt die Seite „Aufbereiten“ durch dieselben Schritte: Unterlagen hochladen, Einheiten wählen, Vorschau, starten, veröffentlichen, Big Picture. Die Bedienung beschreibt `docs/inhalte-einbinden.md`. Im Terminal:

1. Modulordner im Studienordner ablegen und im Hub unter „Dokumente“ synchronisieren. Lehrbriefe brauchen eine Kurseinheit (wird aus Dateinamen wie `10001-02-S#1-…pdf` erkannt, sonst von Hand zuordnen).
2. Vorschau ohne Modellaufruf: `.venv/bin/python tools/import_module.py --module 10001 --preview`
3. Probelauf mit einer Kurseinheit: `.venv/bin/python tools/import_module.py --module 10001 --unit 1`
4. Ergebnis prüfen:
   - Fragen: `imports/<modul>_einheit<N>_lokal.json` erscheint nach dem Synchronisieren unter „Dokumente“ als offener Import mit Vorschau. Alle Fragen tragen `verified: false` und `generated_by: Lokales Modell (<Modell>)`.
   - Lernseiten: `imports/entwuerfe/<Modulnummer>-learning-pages.json`.
5. Veröffentlichen der Lernseiten: `.venv/bin/python tools/import_module.py --module 10001 --publish`. Vorhandene Lernseiten werden nie überschrieben: Gibt es für das Modul schon eine Datei in `content/`, übernimmt das Veröffentlichen nur Einheiten, die dort noch fehlen, und ergänzt Modulüberblick und Lernpfad. Big Picture und alle übrigen Felder bleiben unverändert. Vor dem Ändern liegt eine Kopie unter `<Datenordner>/backups/`.

Dieselben Schritte stehen als API bereit (`GET /api/module-import/preview`, `POST /api/module-import`, `GET /api/module-import`, `POST /api/module-import/cancel`, `POST /api/module-import/publish`). Dazu kommen:

- `GET /api/module-import/overview?module_id=…`: je Einheit die Dokumente (mit `usable` und Grund), Zahl der Entwurfs- und veröffentlichten Lernseiten. Es gelten dieselben Regeln wie in der Vorschau.
- `POST /api/documents/upload?module_id=…&filename=…&unit=…`: legt eine weitere Unterlage ab (Dateiinhalt als roher Request-Body). Ziel ist der Modulordner, mit `unit` der Unterordner `Einheit <n>`. Höchstens 300 MB, nichts wird überschrieben (409), danach wird neu eingelesen.

## Big Picture

Aus den **veröffentlichten** Lernseiten erstellt das lokale Modell einen Entwurf für das Big Picture. Das Modell sieht nur `id`, `unit`, `title`, `summary` und `learning_goals` der Lernseiten und liefert Bausteine und Zusammenhänge nach Position. IDs und Quellen setzt der Hub aus den Lernseiten; Bausteine ohne veröffentlichte Lernseite entfallen.

- `GET /api/big-picture?module_id=…`: Status, veröffentlichtes Big Picture (`stale_units` = Einheiten, die danach veröffentlicht wurden) und Entwurf.
- `POST /api/big-picture` `{module_id}`: startet im Hintergrund; Entwurf unter `imports/entwuerfe/<Modulnummer>-big-picture.json`.
- `POST /api/big-picture/publish` `{module_id, replace?}`: schreibt den Entwurf in die Lernseiten-Datei (vorher Sicherung). Ein vorhandenes Big Picture wird nur mit `replace: true` ersetzt.

Chat, Import und Big Picture teilen sich das Modell und laufen nie gleichzeitig.

## Bausteine abschalten

`tutor.local.json` darf `"features": ["voice", "module_import", "big_picture", "development"]` enthalten; nur die genannten Bausteine sind aktiv. Fehlt der Schlüssel, sind alle aktiv. Zu `module_import` gehören auch Übersicht und Upload. Abgeschaltete Bausteine haben keine Routen; `GET /api/settings` nennt die aktiven unter `features`.

## Wie gearbeitet wird

- **Quellen:** PDFs der Art Lehrbrief; Folien nur, wenn für die Kurseinheit kein Lehrbrief vorliegt; andere PDFs nur, wenn beides fehlt. Unterlagen, die der Hub als Klausur, Lösung, Übung oder Zusammenfassung erkennt, bleiben außen vor. Verzeichnisse und fast leere Seiten werden ausgelassen. Was nicht verwendet wird, nennt die Vorschau mit Grund.
- **Abschnitte:** Aufeinanderfolgende Seiten bis etwa 14.000 Zeichen ergeben einen Modellaufruf und eine Lernseite. Kontextfenster 32.768 Tokens, Antwort bis 6.000 Tokens, strukturierte JSON-Ausgabe.
- **Belege:** Das Modell liefert zu jedem Abschnitt und jeder Frage ein wörtliches Zitat. Der Hub sucht das Zitat selbst in den Seitentexten und setzt die PDF-Seite; das Modell vergibt keine Seitenzahlen. Fragen ohne auffindbares Zitat werden verworfen, Abschnitte ohne auffindbares Zitat bleiben mit Prüfhinweis und dem Seitenbereich des Ausschnitts erhalten.
- **Fortsetzen:** Jede fertige Modellantwort liegt in `data/module-import/`. Ein abgebrochener oder wiederholter Lauf fragt nur fehlende Abschnitte neu an. Ein anderes Modell oder eine geänderte Quelldatei erzeugt neue Antworten.
- **Gleichzeitigkeit:** Im Hub gestartet, teilt sich der Import das Modell mit dem Lernchat; während eines Abschnitts meldet der Chat „beantwortet gerade eine Frage“.

## Grenzen

- Das Big Picture entsteht in einem eigenen Schritt (siehe oben), nicht im Import. Keine Tabellen, keine Abbildungen, keine Videotranskripte; der Modulüberblick wird aus den Lernseiten zusammengestellt.
- Eine veröffentlichte Einheit lässt sich über den Import nicht neu erzeugen.
- Aufbereitung und Big Picture sind bisher nur mit einem Platzhalter statt eines echten KI-Modells geprüft.
- Abschnitte folgen Seitenumfang, nicht Kapitelgrenzen.
- Einsendearbeiten werden nicht aufbereitet; sie entstehen von Hand nach `docs/inhalte-einbinden.md`.
- Die Zeitangabe der Vorschau (fünf Minuten je Abschnitt) ist eine grobe Annahme und noch nicht gemessen.
- Fachliche Richtigkeit prüft niemand automatisch; der Zitatabgleich belegt nur, dass die Stelle existiert.
