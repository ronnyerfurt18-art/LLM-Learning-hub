# Architekturlog – Master Learning Hub

Dieses Log hält fest, **wie der Hub aufgebaut ist und warum**. Einzelne Änderungen mit Sicherung und Rückweg stehen weiterhin im `Aenderungslog.md`; hierher gehören Aufbau, Grundsätze und Entscheidungen, die länger gelten. Neue Einträge kommen unten unter „Entscheidungen“ dazu; die Übersicht oben wird bei Bedarf fortgeschrieben.

Stand der Übersicht: 10.11.2026.

## 1. Zwei Stränge: fester Hub und lokales Modell

Der Hub arbeitet mit zwei Strängen, die sich gegenseitig einrahmen.

- **Strang A – fester Hub (Algorithmen):** Regeln, Datenbank und geprüfte Inhaltsdateien. Gleiche Eingabe ergibt immer gleiche Ausgabe. Nur dieser Strang liest Dateien, wählt Kontext aus, speichert Zustände und entscheidet über Abläufe.
- **Strang B – lokales Modell (LLM):** Formuliert, erklärt, plant und entwirft. Seine Ausgabe ist immer ein Vorschlag oder ein Gesprächsbeitrag, nie ein gespeicherter Zustand.

### Wer macht was

| Funktion | Strang A – fester Hub | Strang B – lokales Modell |
|---|---|---|
| Quellen erfassen | Studienordner durchsuchen, Dateiart und Kurseinheit erkennen, Seitentexte auslesen (`documents.py`) | – |
| Üben und Wiederholen | Fragenbank, Auswertung von Auswahl, Zuordnung und Lücken, Wiederholungsplanung nach SM‑2, Klausurmodus (`core.py`, `practice.py`) | – |
| Lernseiten | Laden und vollständige Prüfung der Inhaltsdateien samt Quellen und Seitengrenzen (`learning_pages.py`) | Entwurf neuer Lernseiten im Modul-Import |
| Einsendearbeiten üben | Aufgaben, hergeleitete Lösungen, Punktestaffel (`assignments.py`, Browser) | – |
| Inhaltssuche | Wortsuche über Lernseiten und Seitentexte (`search.py`) | – |
| Lernchat | Kontext auswählen und begrenzen, Belege nummerieren, passende PDF-Stellen ausschneiden (`tutor_context.py`); bei Einsendearbeiten Frage wählen und Stand merken (`tutor_assignments.py`) | Erklären, nachfragen, Lösungsversuche einordnen (`tutor.py`) |
| KI-Planer | Vier Schnellfragen ohne Modell; Termine, Lernstand und Einsendearbeiten als Fakten zusammenstellen (`planner.py`, `planning.py`) | Freie Fragen beantworten, datierte Lernstrecke formulieren |
| Lernprotokoll | Lernziele, Selbsteinschätzung, Wiederholungstermine (`learning_memory.py`) | – |
| Lernwiki | Speichern, Versionieren, Status „ungeprüft/geprüft“ (`lernwiki.py`) | Musterlösung auf ausdrücklichen Wunsch erzeugen |
| Modul-Import | Quellen wählen, in Abschnitte teilen, Zitate in den Seiten wiederfinden, Formate prüfen, Zwischenspeicher (`module_import.py`) | Lernseiten und Übungsfragen je Abschnitt entwerfen |
| Qualitätsprüfung | Feste Regeln nach jeder Antwort, Protokoll der Befunde (`quality.py`) | Zweiter Blick auf eine Antwort auf Knopfdruck |
| Sprache | Aufnahme begrenzen, Dateien nur vorübergehend halten (`voice.py`) | Eigene lokale Sprachmodelle für Erkennen und Vorlesen (nicht das Tutor-Modell) |

### Wie die Stränge ineinandergreifen

Jeder Modellaufruf läuft durch dieselben vier Übergänge. A steht für den festen Hub, B für das Modell.

| Schritt | Richtung | Was passiert | Beispiel |
|---|---|---|---|
| 1. Erkennen | A | Der Hub liest Auswahl und Nachricht und entscheidet, welche Daten gebraucht werden. | „Einsendearbeit 1, Aufgabe 3“ → Frage 3 |
| 2. Einrahmen | A → B | Der Hub stellt Kontext, Regeln und Längenlimit zusammen. Das Modell sieht nur diesen Ausschnitt. | Aussagen, Einordnung, Belegstellen, 9.000 Zeichen |
| 3. Erzeugen | B | Das Modell schreibt Antwort, Plan oder Entwurf. | Erklärung zu Frage 3 |
| 4. Prüfen und Verbuchen | B → A | Der Hub vergleicht die Ausgabe mit seinem Wissen, hängt Befunde an und speichert nur eigene, feste Angaben. | Wortlaut vollständig? Einordnung stimmig? „Frage 3 geöffnet“ |

Auf Wunsch folgt ein fünfter Schritt: Das Modell prüft die eigene Antwort noch einmal gegen denselben Kontext (Knopf „Antwort prüfen“), der Hub bereitet daraus eine Korrekturnachricht vor, und die läuft wieder durch die Schritte 1 bis 4.

```
Nachricht ──► [A] erkennen ──► [A] Kontext + Regeln ──► [B] Antwort
                                                           │
   Anzeige ◄── [A] Befund anhängen ◄── [A] feste Prüfung ◄─┘
      │
      └─ „Antwort prüfen“ ──► [B] Modellprüfung ──► [A] Korrektur vorbereiten ──► neue Nachricht
```

### Wo welcher Übergang liegt

| Übergang | Lernchat | KI-Planer | Modul-Import |
|---|---|---|---|
| Einrahmen | `build_tutor_context`, `build_assignment_context` | Fakten aus `_snapshot`, `_assignment_facts` | `window_messages` mit Seitenausschnitt und JSON-Schema |
| Prüfen | `check_tutor`, Quellenmarker in `_finish` | `check_plan` | `locate_quote`, `validate_import`, `validate_learning_page` |
| Verbuchen | geöffnete Fragen (`tutor:assignments`), Befunde (`quality:log`) | Befunde (`quality:log`) | Importdatei in `imports/`, Entwurf in `imports/entwuerfe/` |
| Freigabe durch dich | Selbsteinschätzung im Lernprotokoll | Termine selbst eintragen | Import bestätigen, Entwurf veröffentlichen |

## 2. Grundsätze

1. **Das Modell schreibt keinen Zustand.** Lernstand, Termine, Fragenbank und Lernseiten ändert nur der Hub, und nur aus festen Angaben oder nach deiner Bestätigung.
2. **Das Modell sieht nur, was der Hub auswählt.** Es liest keine Dateien und hat keine Werkzeuge. Fehlt etwas im Kontext, kann es das nicht wissen; deshalb muss der Hub die richtige Auswahl treffen.
3. **Seitenzahlen und Belege kommen vom Hub.** Das Modell nennt Quellen-IDs oder Zitate; die Zuordnung zur PDF-Seite macht der Hub.
4. **Erzeugtes ist zunächst Entwurf.** Fragen tragen `verified: false`, Lernseiten liegen als Entwurf vor, Musterlösungen sind „ungeprüft“, bis du sie freigibst.
5. **Alles bleibt lokal.** Server nur auf `127.0.0.1`, Modell über Ollama oder Bonsai auf demselben Rechner, keine Weiterleitungen, keine Proxys.
6. **Ein Modellaufruf zur Zeit.** Lernchat, Planer, Lernwiki, Modellprüfung und Modul-Import teilen sich eine Sperre; wer wartet, bekommt eine klare Meldung.
7. **Unvertraute Texte sind Daten.** Lehrbriefinhalte, Nutzernachrichten und geprüfte Antworten werden dem Modell ausdrücklich als Daten übergeben, nicht als Anweisungen.
8. **Ein Befund ist ein Hinweis, kein Urteil.** Die Qualitätsprüfung sagt „bitte gegenlesen“ und ändert selbst nichts.

## 3. Aufbau in Schichten

```
Browser (React, gebaut nach frontend/dist)
   │  JSON über http://localhost:8000/api
FastAPI-Server (backend/main.py) ── Sperren, Zugriff nur lokal
   ├─ feste Dienste: core, documents, learning_pages, assignments, planning,
   │                 search, practice, learning_memory, quality
   ├─ Modellgrenze:  tutor (ein Dienst für alle Modellaufrufe), local_model, bonsai
   └─ Mischformen:   planner, tutor_context, tutor_assignments, lernwiki, module_import
SQLite (data/learning.sqlite3)     Inhaltsdateien (content/, imports/)     Studienordner (nur lesend)
```

| Ablage | Inhalt | Wer schreibt |
|---|---|---|
| `data/learning.sqlite3` | Module, Fragen, Lernversuche, Dokumentenindex, Termine, Lernprotokoll, Lernwiki, Einstellungen (`metadata`) | nur der Hub |
| `content/` | geprüfte Lernseiten, Einsendearbeiten, Lernziele | du bzw. beauftragte Aufbereitung; der Modul-Import nur beim ausdrücklichen Veröffentlichen |
| `imports/` | Frageimporte (warten auf Bestätigung), `entwuerfe/` für Lernseiten | Aufbereitung und Modul-Import |
| `data/module-import/` | Zwischenspeicher fertiger Modellantworten | Modul-Import |
| Studienordner | Originalunterlagen | niemand im Hub; nur Lesezugriff |

## 4. Entscheidungen

### 10.11.2026 – Einsendearbeiten als eigener Kontext in Planer und Lernchat
**Anlass:** Planer und Lernchat antworteten, es seien keine Aufgaben hinterlegt, obwohl sie im Hub lagen. Beide bauen ihren Kontext getrennt auf und kannten `content/assignments/` nicht.
**Entscheidung:** Der Hub erkennt den Bezug zur Einsendearbeit selbst und tauscht den Kontext aus. Der Planer bekommt Fragen und Nachlesestellen ohne Lösungen, der Lernchat die aktuelle Frage mit hergeleiteter Einordnung.
**Folge:** Der Fragenwechsel („nächste Aufgabe“) und der Stand liegen beim Hub. Der Lernchat schreibt damit erstmals selbst etwas, aber nur „Frage geöffnet“, keine Bewertung.

### 10.11.2026 – Modul-Import: das Modell entwirft, der Hub belegt
**Anlass:** Neue Module sollen ohne fremde Hilfe aufbereitet werden können.
**Entscheidung:** Das Modell erzeugt je Seitenausschnitt Lernseite und Fragen und muss ein wörtliches Zitat mitliefern. Der Hub sucht das Zitat selbst in den Seiten; Fragen ohne Treffer werden verworfen. Ergebnisse durchlaufen dieselbe Vorschau und Bestätigung wie fremde Importe.
**Offen:** Qualität mit dem echten Modell ist noch nicht gemessen; Abschnitte folgen dem Seitenumfang statt Kapiteln.

### 10.11.2026 – Qualitätsprüfung zweistufig
**Anlass:** Im ersten Durchlauf fehlte der Wortlaut von Aussagen, und eine erbetene Auflösung wurde verweigert.
**Entscheidung:** Stufe 1 prüft jede Antwort mit festen Regeln ohne Modell und ohne Wartezeit. Stufe 2 lässt das Modell eine Antwort auf Knopfdruck prüfen und bereitet eine Korrektur vor, die du selbst absendest. Der Hub ändert auf Befund hin weder Antworten noch Regeln.
**Begründung:** Ein Modell übersieht einen Teil seiner eigenen Fehler; was sich abzählen lässt, prüft der Hub deshalb selbst. Das Abstellen von Ursachen bleibt eine Entscheidung mit Freigabe (geplante Stufe 3: Regelvorschläge aus dem Protokoll).

### 10.11.2026 – Normale Gespräche schreiben nichts
**Anlass:** Ein bestehender Test sichert zu, dass ein Lernchat-Gespräch die Datenbank nicht verändert; ein Zähler der Qualitätsprüfung hätte das gebrochen.
**Entscheidung:** In die Datenbank kommt nur ein tatsächlicher Befund. Zähler und der Kontext für die Modellprüfung liegen im Arbeitsspeicher und gehen beim Neustart verloren.
**Folge:** Eine Antwort lässt sich nach einem Neustart des Hubs nicht mehr nachträglich prüfen.

### 10.11.2026 – Geänderter Code wirkt erst nach echtem Neustart
**Anlass:** Eine Änderung schien nicht zu wirken, weil `Start.command` bei laufendem Hub nur die vorhandene Seite öffnet.
**Festgehalten:** Backend-Änderungen brauchen Ctrl+C im Startfenster und einen neuen Start. Oberflächenänderungen brauchen zusätzlich einen neuen Bau nach `frontend/dist` und ein Neuladen der Seite.

## 5. Bekannte Lücken

- Der Modul-Import hat noch keine Oberfläche und kein Big Picture.
- Die Qualitätsprüfung deckt normale Lernseiten-Gespräche nur mit zwei Regeln ab; für den Planer gibt es keine Modellprüfung.
