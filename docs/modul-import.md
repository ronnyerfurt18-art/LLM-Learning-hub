# Modul-Import mit dem lokalen Modell (Stufe 1)

Neue Module lassen sich mit dem lokal angebundenen Ollama-Modell aufbereiten. Aus den erfassten Kursunterlagen entstehen ein **Lernseiten-Entwurf** und **Übungsfragen**. Nichts wird still übernommen: Fragen warten als Importdatei auf die Prüfung unter „Dokumente“, Lernseiten bleiben ein Entwurf, bis sie ausdrücklich veröffentlicht werden.

## Ablauf

1. Modulordner im Studienordner ablegen und im Hub unter „Dokumente“ synchronisieren. Lehrbriefe brauchen eine Kurseinheit (wird aus Dateinamen wie `10001-02-S#1-…pdf` erkannt, sonst von Hand zuordnen).
2. Vorschau ohne Modellaufruf: `.venv/bin/python tools/import_module.py --module 10001 --preview`
3. Probelauf mit einer Kurseinheit: `.venv/bin/python tools/import_module.py --module 10001 --unit 1`
4. Ergebnis prüfen:
   - Fragen: `imports/<modul>_einheit<N>_lokal.json` erscheint nach dem Synchronisieren unter „Dokumente“ als offener Import mit Vorschau. Alle Fragen tragen `verified: false` und `generated_by: Lokales Modell (<Modell>)`.
   - Lernseiten: `imports/entwuerfe/<Modulnummer>-learning-pages.json`.
5. Veröffentlichen der Lernseiten: `.venv/bin/python tools/import_module.py --module 10001 --publish`. Vorhandene Lernseiten eines Moduls werden nie überschrieben.

Dieselben Schritte stehen als API bereit (`GET /api/module-import/preview`, `POST /api/module-import`, `GET /api/module-import`, `POST /api/module-import/cancel`, `POST /api/module-import/publish`); eine Oberfläche dafür folgt in Stufe 2.

## Wie gearbeitet wird

- **Quellen:** PDFs der Art Lehrbrief; Folien nur, wenn für die Kurseinheit kein Lehrbrief vorliegt. Verzeichnisse und fast leere Seiten werden ausgelassen. Was nicht verwendet wird, nennt die Vorschau mit Grund.
- **Abschnitte:** Aufeinanderfolgende Seiten bis etwa 14.000 Zeichen ergeben einen Modellaufruf und eine Lernseite. Kontextfenster 32.768 Tokens, Antwort bis 6.000 Tokens, strukturierte JSON-Ausgabe.
- **Belege:** Das Modell liefert zu jedem Abschnitt und jeder Frage ein wörtliches Zitat. Der Hub sucht das Zitat selbst in den Seitentexten und setzt die PDF-Seite; das Modell vergibt keine Seitenzahlen. Fragen ohne auffindbares Zitat werden verworfen, Abschnitte ohne auffindbares Zitat bleiben mit Prüfhinweis und dem Seitenbereich des Ausschnitts erhalten.
- **Fortsetzen:** Jede fertige Modellantwort liegt in `data/module-import/`. Ein abgebrochener oder wiederholter Lauf fragt nur fehlende Abschnitte neu an. Ein anderes Modell oder eine geänderte Quelldatei erzeugt neue Antworten.
- **Gleichzeitigkeit:** Im Hub gestartet, teilt sich der Import das Modell mit dem Lernchat; während eines Abschnitts meldet der Chat „beantwortet gerade eine Frage“.

## Grenzen der Stufe 1

- Kein Big Picture, keine Tabellen, keine Abbildungen, keine Videotranskripte; der Modulüberblick wird aus den Lernseiten zusammengestellt.
- Abschnitte folgen Seitenumfang, nicht Kapitelgrenzen.
- Einsendearbeiten werden nicht aufbereitet; sie entstehen von Hand nach `docs/inhalte-einbinden.md`.
- Die Zeitangabe der Vorschau (fünf Minuten je Abschnitt) ist eine grobe Annahme und noch nicht gemessen.
- Fachliche Richtigkeit prüft niemand automatisch; der Zitatabgleich belegt nur, dass die Stelle existiert.
