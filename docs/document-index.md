# Dokumentenindex

Bestandsaufnahme vom 12.10.2026. Das Studienverzeichnis ist direkt lesbar. Die Originaldateien werden ausschließlich gelesen; der Index und die Anwendungsdaten liegen im separaten Ordner `master-learning-hub`.

Erfasst wurden 19 unterstützte Dokumente: 18 PDFs und eine Markdown-Zusammenfassung. Drei Modulordner wurden erkannt. Alle 19 Dokumente enthalten extrahierbaren Text. Die fünf Videos und die Modulübersicht als PNG gehören nicht zu den unterstützten Textformaten und werden nicht als Lernfragen importiert. Im Verlauf der Bestandsaufnahme erschien auch die Musterlösung für Einheit 2 im Studienordner; sie wurde in den Index aufgenommen.

Die vollständigen relativen Dateipfade, Dateigrößen, Seitenzahlen und SHA-256-Prüfsummen stehen in `data/document-inventory.json`. Die folgende Tabelle zeigt den Ausgangsbestand. Die Anwendung aktualisiert ihren Datenbankindex bei jeder Synchronisierung.

| Modul | Dokument | Einheit | Art | Seiten |
|---|---|---:|---|---:|
| 32281 Digitale Diversität | Lösungsvorschläge Übungsaufgaben Einheit 1.pdf | 1 | Musterlösung | 7 |
| 32281 Digitale Diversität | 01-session-1-zusammenfassung.md | 1 | Lernzusammenfassung | 1 logischer Abschnitt |
| 32281 Digitale Diversität | 32281-01-S#1-2002287-V1.0.pdf | 1 | Studienbrief | 66 |
| 32281 Digitale Diversität | folien_session1_WiSe_24_25.pdf | 1 | Vorlesungsfolien | 109 |
| 32281 Digitale Diversität | 32281-02-S#1-2002288-V1.0.pdf | 2 | Studienbrief | 105 |
| 32281 Digitale Diversität | Lösungsvorschläge Übungsaufgaben Einheit 2.pdf | 2 | Musterlösung | 11 |
| 32281 Digitale Diversität | folien_session2_WiSe_24_25.pdf | 2 | Vorlesungsfolien | 123 |
| 32281 Digitale Diversität | Einsendearbeit 1, Abgabe 01.12.2026 | offen | Einsendeaufgabe | 7 |
| 32281 Digitale Diversität | Einsendearbeit 2, Abgabe 15.01.2027 | offen | Einsendeaufgabe | 7 |
| 32711 BI | 32711-01-S#1-S002664941-V1.0.pdf | 1 | Studienbrief | 50 |
| 32711 BI | 32711-02-S#1-S002664968-V1.0.pdf | 2 | Studienbrief | 110 |
| 32711 BI | 32711-03-S#1-2001332-V1.0.pdf | 3 | Studienbrief | 61 |
| 31311 IT GOV | Klausur 31311 ITG SS23_Moodle.pdf | offen | Altklausur | 9 |
| 31311 IT GOV | Klausur 31311 ITG SoSe24_final.pdf | offen | Altklausur | 19 |
| 31311 IT GOV | Klausur 31311 ITG WS2324_vPapier.pdf | offen | Altklausur | 18 |
| 31311 IT GOV | Klausur 31311 ITG WiSe2425_Moodle.pdf | offen | Altklausur | 10 |
| 31311 IT GOV | Klausur 31311_SS25_vMoodle.pdf | offen | Altklausur | 10 |
| Nicht zugeordnet | Belegbogen_8919810_WS2026.pdf | offen | Verwaltung | 1 |
| Nicht zugeordnet | sepa_lastschriftmandat Kopie.pdf | offen | Verwaltung | 1 |

Die laufende Nummer einer Einsendearbeit wird nicht als Kurseinheit interpretiert. Verwaltungsunterlagen bleiben ohne Modulzuordnung und erzeugen keine Lernfragen. Die Kurzbezeichnungen „BI“ und „IT GOV“ werden aus den vorhandenen Ordnernamen übernommen und lassen sich in der Modulverwaltung ändern.

## Zuordnung und Änderungen

Der Scanner erkennt Modulordner, die mit einer fünfstelligen Modulnummer beginnen, auch unter Semesterordnern. Namen wie `Session1`, `Einheit 2` und `Kurseinheit-3` bestimmen die Einheit. Dateinamen im Format `32711-03-…` liefern die Einheit 3. Eine explizite Einheitsangabe im Dateinamen hat Vorrang vor der Ordnerangabe.

Jede unterstützte Datei erhält eine SHA-256-Prüfsumme. Ein identischer Hash nutzt den vorhandenen Text aus der Datenbank. Neue und geänderte Dokumente erhalten eine Importvorschau. Quellen, die während der Extraktion verändert werden, bekommen einen Fehlerstatus und werden beim nächsten Durchlauf erneut verarbeitet. Fehler einer einzelnen Datei verhindern die Erfassung der übrigen Dateien nicht. Falls ein ganzer Unterordner nicht aufgelistet werden kann, wird der unvollständige Durchlauf mit einem klaren Fehler abgebrochen. Der vorhandene Index bleibt erhalten, damit nicht zugängliche Dokumente nicht irrtümlich als gelöscht erscheinen.

Ausgeschlossen werden der gesamte Anwendungsordner, versteckte Ordner, temporäre Office-Dateien, Entwicklungsumgebungen und symbolische Verknüpfungen auf externe Dateien. Symbolische Ordnerverknüpfungen werden zur Vermeidung von Schleifen nicht verfolgt. Die Quelldateien werden nicht verschoben, überschrieben oder umbenannt.

## Unterstützte Textformate

| Format | Extraktion und Quellenangabe |
|---|---|
| PDF | PyMuPDF, ersatzweise pypdf; echte, ab 1 gezählte Dokumentseiten |
| DOCX | Absätze und Tabellen in Dokumentreihenfolge; ein logischer Dokumentabschnitt, keine behauptete Word-Seitenzahl |
| PPTX | Texte, Tabellen, Gruppen und Referentennotizen; Foliennummern ab 1 |
| XLSX | Tabellenblätter und Zellwerte; Formeln bleiben als Formeltext erhalten, keine Neuberechnung oder externen Verknüpfungen |
| TXT | UTF-8 oder UTF-16; Formularvorschub trennt logische Abschnitte |
| Markdown | UTF-8 oder UTF-16; unveränderter Quelltext und logische Abschnitte |

PDFs ohne lesbare Textebene (Scans, Fotos) werden lokal per Texterkennung gelesen (`backend/ocr.py`, RapidOCR mit mitgelieferten ONNX-Modellen, Seiten mit 200 dpi gerendert); erkannte Seiten sind mit `ocr` markiert, das Dokument nennt `ocr_pages`. Fehlt das Paket `rapidocr`, erhält das Dokument einen sichtbaren Hinweis mit dem Installationsschritt; bleibt auch die Texterkennung leer, einen eigenen Fehler. Kennwortgeschützte PDFs erhalten einen eigenen Fehlerhinweis. Weder OCR noch die Verarbeitung von Bildern oder Videos wird stillschweigend als vorhanden ausgegeben.

## Lokale Fragevorschläge

Die Regeln übernehmen nur ausdrücklich markierte Frage-Antwort-Paare und eindeutig formulierte Definitionen. Frage-Antwort-Paare erzeugen Karteikarten. Als Klausur oder Fallszenario erkennbare Quellen können zusätzlich die passende offene Übungsform anbieten. Definitionen erzeugen Lückentexte; mehrere eindeutige Begriffsdefinitionen können eine Zuordnung ergeben.

Alle Vorschläge enthalten Originaltext, relativen Quellpfad, Seiten- oder Abschnittsnummer, Lösung, Erklärung und Prüfstatus. Sie bleiben unbestätigt, bis der Nutzer die Importvorschau bestätigt. Die Regeln erfinden keine falschen Auswahlantworten und zerlegen gewöhnlichen Fließtext nicht in vermeintlich geprüfte Originalfragen. Die initiale GPT-Work-Aufbereitung von Digitale Diversität wird separat über das dokumentierte JSON-Importformat bereitgestellt.

## Prüfung

Die automatischen Tests prüfen alle sechs Formate mit temporären Dateien, Zuordnungen bei Unicode-Dateinamen, Hashänderungen, unveränderte Quelldateien, fehlerhafte und verschlüsselte PDFs, binäre Textdateien, externe Verknüpfungen, zyklische Ordnerverknüpfungen sowie die Quellenangaben und konservative Fragegenerierung.

## Entfernen

`DELETE /api/documents/{id}` nimmt eine Datei aus dem Index und verschiebt sie aus dem Studienordner (oder aus `imports/` bei Fragenimporten) nach `<Datenordner>/papierkorb/<Zeitstempel>/<Pfad>`. Nichts wird endgültig gelöscht. Antwort: `path`, `moved_to`, `file_was_missing`, `questions_kept` (Fragen mit dieser Datei als Quelle bleiben). In der Oberfläche: „Datei entfernen“ im Öffnen-Fenster unter „Dokumente“ und „Entfernen“ je Datei in Schritt 3 von „Aufbereiten“, jeweils mit Rückfrage.
