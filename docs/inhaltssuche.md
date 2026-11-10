# Wörter und Themen in Lerninhalten suchen

Stand: 15. Oktober 2026.

## Bedienung

Oben auf jeder Seite öffnet die Lupe **Inhalte durchsuchen** die Suche. Derselbe Einstieg steht in der seitlichen Navigation. Der Dialog überlagert die aktuelle Seite: Ein ungesendeter Antwortentwurf bleibt beim Öffnen und Schließen erhalten.

1. Einen Fachbegriff oder wichtige Wörter aus der Aufgabe eingeben, zum Beispiel **symbolisches Kapital**.
2. Bei Bedarf das Studienmodul wählen. Voreingestellt ist das aktuell geöffnete Modul; **Alle Module** erweitert die Suche.
3. **Suchen** oder Enter drücken. Die Treffer zeigen Textausschnitte mit hervorgehobenen Suchwörtern.
4. **Zum Lernabschnitt** öffnet die konkrete Stelle und hebt den Abschnitt hervor. Bei Big-Picture-Treffern wird der passende Baustein geöffnet. Quellenlinks öffnen die lokale Unterlage; bei PDFs springt der Link zur tatsächlichen PDF-Seite.

**Weitere Treffer anzeigen** ergänzt die nächsten Fundstellen. Das Schließen funktioniert über das Kreuz, Escape oder einen Klick außerhalb des Dialogs. Suchtext und Modulfilter bleiben während der geöffneten App für das nächste Öffnen erhalten. Ein Seitenneuladen setzt den Suchentwurf zurück. Die Suche speichert keinen Verlauf.

## Was durchsucht wird

- Veröffentlichte Lernseiten: Titel, Lernziele, Absätze, Listen, Tabellen, Hinweise und Bildbeschreibungen.
- Modulübersichten und Big Pictures einschließlich Bausteinen und erklärten Verbindungen.
- Bereits eingelesene lokale Studienunterlagen aus dem Dokumentenindex, einschließlich PDF, DOCX, PPTX, XLSX, Markdown und Text. Auch vorhandene Kursaufgaben und Lösungsvorschläge können gefunden werden. Ein Dateitreffer ist nicht automatisch eine offizielle Musterlösung; beispielsweise sind auch selbst erstellte Zusammenfassungen und automatische Transkripte enthalten.

Alle Suchwörter müssen innerhalb derselben Fundstelle einschließlich ihrer Überschrift vorkommen. Wortteile werden gefunden. Groß-/Kleinschreibung und Akzente werden vereinheitlicht; **ß** und **ss** sind gleichwertig. **Mannlichkeit** findet beispielsweise **Männlichkeit**. Eine Eingabe mehrerer Wörter ist eine gemeinsame Wortsuche, keine exakt vorgeschriebene Wortfolge. Die Oberfläche verlangt mindestens zwei Zeichen und erlaubt höchstens 200 Zeichen.

PDF-Treffer verwenden die echte Seitenzählung ab dem Titelblatt. Word-Dateien werden ohne erfundene PDF-Seite angezeigt; Präsentationen nennen die Folie, Tabellen die Arbeitsblattbezeichnung. Fehlende, fehlerhafte oder offensichtlich veraltete Indexeinträge sowie administrative und interne Anwendungsdateien werden ausgelassen. Die Dokumentenerkennung aktualisiert den Index im vorhandenen Rhythmus; bei neuen Unterlagen kann **Ordner prüfen** helfen.

Videos und Bilder werden nicht erneut analysiert. Durchsuchbar sind die bereits ausgearbeiteten Lerntexte, Bildbeschreibungen und gegebenenfalls vorhandene Texttranskripte. Die vorhandenen Videozeitmarken bleiben als Nachlesestellen erreichbar.

## Lokal und ohne Änderung der Lernstände

`backend/search.py` liest die veröffentlichten Inhaltspakete und den bestehenden Dokumentenindex über eine SQLite-Verbindung im Nur-Lesen-Modus. Es gibt keine neue Extraktion bei jeder Suche, keine Modellanfrage und keine externe Suchmaschine. Die Lern-Datenbank erhält keine Suchhistorie. Das vorhandene lokale Serverzugriffsprotokoll kann die angefragte URL einschließlich Suchbegriffen enthalten. Browser und Betriebssystem verarbeiten wie üblich eigene Laufzeitdaten; der Studienordner liegt unabhängig davon in iCloud Drive.

Die Suche liest keine persönlichen Antwortversuche oder laufenden Klausurzustände. Sie verändert weder Fortschritt noch Wiederholungsplanung. Beim bewussten Wechsel von einem Lerntraining zu einer anderen Lernseite gelten die bisherigen Navigationsregeln für ungesendete Antworten; ein bloßes Öffnen und Schließen der Suche lässt sie erhalten. Quellenlinks öffnen die Unterlage in einem weiteren Tab.

## Umsetzung und Prüfung

Der lesende Endpunkt ist `GET /api/search?q=...&module_id=...&limit=30&offset=0`. `module_id` ist optional. Höchstens 100 Treffer pro Abruf und 200 Zeichen je Suchanfrage. Die Oberfläche lädt jeweils 30 Treffer. Antworten bestehen aus reinen Texten und geprüften lokalen Navigationszielen; Hervorhebungen entstehen mit React ohne HTML aus Suchergebnissen.

Zwölf gezielte Suchtests prüfen Wortsuche, Unicode, Modulgrenzen, genaue PDF-Seiten, andere Dateitypen, sichere Quellenpfade, Begrenzung, unveränderte Dateien/Daten und ausbleibende Netzwerkaufrufe. Der vollständige Backendlauf umfasst 156 erfolgreiche Tests. TypeScript-Prüfung und Produktionsbuild bestehen. Die unabhängige Codeprüfung fand einen Fehler beim erneuten Öffnen desselben Suchtreffers; ein eigener Navigationszähler sorgt nun auch dabei für den Sprung zur richtigen Stelle.

Die tatsächlichen 375 Fragen, 31 Originalübungen, drei Lernversuche, zwei Fortschrittsdatensätze und null Klausuren wurden vor und nach der Prüfung vollständig verglichen und bleiben unverändert. Sicherung vor der Änderung: `data/backups/vor-inhaltssuche-20261015-203609/`.
