# Fragen üben und Fehler gezielt wiederholen

Stand: 16. Oktober 2026.

[Fragen üben](http://localhost:8000/#practice?module=M-10001) bietet eine Übungsrunde ohne Zeitlimit. Nach „Antwort prüfen“ werden die Korrektur, alle Auswahlmöglichkeiten, die eigene Auswahl, individuelle Antworterklärungen und Nachlesestellen angezeigt. Am Ende folgt eine gespeicherte Schlussauswertung aller Fragen. Ungeprüfte Fragen sind darin ausdrücklich als unbeantwortet gekennzeichnet. Für sie werden keine neuen Fehlversuche oder Wiederholungsstrafen erzeugt.

Die vorhandene Klausursimulation bleibt mit Zeitlimit und Lösungen nach der Abgabe verfügbar. Auf ihrer Einstiegsseite führt „Mit direkter Rückmeldung üben“ zum neuen Lernmodus. Auch frühere Klausurauswertungen zeigen die vollständigen Antwortmöglichkeiten, den Fallkontext und vorhandene Aufgabenabbildungen. Ergänzte Erläuterungen erscheinen unter denselben Fragen-IDs auch in älteren Auswertungen.

## Fehlerfragen

Im Reiter [Fehlerfragen](http://localhost:8000/#practice?module=M-10001&tab=mistakes) stehen Fragen, deren jüngster bewerteter Versuch falsch oder teilweise richtig war. Offene Antworten mit noch ausstehender fachlicher Selbstbewertung werden gesondert als „Selbstbewertung offen“ aufgeführt, auch wenn ein Schlagworthinweis bereits alle Begriffe erkannt hat. Die Liste berücksichtigt Versuche aus Lerntraining, Klausursimulation und neuen Übungsrunden.

Eine später vollständig richtige, automatisch oder fachlich selbst bewertete Antwort entfernt die Frage aus diesem Fehlerpool. Ein neuer Fehler nimmt sie wieder auf. Fällige Wiederholungen bleiben unabhängig davon über den bisherigen Bereich „Wiederholungen“ verfügbar. Karteikarten werden dort weitergeführt; der neue Übungsmodus verwendet Auswahl-, Zuordnungs-, Lücken- und offene Fragen.

## Erklärungen und Nachlesen

Alle 143 Auswahlfragen besitzen individuelle Erklärungen zu ihren insgesamt 603 Optionen. Bei einer Frage nach einer falschen Aussage bedeutet „Richtige Antwort“ die gesuchte Auswahl; es ist kein Wahrheitsurteil über die falsche Behauptung. Die Erläuterung benennt den richtigen Sachverhalt.


## Speicherung und technische Prüfung

Geprüfte Antworten, Fragenpositionen und Runden liegen dauerhaft in der lokalen Datenbank. Ungeprüfte Antwortentwürfe werden zusätzlich im Browser zwischengespeichert. Eine identisch erneut übermittelte Antwort erzeugt keinen weiteren Lernversuch. Nach der Prüfung ist sie in dieser Runde gesperrt; eine neue Runde erlaubt einen neuen Versuch. Selbstbewertungen wirken sich auch nach Rundenabschluss auf die gespeicherte Auswertung aus.

Die Runden werden als eigene Einträge in der vorhandenen Metadatentabelle gespeichert und sind in SQLite-Sicherungen und JSON-Exporten enthalten. Vorhandene Lernstände und Klausurantworten werden beim Einspielen der zusätzlichen Erklärungen nicht geändert. Tests und Browserprobeläufe verwenden separate Datenbanken.

Der Produktionsbuild und alle **190 Tests** bestehen. 19 neue Regressionstests sichern unter anderem Fehlerpool und Modulfilter, doppelte Übermittlung, atomare Speicherung, Neustart, offene Selbstbewertungen, Abschluss mit unbeantworteten Fragen, Export und unveränderte Lesezugriffe. Neue Lösungserklärungen und Lernvertiefungen bleiben in aktiven Klausuren serverseitig verborgen. Vier zusätzliche Tests prüfen die vollständige Modell-Lernseite, Originalstellen und Suchvarianten. Die Standardsuche nach Tests ist auf `tests/` begrenzt, damit Sicherungskopien nicht als aktuelle Tests ausgeführt werden.

Im Browser wurden eine falsche Antwort zum Vier-Ebenen-Modell, die individuelle Erklärung aller vier Optionen, die Gesamttabelle, Fortsetzen nach Neuladen, der Abschluss mit zwei unbeantworteten Aufgaben und der Suchsprung zum konkreten Lernabschnitt geprüft.
