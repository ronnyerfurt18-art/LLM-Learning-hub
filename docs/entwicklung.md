# Entwicklung: Anforderungen an den Hub festhalten und weitergeben

Die Seite **Entwicklung** sammelt, was am Hub selbst anders werden soll. Das lokale KI-Modell arbeitet aus einer Anforderung einen Auftrag aus, der Hub stuft ihn ein und schreibt den Prompt für eine externe KI wie Cowork oder Codex. Kleine Aufträge kann das lokale KI-Modell selbst umsetzen; Programmcode ändert der Hub dabei nur, wenn du einen Vorschlag ausdrücklich übernimmst.

## Ablauf

1. **Anforderung speichern.** Text mit 10 bis 4000 Zeichen, Titel optional. Der Wortlaut bleibt danach unverändert; Nachträge kommen in die **Ergänzung**.
2. **Auftrag ausarbeiten.** Das KI-Modell liefert Titel, Ziel, betroffene Dateien, Schritte, Abnahmekriterien, Risiken, offene Fragen und eine Größe (klein, mittel, groß). Ein neuer Lauf ersetzt den bisherigen Auftrag; ein fehlgeschlagener Lauf lässt ihn stehen und zeigt den Grund.
3. **Einstufung.** Der Hub entscheidet nach festen Regeln zwischen **Lokal machbar** und **Extern übergeben** und nennt die Gründe. Du kannst die Einstufung umstellen.
4. **Lokal umsetzen (nur „Lokal machbar“).** Mit **Änderung vorschlagen lassen** liest das KI-Modell die genannten Dateien und schlägt Ersetzungen vor. Du siehst sie als Vorher-Nachher-Vergleich und wählst **Übernehmen** oder **Verwerfen**. Einzelheiten stehen unter „Umsetzung durch das lokale KI-Modell“.
5. **Prompt kopieren.** Der Prompt steht unter jeder Anforderung, auch ohne Auftrag. Danach setzt du den Status auf **Übergeben**, später auf **Umgesetzt** oder **Verworfen**.

Status: Neu, Auftrag liegt vor, Übergeben, Umgesetzt, Verworfen. Den ersten Wechsel zu „Auftrag liegt vor“ setzt der Hub, ebenso „Umgesetzt“ beim Übernehmen eines Vorschlags und „Auftrag liegt vor“ beim Zurücknehmen; alle anderen setzt du. Umgesetzte und verworfene Anforderungen sind in der Liste ausgeblendet, bis du sie einblendest. Gelöscht wird nichts.

## Was das KI-Modell sieht

Für den Auftrag:

- die Anforderung im Wortlaut und die Ergänzung,
- den Dateiindex des Programms: Dateinamen aus `backend/`, `frontend/src/`, `tools/`, `docs/` sowie `launcher.py` und `README.md`, je mit einer Zeile Beschreibung aus der Datei selbst (Docstring, Überschrift oder exportierte Namen),
- die Abschnitte „Grundsätze“ und „Aufbau in Schichten“ aus `logs/Architekturlog.md`, gekürzt auf 3000 Zeichen.

Dabei sieht es keinen Quelltext. Der Index ist auf 6000 Zeichen begrenzt; wird er länger, kürzt der Hub zuerst die Beschreibungen.

Für einen Änderungsvorschlag zusätzlich:

- Ziel, Schritte und Abnahmekriterien des Auftrags,
- den Inhalt der im Auftrag genannten Dateien, höchstens zwei Programmdateien.

In keinem Fall sieht es Inhalte aus `content/`, `imports/`, `data/`, `tutor.local.json` oder dem Studienordner. Der Quelltext geht nur an das lokale KI-Modell auf diesem Mac.

## Was der Hub prüft

- **Dateien:** Übernommen werden nur Dateien aus dem Index. Eine neue Datei wird nur übernommen, wenn das KI-Modell sie als neu kennzeichnet und sie in `backend/`, `frontend/src/`, `tests/`, `tools/` oder `docs/` mit erlaubter Endung liegt. Alles andere steht unter „weggelassen“ und kommt nicht in den Prompt.
- **Tests:** Zu jeder genannten Datei `backend/x.py` ergänzt der Hub `tests/test_x.py`, wenn es sie gibt.
- **Pflichtinhalt:** Ohne Titel, Ziel, mindestens einen Schritt und ein Abnahmekriterium gilt der Lauf als fehlgeschlagen.
- **Einstufung „Lokal machbar“** nur, wenn alles zutrifft: Größe „klein“, höchstens zwei Programmdateien (Tests und Dokumente zählen nicht), nur Server oder nur Oberfläche, keine neue Datei, mindestens eine belegte Datei.

## Umsetzung durch das lokale KI-Modell

Der Abschnitt erscheint unter jedem Auftrag. **Änderung vorschlagen lassen** gibt es nur bei der Einstufung **Lokal machbar**.

1. **Dateien lesen.** Der Hub nimmt die im Auftrag genannten Dateien aus `backend/`, `frontend/src/`, `tools/`, `tests/` und `docs/`. Sind Programmdateien genannt, gehen nur sie an das KI-Modell, höchstens zwei. Neue Dateien, `launcher.py`, `README.md` und alles außerhalb des Dateiindex sind ausgeschlossen.
2. **Vorschlag.** Das KI-Modell antwortet mit Ersetzungen: Datei, bisheriger Text, neuer Text, ein Satz Begründung. Fehlt ihm eine Angabe, stellt es stattdessen eine Rückfrage; die beantwortest du in der Ergänzung und lässt neu vorschlagen.
3. **Prüfung durch den Hub.** Eine Ersetzung ist übernehmbar, wenn ihre Datei zum Auftrag gehört, der bisherige Text dort genau einmal vorkommt, sie sich mit keiner anderen überschneidet und eine Python-Datei danach noch gültiges Python ist. Alles andere steht mit Grund im Vorschlag und wird nie geschrieben. Ändert sich in Oberfläche oder Styles die Zahl der Klammern, zeigt der Hub eine Warnung.
4. **Freigabe.** Bis du **Übernehmen** wählst, ändert sich keine Datei. **Verwerfen** schließt den Vorschlag. Ein neuer Auftrag verwirft einen offenen Vorschlag ebenfalls.
5. **Übernehmen.** Der Hub prüft, dass die Dateien noch so sind wie beim Vorschlag, kopiert sie nach `data/backups/development/<Nummer>-<Zeitstempel>/`, schreibt die Änderung, trägt sie oben in `logs/Aenderungslog.md` ein und setzt den Status auf **Umgesetzt**. Danach steht dort, was noch nötig ist: bei `frontend/` in diesem Ordner `npm run build` und die Seite neu laden, bei `backend/` den Hub neu starten.
6. **Zurücknehmen.** Stellt die Dateien aus der Sicherung bytegenau wieder her und setzt den Status auf **Auftrag liegt vor**. Wurde eine Datei seit dem Übernehmen weiter geändert, nimmt der Hub nichts zurück und nennt den Sicherungsordner. Solange eine Änderung übernommen ist, gibt es für diese Anforderung keinen neuen Vorschlag.

**Große Dateien.** Passen die Dateien nicht in das Kontextfenster (`context_tokens` in `tutor.local.json`, gerechnet mit 2,2 Zeichen je Token), bekommt die erste genannte Datei Vorrang. Von einer Datei, die nicht mehr passt, zeigt der Hub nur Ausschnitte von je rund 1400 Zeichen um Stellen, an denen ein Wort aus Ergänzung, Anforderung oder Auftrag höchstens achtmal vorkommt. Findet er keine solche Stelle, bricht er mit einem Hinweis ab: Nenne dann in der Ergänzung einen Begriff aus der Datei, zum Beispiel einen Klassennamen. Bei 32 768 Token passen `frontend/src/styles.css` und `frontend/src/App.tsx` zusammen noch ganz hinein.

## Der Prompt

Der Hub baut den Prompt ohne KI-Modell aus festen Teilen: Projektbeschreibung und Projektordner, Anforderung im Wortlaut, Ergänzung, Auftrag, Regeln des Projekts, Prüfschritte und Abschlussbericht. Gibt es noch keinen Auftrag, verlangt der Prompt zuerst einen Plan zur Zustimmung.

Die Regeln stehen in [`entwicklungsregeln.md`](entwicklungsregeln.md) und gehen ab der zweiten Zeile unverändert in jeden Prompt, höchstens 4000 Zeichen. Fehlt die Datei oder ist sie leer, verwendet der Hub fünf eingebaute Standardregeln.

Der Prompt enthält den Pfad des Projektordners und damit in der Regel den Benutzernamen des Macs. Er verlässt den Hub erst, wenn du ihn kopierst und woanders einfügst.

## Der Entwicklungs-Chat

Auf jeder Seite gibt es unten rechts den Knopf „Entwicklung“. Er öffnet ein Chat-Fenster, in dem du eine Aufgabe in Worten aufgibst (kein Code nötig). Der Hub führt sie so weit, wie er allein kommt:

1. **Auftrag und Einstufung:** Das KI-Modell arbeitet den Auftrag aus, der Hub stuft ihn ein. Was sich nicht lokal lösen lässt, endet beim Prompt für eine externe KI („Prompt kopieren“).
2. **Vorschlag:** Bei lokal machbaren Aufträgen schlägt das KI-Modell die Änderung vor. Du siehst Datei, Begründung, bisherigen und neuen Text. Fragt das Modell nach, antwortest du im Chat.
3. **Freigabe:** „Übernehmen und prüfen“ schreibt die Änderung (mit Sicherung) und startet sofort die Prüfung. „Verwerfen“ lässt alles, wie es ist.
4. **Prüfung durch den Hub:** Er führt nur feste Befehle aus, nie etwas, das das KI-Modell geschrieben hat: bei Änderungen an `frontend/` den Befehl „npm run build“, bei Änderungen an Python-Dateien die Tests des Auftrags. Das Ergebnis steht im Verlauf der Anforderung.
5. **Urteil:** Am Ende steht „✓ Erledigt“ oder „✗ Noch nicht erledigt“ mit den Gründen. Nicht erledigt heißt zum Beispiel: der Bau ist fehlgeschlagen (Fehlertext steht dabei, „Zurücknehmen“ ist möglich), oder der Hub muss mit „Start.command“ neu gestartet werden, weil sich Servercode geändert hat. Das kann der Hub nicht selbst.

Wo der Chat gerade steht, merkt sich der Browser; „Alle Anforderungen“ führt zur Liste mit allen Aufgaben und ihrem Verlauf.

## Stand und Verlauf: woran du siehst, ob etwas wirkt

„Umgesetzt“ als Status sagt nur, dass etwas in den Dateien steht oder dass du es so markiert hast. Ob du es im Hub **siehst**, zeigt der Block „Stand“ über jeder Anforderung und die Zeile unter jedem Eintrag der Liste.

- **Stand-Zeile:** zum Beispiel „Übernommen, wirkt aber noch nicht“, „Übernommen und wirksam“, „Vorschlag wartet auf deine Freigabe“, „Zurückgenommen“ oder „Verworfen“.
- **Prüfpunkte (✓/✗):** Wurde eine Änderung an der Oberfläche übernommen, prüft der Hub, ob `frontend/dist/index.html` später als die Übernahme gebaut wurde. Wurde Servercode geändert, prüft er, ob der Hub seitdem neu gestartet wurde. „Stand neu prüfen“ liest beides erneut ein. Bei ✗ steht dort, was zu tun ist (zum Beispiel im Ordner „frontend“ den Befehl „npm run build“ ausführen).
- **Liste:** Statt eines Schalters gibt es zwei Gruppen, „Offen“ und „Abgeschlossen“. Beide sind immer sichtbar, offene Prüfpunkte stehen direkt in der Zeile.
- **Verlauf:** Unter jeder Anforderung steht aufklappbar, was wann geschah (angelegt, Auftrag ausgearbeitet, Änderung vorgeschlagen, übernommen, zurückgenommen, verworfen, Status oder Einstufung geändert). Der Verlauf ist angehängt, nie überschrieben, und auf 100 Einträge begrenzt. Ältere Anforderungen bekommen die Ereignisse, die sich aus ihren Zeitstempeln ergeben.

Wichtig: Eine Anforderung beschreibst du in Worten. Code gehört nicht hinein; den schreibt das KI-Modell als Vorschlag, und du siehst ihn vor der Freigabe.

## Schnittstellen

- `POST /api/development/ask` (Aufgabe aufgeben: Auftrag, Einstufung, Vorschlag in einem Lauf) und `POST /api/development/requests/{id}/verify` (Prüfung nach der Übernahme) gehören zum Chat.

- `GET /api/development`: Liste der Anforderungen (neueste zuerst), Stand des laufenden Auftrags, `model_available`, Herkunft der Regeln.
- `POST /api/development/requests` `{text, title?, note?}`: legt eine Anforderung an (`E-001`, `E-002`, …).
- `GET /api/development/requests/{id}`: Anforderung mit Auftrag und `prompt`.
- `PATCH /api/development/requests/{id}` `{title?, note?, status?, route?}`: `status` ist `new`, `drafted`, `handed_over`, `done` oder `dropped`; `route` ist `local` oder `external` und setzt einen Auftrag voraus.
- `POST /api/development/requests/{id}/order`: startet die Ausarbeitung im Hintergrund (202). 409, wenn schon eine läuft; 503, wenn der Lernchat nicht mit einem Ollama-Modell eingerichtet ist.
- `POST /api/development/requests/{id}/proposal`: startet den Änderungsvorschlag im Hintergrund (202). 400, wenn kein lokal machbarer Auftrag mit änderbaren Dateien vorliegt; 409, wenn das KI-Modell schon für die Entwicklung arbeitet oder eine Änderung übernommen ist; 503 wie oben. Der Stand steht in `job` (`kind` ist `order` oder `proposal`), das Ergebnis in `proposal` der Anforderung, ein Fehlschlag in `change_error`.
- `POST /api/development/requests/{id}/proposal/apply`, `/discard`, `/revert`: übernehmen, verwerfen, zurücknehmen. Antwort ist die Anforderung; 409, wenn der Vorschlag nicht im passenden Zustand ist oder eine Datei sich inzwischen geändert hat.

`proposal` hat den Zustand `open`, `applied`, `reverted` oder `discarded` und enthält je Ersetzung `path`, `search`, `replace`, `reason`, `ok`, `problem` sowie `lead` und `tail` (Text davor und danach für die Anzeige).

Die Anforderungen liegen samt Vorschlag in der Datenbank (`metadata`, Schlüssel `development:requests`) und damit in der Sicherung des Hubs. Der Baustein heißt in der Abschaltliste `development`.

## Grenzen

- Ausarbeitung und Änderungsvorschlag laufen nur mit Ollama, nicht mit Bonsai. Sie teilen sich das KI-Modell mit Lernchat, Aufbereitung und Big Picture und warten, bis es frei ist. Es läuft immer nur eines von beiden.
- Nach dem Übernehmen laufen weder Tests noch der Bau der Oberfläche aus dem Hub heraus. Der Hub prüft, dass eine Ersetzung genau eine Stelle trifft, nicht, ob sie fachlich richtig ist.
- Das lokale KI-Modell legt keine neuen Dateien an, löscht nichts und ändert höchstens zwei Programmdateien je Auftrag. Trifft es den bisherigen Text nicht zeichengenau, ist die Ersetzung nicht übernehmbar; eine zweite Runde mit den Ablehnungsgründen gibt es nicht.
- Die Sicherungen unter `data/backups/development/` räumt der Hub nicht auf.
- Das KI-Modell rät die betroffenen Dateien aus Namen und Kurzbeschreibungen. Der Prompt weist die externe KI deshalb an, die Liste am Quelltext zu prüfen.
- Spracheingabe gibt es auf dieser Seite nicht.
- Geprüft ist der Ablauf mit einem Platzhalter statt eines echten KI-Modells. Wie brauchbar die Aufträge und Änderungsvorschläge eines echten KI-Modells sind, ist nicht gemessen.
