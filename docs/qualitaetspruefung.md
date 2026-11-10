# Qualitätsprüfung der KI-Antworten (Stufe 1)

Der Hub prüft jede fertige Antwort von Lernchat und KI-Planer mit festen Regeln gegen das, was er selbst weiß. Dabei wird kein Modell aufgerufen; die Prüfung kostet keine Wartezeit. Ein Befund ist ein Hinweis zum Gegenlesen, kein Urteil.

## Was geprüft wird

| Bereich | Prüfung |
|---|---|
| Lernchat und Planer | Antwort am Längenlimit abgeschnitten (Meldung von Ollama) |
| Lernchat | Tutor behauptet, etwas gespeichert oder notiert zu haben |
| Lernchat, Einsendearbeit | Frage neu geöffnet, aber Aussagen fehlen im Wortlaut (mit Buchstaben) |
| Lernchat, Einsendearbeit | Antwort ordnet eine Aussage anders ein als die hergeleitete Lösung im Hub |
| Lernchat, Einsendearbeit | Auflösung erbeten, aber nicht gegeben |
| Planer, eine Einsendearbeit | Plan nennt nicht alle Fragennummern |

Nicht zuordenbare Quellenmarker und fehlende Quellenverweise meldet der Lernchat schon länger selbst.

## Wo der Befund erscheint

Unter der Antwort als Absatz „Prüfhinweis des Lernhubs (automatisch, nicht vom Modell)“ und zusätzlich unter „Hinweise zur Antwort“. Weil der Absatz Teil des Gesprächsverlaufs ist, liest ihn das Modell bei der nächsten Nachricht mit. Ohne Befund bleibt die Antwort unverändert.

## Protokoll

`GET /api/quality` (im Browser: `http://localhost:8000/api/quality`) zeigt die letzten 200 Befunde mit Zeitpunkt, Modul und Anfang der Nachricht sowie je Bereich die Zahl geprüfter und beanstandeter Antworten seit dem letzten Start des Hubs. In die Hub-Datenbank (`quality:log`) wird nur bei einem Befund geschrieben; eine Antwort ohne Befund verändert nichts, und der Antworttext selbst wird nie gespeichert.

## Grenzen

- Die Einordnungsprüfung erkennt nur eindeutige Formen („C (falsch)“, „Aussage E ist wahr“). Ein Satz wie „Deine Begründung zu E ist falsch“ kann fälschlich als Einordnung zählen.
- „Wortlaut vorhanden“ heißt: mindestens 70 % der Vier-Wort-Folgen der Aussage stehen in der Antwort.
- Fachliche Richtigkeit außerhalb der hinterlegten Einordnungen wird nicht geprüft.
- Normale Lernseiten-Gespräche haben bisher nur die Prüfungen auf Abbruch und Speicherbehauptung.

## Stufe 2: Antwort prüfen lassen (seit 10.11.2026)

Unter jeder Antwort im Lernchat steht bei lokalem Modell **Antwort prüfen**. Das Modell vergleicht dann genau diese Antwort mit den Lerndaten, die ihm beim Antworten vorlagen, und nennt höchstens fünf Befunde mit zitierter Stelle und Quellen-ID oder „Keine Beanstandung“. Die festen Prüfhinweise aus Stufe 1 werden mit angezeigt.

**Korrektur als nächste Nachricht vorbereiten** legt eine fertige Nachricht in das Eingabefeld. Du liest sie und sendest selbst; der Hub verschickt nichts von allein. Diese Nachricht beginnt mit „Prüfhinweis-Korrektur:“ und wechselt bei Einsendearbeiten die Frage nicht, auch wenn die Befunde Fragennummern nennen.

- Die Prüfung dauert etwa so lange wie eine Antwort; der Lernchat wartet solange.
- Geprüft werden kann nur, was seit dem letzten Start des Hubs beantwortet wurde (die letzten 40 Antworten). Der dafür nötige Kontext liegt im Arbeitsspeicher.
- Ein Befund der Modellprüfung wird im Protokoll (`quality:log`, Bereich `review`) festgehalten.
- Prüfer und Tutor sind dasselbe Modell; die Prüfung kann Fehler übersehen oder zu Unrecht beanstanden.
- Route: `POST /api/quality/review` mit `message` und `answer`.

## Nächste Stufe

3. Regelvorschläge aus dem Protokoll, die nach Freigabe in die Tutor-Anweisungen übernommen werden. Außerdem offen: Modellprüfung für den Planer, mehr feste Regeln für normale Lernseiten-Gespräche.
