# Lernwiki – nächster Ausbau nach dem lokalen Tutor

Stand: 6. November 2026. Anforderungen aus dem Gespräch; noch keine implementierte Wiki-Funktion.

## Zweck
Geprüfte Erklärungen, Lernaufgaben und Lösungskriterien wiederverwenden, um wiederholte Modellaufrufe zu vermeiden und die fachliche Konsistenz zu verbessern. Es entsteht ein kuratierter Wissensbestand, kein fortlaufender Chatprotokoll-Stapel. Ein Nachtraining der Modellgewichte ist dafür zunächst nicht erforderlich.

## Eintrag
- ID, Version, Modul, Thema und Abschnitt.
- Frage beziehungsweise Lernziel und Art des Eintrags: Erklärung, Beispiel, Aufgabe oder Bewertungskriterien.
- Antwort, Herleitung, Quellen mit Seitenbezug und zugrunde liegende Inhaltsversion.
- Herkunft: Modell, Erstellungsdatum, Kontext- und Promptversion.
- Prüfstatus: Entwurf, zur Prüfung exportiert, mit Quellen bestätigt, korrigiert oder verworfen.
- Prüfer, Prüfmethode, Datum, Begründung und offene Unsicherheiten.
- Nutzungshäufigkeit, letzte Verwendung und Zahl tatsächlich vermiedener Modellaufrufe.
- Dokumentierte Prüfergebnisse und Fehler/Korrekturen; keine erfundene Genauigkeitsprozentzahl aus bloßer Nutzung oder Modellselbsteinschätzung.

## Wiederverwendung
Nur bestätigte, gültige Einträge werden ohne Modellantwort ausgeliefert. Für den Beginn gilt ein eindeutiger Treffer auf Frage, Lernziel und Kurskontext. Ähnliche Fragen liefern Vorschläge; Ähnlichkeit allein gilt nicht als Beweis, dass dieselbe Antwort passt. Gesprächsabhängige Rückfragen werden nicht durch einen kontextlosen Cachetreffer beantwortet.

Ändern sich Quellen, Aufgaben oder Lösungskriterien, wird die Freigabe der betroffenen Version erneut geprüft. Häufigkeit und fachliche Genauigkeit bleiben getrennte Kennzahlen.

## Prüfung über die GPT-App
Ein Markdown-Export enthält Frage, Antwort, fachliche Kriterien, verfügbare Quellenbelege, Eintrags-ID und Version. Ein standardisierter Prüfauftrag bittet um korrekte, teilweise korrekte, unbelegte und falsche Aussagen mit Begründung und Belegen. Der Export überträgt selbst keine Daten an einen Cloud-Dienst.

Das Prüfergebnis wird nachvollziehbar zur exportierten Version zurückgeführt. Korrekturen werden als neue Version gespeichert; eine Prüfung einer älteren Version darf eine zwischenzeitlich veränderte Antwort nicht freigeben. Eine GPT-Antwort ohne belastbare Belege wird nicht automatisch als fachlich bestätigt eingestuft.

## Verbesserung des Lernsystems
Passende bestätigte Einträge können unmittelbar ohne LLM-Aufruf angezeigt werden. Bei neuen Fragen bilden passende geprüfte Einträge die Wissensgrundlage für das lokale Modell. Die Modellgewichte bleiben dabei unverändert. Ein späteres Nachtraining wäre eine eigenständige Entscheidung auf Grundlage eines ausreichend großen geprüften Datensatzes und eines getrennten Evaluationssatzes.

## Umsetzungsstand (07.11.2026, Etappe 2)
- Umgesetzt: Musterlösung je Lernziel aus `content/tutor/goals.json` per Knopf („Musterlösung erstellen“) im Lernprotokoll; Speicherung als Version in `tutor_wiki_entries` (Antwort, Quellen, zitierte Originalauszüge, Modell, Thinking, Kontext-Hash, Dauer); sofortige Wiederverwendung ohne Modellaufruf; „Verbessern“ erzeugt eine neue Version, ältere bleiben abrufbar; Status „KI-Entwurf, ungeprüft“ / „Von dir geprüft“; Hinweis „veraltet“, wenn sich Lernstoff oder Vorgaben seit der Version geändert haben; optional „Gründlich nachdenken“.
- Noch offen: Erzeugung in Pausen und als Stapel je Modul (Etappe 3), seitengenaue Kontextsuche zur Aufgabe und Export zur Prüfung (Etappe 4), Nutzung geprüfter Einträge als Wissensgrundlage für neue Fragen, verwandte Einträge bei ähnlichen Aufgaben.
