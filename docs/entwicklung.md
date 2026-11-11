# Entwicklung: Anforderungen an den Hub festhalten und weitergeben

Die Seite **Entwicklung** sammelt, was am Hub selbst anders werden soll. Das lokale KI-Modell arbeitet aus einer Anforderung einen Auftrag aus, der Hub stuft ihn ein und schreibt den Prompt für eine externe KI wie Cowork oder Codex. Der Baustein ändert keinen Programmcode.

## Ablauf

1. **Anforderung speichern.** Text mit 10 bis 4000 Zeichen, Titel optional. Der Wortlaut bleibt danach unverändert; Nachträge kommen in die **Ergänzung**.
2. **Auftrag ausarbeiten.** Das KI-Modell liefert Titel, Ziel, betroffene Dateien, Schritte, Abnahmekriterien, Risiken, offene Fragen und eine Größe (klein, mittel, groß). Ein neuer Lauf ersetzt den bisherigen Auftrag; ein fehlgeschlagener Lauf lässt ihn stehen und zeigt den Grund.
3. **Einstufung.** Der Hub entscheidet nach festen Regeln zwischen **Lokal machbar** und **Extern übergeben** und nennt die Gründe. Du kannst die Einstufung umstellen.
4. **Prompt kopieren.** Der Prompt steht unter jeder Anforderung, auch ohne Auftrag. Danach setzt du den Status auf **Übergeben**, später auf **Umgesetzt** oder **Verworfen**.

Status: Neu, Auftrag liegt vor, Übergeben, Umgesetzt, Verworfen. Den ersten Wechsel zu „Auftrag liegt vor“ setzt der Hub, alle anderen du. Umgesetzte und verworfene Anforderungen sind in der Liste ausgeblendet, bis du sie einblendest. Gelöscht wird nichts.

## Was das KI-Modell sieht

- die Anforderung im Wortlaut und die Ergänzung,
- den Dateiindex des Programms: Dateinamen aus `backend/`, `frontend/src/`, `tools/`, `docs/` sowie `launcher.py` und `README.md`, je mit einer Zeile Beschreibung aus der Datei selbst (Docstring, Überschrift oder exportierte Namen),
- die Abschnitte „Grundsätze“ und „Aufbau in Schichten“ aus `logs/Architekturlog.md`, gekürzt auf 3000 Zeichen.

Es sieht keinen Quelltext und keine Inhalte aus `content/`, `imports/`, `data/`, `tutor.local.json` oder dem Studienordner. Der Index ist auf 6000 Zeichen begrenzt; wird er länger, kürzt der Hub zuerst die Beschreibungen.

## Was der Hub prüft

- **Dateien:** Übernommen werden nur Dateien aus dem Index. Eine neue Datei wird nur übernommen, wenn das KI-Modell sie als neu kennzeichnet und sie in `backend/`, `frontend/src/`, `tests/`, `tools/` oder `docs/` mit erlaubter Endung liegt. Alles andere steht unter „weggelassen“ und kommt nicht in den Prompt.
- **Tests:** Zu jeder genannten Datei `backend/x.py` ergänzt der Hub `tests/test_x.py`, wenn es sie gibt.
- **Pflichtinhalt:** Ohne Titel, Ziel, mindestens einen Schritt und ein Abnahmekriterium gilt der Lauf als fehlgeschlagen.
- **Einstufung „Lokal machbar“** nur, wenn alles zutrifft: Größe „klein“, höchstens zwei Programmdateien (Tests und Dokumente zählen nicht), nur Server oder nur Oberfläche, keine neue Datei, mindestens eine belegte Datei.

## Der Prompt

Der Hub baut den Prompt ohne KI-Modell aus festen Teilen: Projektbeschreibung und Projektordner, Anforderung im Wortlaut, Ergänzung, Auftrag, Regeln des Projekts, Prüfschritte und Abschlussbericht. Gibt es noch keinen Auftrag, verlangt der Prompt zuerst einen Plan zur Zustimmung.

Die Regeln stehen in [`entwicklungsregeln.md`](entwicklungsregeln.md) und gehen ab der zweiten Zeile unverändert in jeden Prompt, höchstens 4000 Zeichen. Fehlt die Datei oder ist sie leer, verwendet der Hub fünf eingebaute Standardregeln.

Der Prompt enthält den Pfad des Projektordners und damit in der Regel den Benutzernamen des Macs. Er verlässt den Hub erst, wenn du ihn kopierst und woanders einfügst.

## Schnittstellen

- `GET /api/development`: Liste der Anforderungen (neueste zuerst), Stand des laufenden Auftrags, `model_available`, Herkunft der Regeln.
- `POST /api/development/requests` `{text, title?, note?}`: legt eine Anforderung an (`E-001`, `E-002`, …).
- `GET /api/development/requests/{id}`: Anforderung mit Auftrag und `prompt`.
- `PATCH /api/development/requests/{id}` `{title?, note?, status?, route?}`: `status` ist `new`, `drafted`, `handed_over`, `done` oder `dropped`; `route` ist `local` oder `external` und setzt einen Auftrag voraus.
- `POST /api/development/requests/{id}/order`: startet die Ausarbeitung im Hintergrund (202). 409, wenn schon eine läuft; 503, wenn der Lernchat nicht mit einem Ollama-Modell eingerichtet ist.

Die Anforderungen liegen in der Datenbank (`metadata`, Schlüssel `development:requests`) und damit in der Sicherung des Hubs. Der Baustein heißt in der Abschaltliste `development`.

## Grenzen

- Die Ausarbeitung läuft nur mit Ollama, nicht mit Bonsai. Sie teilt sich das KI-Modell mit Lernchat, Aufbereitung und Big Picture und wartet, bis es frei ist.
- „Lokal machbar“ ist bisher nur eine Einstufung. Die Umsetzung durch das lokale KI-Modell auf einem Git-Branch ist nicht eingebaut.
- Das KI-Modell rät die betroffenen Dateien aus Namen und Kurzbeschreibungen. Der Prompt weist die externe KI deshalb an, die Liste am Quelltext zu prüfen.
- Spracheingabe gibt es auf dieser Seite nicht.
- Geprüft ist der Ablauf mit einem Platzhalter statt eines echten KI-Modells. Wie brauchbar die Aufträge eines echten KI-Modells sind, ist nicht gemessen.
