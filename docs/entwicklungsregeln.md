# Regeln für Änderungen am Hub

- Lies zuerst `logs/Architekturlog.md` und die betroffenen Dateien vollständig. Ändere nichts, was du nicht gelesen hast.
- Halte die Grundsätze aus dem Architekturlog ein: Das KI-Modell schreibt keinen Zustand, es sieht nur, was der Hub auswählt, und alles bleibt lokal (Server nur auf `127.0.0.1`, keine Aufrufe ins Internet).
- Übernimm den Stil des vorhandenen Codes: knappe Funktionen, deutsche Meldungen für Nutzer, englische Docstrings und Kommentare nur dort, wo sie etwas erklären, das der Code nicht zeigt.
- Füge keine Abhängigkeiten in `requirements.txt` oder `frontend/package.json` hinzu, ohne vorher zu fragen.
- Jede neue Funktion bekommt Tests, die bei einem Fehler wirklich fehlschlagen. Vorhandene Tests änderst du nur, wenn sich das Verhalten laut Auftrag ändert.
- Überschreibe und lösche nichts, was Nutzerdaten sein kann: `content/`, `imports/`, `planning/`, `data/`, `tutor.local.json` und der Studienordner. Vor einer Änderung an einer vorhandenen Datei in `content/` legst du eine Sicherung unter `data/backups/` an.
- Schreibe Dateien über eine temporäre Datei im selben Ordner und ersetze dann das Ziel.
- Ein neuer Baustein meldet seine Routen in einer eigenen Datei an und lässt sich über `features` in `tutor.local.json` abschalten.
- Dokumentiere jede Änderung in `logs/Aenderungslog.md` (was, warum, wie rückgängig) und Entscheidungen zum Aufbau in `logs/Architekturlog.md`. Neue Bedienung beschreibst du in `docs/`.
- Prüfe am Ende mit der ganzen Testsuite und einem Bau der Oberfläche. Sag ausdrücklich, was du nicht prüfen konntest, zum Beispiel einen Lauf mit einem echten KI-Modell.
- Committe nicht und lade nichts hoch, ohne dass ich es ausdrücklich verlange.
