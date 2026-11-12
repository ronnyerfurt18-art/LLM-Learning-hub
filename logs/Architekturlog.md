# Architekturlog – Master Learning Hub

Dieses Log hält fest, **wie der Hub aufgebaut ist und warum**. Einzelne Änderungen mit Sicherung und Rückweg stehen weiterhin im `Aenderungslog.md`; hierher gehören Aufbau, Grundsätze und Entscheidungen, die länger gelten. Neue Einträge kommen unten unter „Entscheidungen“ dazu; die Übersicht oben wird bei Bedarf fortgeschrieben.

Stand der Übersicht: 11.11.2026.

## 1. Zwei Stränge: fester Hub und lokales Modell

Der Hub arbeitet mit zwei Strängen, die sich gegenseitig einrahmen.

- **Strang A – fester Hub (Algorithmen):** Regeln, Datenbank und geprüfte Inhaltsdateien. Gleiche Eingabe ergibt immer gleiche Ausgabe. Nur dieser Strang liest Dateien, wählt Kontext aus, speichert Zustände und entscheidet über Abläufe.
- **Strang B – lokales Modell (LLM):** Formuliert, erklärt, plant und entwirft. Seine Ausgabe ist immer ein Vorschlag oder ein Gesprächsbeitrag, nie ein gespeicherter Zustand.

### Wer macht was

| Funktion | Strang A – fester Hub | Strang B – lokales Modell |
|---|---|---|
| Quellen erfassen | Studienordner durchsuchen, Dateiart und Kurseinheit erkennen, Seitentexte auslesen (`documents.py`); Scans ohne Textebene lokal erkennen (`ocr.py`) | – |
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
| Entwicklung | Anforderungen speichern, Dateiindex des Programms bilden, genannte Dateien belegen, Tests ergänzen, Weg einstufen, Übergabe-Prompt schreiben (`development.py`); für lokal machbare Aufträge Dateien auswählen, Ersetzungen prüfen, nach deiner Freigabe sichern und schreiben (`development_change.py`) | Auftrag aus einer Anforderung ausarbeiten: Ziel, Dateien, Schritte, Abnahmekriterien, Risiken, Fragen, Größe; für lokal machbare Aufträge einzelne Ersetzungen vorschlagen |
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

| Übergang | Lernchat | KI-Planer | Modul-Import | Entwicklung |
|---|---|---|---|---|
| Einrahmen | `build_tutor_context`, `build_assignment_context` | Fakten aus `_snapshot`, `_assignment_facts` | `window_messages` mit Seitenausschnitt und JSON-Schema | `messages_for` mit Dateiindex, Architekturauszug und JSON-Schema; `change_messages` mit dem Inhalt der genannten Dateien |
| Prüfen | `check_tutor`, Quellenmarker in `_finish` | `check_plan` | `locate_quote`, `validate_import`, `validate_learning_page` | `build_order`, `decide_route`; `check_edits` |
| Verbuchen | geöffnete Fragen (`tutor:assignments`), Befunde (`quality:log`) | Befunde (`quality:log`) | Importdatei in `imports/`, Entwurf in `imports/entwuerfe/` | Anforderung mit Auftrag und Vorschlag (`development:requests`); nach Freigabe Programmdateien, Sicherung in `data/backups/development/` |
| Freigabe durch dich | Selbsteinschätzung im Lernprotokoll | Termine selbst eintragen | Import bestätigen, Entwurf veröffentlichen | Einstufung umstellen, Prompt selbst kopieren; Vorschlag übernehmen, verwerfen oder zurücknehmen |

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
   └─ Mischformen:   planner, tutor_context, tutor_assignments, lernwiki, module_import,
                     big_picture, development, development_change
SQLite (data/learning.sqlite3)     Inhaltsdateien (content/, imports/)     Studienordner (nur lesend)
```

| Ablage | Inhalt | Wer schreibt |
|---|---|---|
| `data/learning.sqlite3` | Module, Fragen, Lernversuche, Dokumentenindex, Termine, Lernprotokoll, Lernwiki, Entwicklungsanforderungen, Einstellungen (`metadata`) | nur der Hub |
| `content/` | geprüfte Lernseiten, Einsendearbeiten, Lernziele | du bzw. beauftragte Aufbereitung; der Modul-Import nur beim ausdrücklichen Veröffentlichen |
| `imports/` | Frageimporte (warten auf Bestätigung), `entwuerfe/` für Lernseiten | Aufbereitung und Modul-Import |
| `data/module-import/` | Zwischenspeicher fertiger Modellantworten | Modul-Import |
| `data/backups/development/` | Stand der Programmdateien vor einer im Hub übernommenen Änderung | Entwicklung, beim Übernehmen |
| `backend/`, `frontend/src/`, `tools/`, `tests/`, `docs/` | Programm und Anleitungen | du bzw. eine beauftragte KI; der Hub nur beim Übernehmen eines freigegebenen Vorschlags |
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

### 11.11.2026 – Aufbereitung pro Einheit mit zwei Haltepunkten
**Anlass:** Unterlagen treffen über das Semester verteilt ein. Bisher ließ sich ein Modul nur einmal veröffentlichen.
**Entscheidung:** Der Auslöser liegt bei der Einheit. Erster Haltepunkt ist „Aufbereitung starten“ nach der Vorschau, zweiter „Lernseiten veröffentlichen“. Das Veröffentlichen ergänzt nur Einheiten, die noch fehlen; vorhandene Lernseiten und ein vorhandenes Big Picture bleiben unverändert. Vor jeder Änderung an einer Datei in `content/` entsteht eine Sicherung unter `data/backups/`.
**Folge:** Eine bereits veröffentlichte Einheit lässt sich über den Import nicht neu erzeugen. Wer das will, entfernt sie von Hand aus der Datei.

### 11.11.2026 – Der Hub schreibt erstmals in den Studienordner
**Anlass:** Unterlagen sollen sich über die Homepage hochladen lassen.
**Entscheidung:** `POST /api/documents/upload` legt Dateien im Modulordner ab, mit gewählter Einheit im Unterordner `Einheit <n>`. Der Hub überschreibt dort nie etwas, legt nichts außerhalb des Studienordners oder im Programmordner ab und löscht dort nichts (Entfernen verschiebt in den Papierkorb, siehe unten). Alles andere im Studienordner liest er weiterhin nur.
**Offen:** Die Einheit bestimmt weiterhin die Dokumentenerkennung; eine Nummer im Dateinamen hat Vorrang vor dem Ordner. Die Antwort des Uploads nennt deshalb die erkannte und die gewählte Einheit.

### 11.11.2026 – Big Picture als eigener Baustein
**Anlass:** Das Big Picture soll auch für Module entstehen können, deren Lernseiten nicht aus dem Import stammen.
**Entscheidung:** `backend/big_picture.py` kennt weder den Modul-Import noch die Oberfläche. Eingang sind die veröffentlichten Lernseiten eines Moduls, Ausgang ist ein geprüfter Entwurf. Das KI-Modell sieht nur Titel, Zusammenfassung und Lernziele und liefert Bausteine und Beziehungen nach Position; IDs und Quellen setzt der Hub aus den Lernseiten. Das Feld `units` hält fest, welche Einheiten eingeflossen sind, damit der Hub ein veraltetes Big Picture erkennt.
**Offen:** Die Qualität der Zusammenhänge mit einem echten KI-Modell ist nicht gemessen, auch nicht auf 16 GB.

### 11.11.2026 – Bausteine im selben Prozess, abschaltbar
**Anlass:** Die Frage, ob Funktionen als eigene Dienste laufen sollen.
**Entscheidung:** Keine getrennten Dienste. Jeder Baustein ist eine Datei, die ihre Routen selbst anmeldet. `features` in `tutor.local.json` bestimmt, welche Bausteine geladen werden (`voice`, `module_import`, `big_picture`, seit dem Abzweig „Entwicklung“ auch `development`); die Oberfläche blendet die übrigen aus.
**Begründung:** Getrennte Prozesse kosten Startzeit und Arbeitsspeicher, der auf 16 GB knapp ist. Eigene Prozesse bleiben die KI-Modelle (Ollama, Bonsai) und die Sprachverarbeitung.

### 11.11.2026 – Abzweig „Entwicklung“: das Modell entwirft den Auftrag, der Hub schreibt den Prompt
**Anlass:** Änderungen am Hub sollen im Hub vorbereitet werden, lokal oder mit einem Prompt für eine externe KI.
**Entscheidung:** Der Baustein `development` ändert keinen Programmcode. Das KI-Modell sieht die Anforderung, die Dateinamen des Programms mit je einer Zeile Beschreibung und die Grundsätze aus diesem Log, aber keinen Quelltext und keine Lerninhalte. Es schlägt Dateien, Schritte und Kriterien vor. Der Hub übernimmt nur Dateien, die er findet, ergänzt zugehörige Tests, entscheidet nach festen Regeln über den Weg und baut den Übergabe-Prompt aus festen Teilen und `docs/entwicklungsregeln.md`. Der Prompt verlässt den Hub nur über die Zwischenablage.
**Begründung:** Ein lokales KI-Modell mit 27 Milliarden Parametern schärft eine Anforderung brauchbar, ändert Code über mehrere Dateien aber unzuverlässig. Ein fester Prompt bleibt nachvollziehbar und enthält nichts, was der Hub nicht selbst hineingelegt hat.
**Offen:** Umsetzung kleiner Änderungen durch das lokale KI-Modell auf einem Git-Branch mit Freigabe und Testlauf. Sie setzt voraus, dass der Programmordner ein Git-Repository ist und nicht in einem Cloud-Ordner liegt.

### 11.11.2026 – Entwicklung: kleine Aufträge setzt das lokale Modell um, der Hub schreibt nach Freigabe
**Anlass:** „Lokal machbar“ war nur eine Einstufung. Kleine Änderungen wie ein Farbwert sollen im Hub selbst umgesetzt werden können.
**Entscheidung:** `backend/development_change.py` ergänzt den Baustein `development`. Für einen Auftrag mit der Einstufung „lokal machbar“ liest der Hub die genannten Dateien (höchstens zwei Programmdateien, nur aus dem Dateiindex, keine neuen) und gibt ihren Inhalt an das lokale KI-Modell, ganz oder in Ausschnitten, wenn sie nicht ins Kontextfenster passen. Das KI-Modell liefert einzelne Ersetzungen (Datei, bisheriger Text, neuer Text), nie ganze Dateien. Der Hub übernimmt eine Ersetzung nur, wenn die Datei zum Auftrag gehört und der bisherige Text dort genau einmal vorkommt; Python muss danach noch gültig sein. Geschrieben wird erst nach deinem Klick auf „Übernehmen“: Sicherung nach `data/backups/development/`, Schreiben über eine temporäre Datei, Eintrag im Änderungslog, Status „Umgesetzt“. „Zurücknehmen“ stellt die Sicherung bytegenau wieder her, solange die Datei seither nicht weiter geändert wurde.
**Begründung:** Damit ändert sich die Entscheidung vom selben Tag in zwei Punkten: Das KI-Modell sieht jetzt Quelltext, und der Baustein ändert Programmcode. Beides bleibt innerhalb der Grundsätze 1 und 2, weil der Hub die Dateien auswählt und nur nach Bestätigung schreibt. Ersetzungen statt ganzer Dateien, weil `styles.css` und `App.tsx` aus wenigen sehr langen Zeilen bestehen und ein Modell dieser Größe lange Dateien nicht fehlerfrei wiedergibt. Sicherungsordner statt Git-Branch, weil der Programmordner im iCloud-Ordner liegt und kein Git-Repository ist.
**Offen:** Tests und der Bau der Oberfläche laufen nach dem Übernehmen nicht aus dem Hub heraus (Stufe 2). Ob ein echtes KI-Modell den bisherigen Text in langen Zeilen zeichengenau trifft, ist nicht gemessen; eine zweite Runde mit den Ablehnungsgründen gibt es nicht.

### 11.11.2026 – Entwicklung: Stand und Verlauf statt bloßem Status

**Entscheidung:** Der Status einer Anforderung („Umgesetzt“) sagt nichts darüber, ob die Änderung im laufenden Hub ankommt. Deshalb berechnet der Server zusätzlich einen **Stand** (`outcome`) aus dem gespeicherten Zustand und aus zwei Dateizeiten: `frontend/dist/index.html` gegen den Zeitpunkt der Übernahme, und der Start des Hubs gegen denselben Zeitpunkt. Der Stand wird bei jedem Abruf neu berechnet, nicht gespeichert; so kann er nicht veralten.

**Verlauf:** Jede Anforderung führt eine angehängte Liste (`history`, höchstens 100 Einträge). Ältere Anforderungen erhalten beim ersten Anzeigen die Ereignisse, die ihre Zeitstempel hergeben (`legacy_history`).

**Warum so:** Der Hub kann nicht sehen, ob du die Seite neu geladen hast; er kann aber belegen, ob ein Neubau oder Neustart nach der Übernahme stattfand. Das ist die ehrliche Grenze der Prüfung und steht so in der Oberfläche.

**Folgen:** Betroffen sind `backend/development.py`, `backend/development_change.py`, `Development.tsx`, `development.css`, `types.ts`. Neue Tests in `tests/test_development_status.py`.

### 11.11.2026 – Entwicklung als Chat mit Urteil „erledigt / nicht erledigt“

**Entscheidung:** Formular und Listen reichten nicht, weil man nach dem Abschicken nicht sah, wo die Aufgabe steht. Der Bereich bekommt ein Chat-Fenster (`DevChat.tsx`, auf jeder Seite), das denselben Zustand zeigt wie die Seite „Entwicklung“, nur als Gespräch. Eine Aufgabe läuft als **ein** Hintergrundlauf (`kind='flow'`): Auftrag, Einstufung, bei „lokal“ der Vorschlag. Die Freigabe bleibt bei der Person.

**Prüfung:** Nach der Übernahme startet ein weiterer Lauf (`kind='verify'`), der ausschließlich feste Befehle ausführt (Bau der Oberfläche, Tests der betroffenen Python-Dateien). Das Ergebnis liegt am Vorschlag (`proposal.verify`) und fließt in den Stand ein: ein Fehlschlag macht aus „Übernommen“ ein rotes „Prüfung fehlgeschlagen“. Was der Hub nicht selbst tun kann (Neustart nach Servercode-Änderung), bleibt als ✗ stehen; „erledigt“ gibt es erst, wenn kein Punkt offen ist.

**Warum feste Befehle:** Das KI-Modell liefert nur Textersetzungen. Ein vom Modell gewählter Befehl würde den Schutz der Freigabe aushebeln.

**Folgen:** `backend/development_flow.py` neu, `tests/test_development_flow.py` neu; die Seite „Entwicklung“ bleibt für Verlauf und Handarbeit.

### 11.11.2026 – Texterkennung (OCR) als fester Baustein vor dem Modell

**Entscheidung:** PDFs ohne Textebene (Scans, Fotos) liest der feste Hub selbst: `ocr.py` rendert die Seite mit `pypdfium2` und erkennt den Text lokal mit RapidOCR (ONNX-Modelle im Paket, keine Downloads, nichts verlässt den Rechner). Erkannte Seiten tragen die Markierung `ocr`; Dokumente zeigen die Zahl der erkannten Seiten.

**Warum Strang A:** Texterkennung ist deterministisch und gehört zum Erfassen der Quellen, nicht zum Formulieren. Das Modell bekommt den erkannten Text wie jeden anderen Seitentext über denselben Übergang „Einrahmen“; es sieht nie das Bild.

**Folgen:** `requirements.txt` um `rapidocr` und `onnxruntime` erweitert (Python 3.9 bekommt ältere, passende Versionen). Fehlt das Paket, meldet der Index weiterhin einen klaren Fehler statt stillzuschweigen.

### 11.11.2026 – Entfernen verschiebt in den Papierkorb, löscht nie

**Anlass:** Eine falsch oder unlesbar hochgeladene Datei blieb als Leiche in der Dokumentenliste.

**Entscheidung:** `DELETE /api/documents/{id}` (`document_trash.py`) verschiebt die Datei aus dem Studienordner nach `<Datenordner>/papierkorb/<Zeitstempel>/<Pfad>` und entfernt den Indexeintrag. Der Hub löscht damit weiterhin nichts endgültig; der Rückweg ist „Datei zurückschieben, Ordner durchsuchen“. Bereits übernommene Fragen und veröffentlichte Lernseiten bleiben unberührt, ein leer gewordener Ordner `Einheit <n>` aus dem Upload wird mit entfernt.

### 11.11.2026 – „KI fragen“: die Seite meldet, was sie zeigt
**Anlass:** Kurze Rückfragen sollen auf jeder Seite möglich sein, ohne in den Lernchat zu wechseln.
**Entscheidung:** Ein Fenster für alle Seiten (`AskAi.tsx`), keine eigene Logik je Seite. Eine Seite meldet über `pageContext.ts` Titel und Text dessen, was gerade sichtbar ist; ohne Meldung gelten Seitentitel und gewähltes Modul. Der Server (`backend/quick_chat.py`) setzt diese Angaben als Daten vor den kompakten Studienkontext des Moduls und ergänzt feste Regeln für kurze Antworten. Die Trainingsfrage meldet die Musterantwort erst nach dem Aufdecken. Kein eigener Schalter in `features`: das Fenster gehört zum Lernbegleiter und nutzt dessen Modell und Sperre.
**Folge:** Läuft gerade eine Antwort im Lernchat, meldet „KI fragen“, dass der Lernbegleiter beschäftigt ist (und umgekehrt). Das Gespräch im Fenster wird nicht gespeichert und geht beim Neuladen verloren.
**Offen:** Weitere Seiten (Lernseiten-Abschnitt, Klausurtraining) melden noch keinen eigenen Inhalt.

## 5. Bekannte Lücken

- Aufbereitung, Big Picture und die Aufträge im Abzweig „Entwicklung“ sind nur mit einem Platzhalter statt eines echten KI-Modells geprüft.
- Im Abzweig „Entwicklung“ rät das KI-Modell die betroffenen Dateien aus Namen und Kurzbeschreibungen; der Hub prüft nur, ob es sie gibt, nicht ob sie die richtigen sind.
- Die lokale Umsetzung im Abzweig „Entwicklung“ ist nur mit einem Platzhalter statt eines echten KI-Modells geprüft. Der Hub prüft, dass eine Ersetzung genau eine Stelle trifft, nicht, ob sie fachlich richtig ist; bei Oberfläche und Styles gibt es nur eine Warnung zur Klammerzahl.
- Die Übersicht je Einheit liest bei jedem Aufruf die Seitentexte aller Lehrbriefe; bei großen Modulen ist das langsam.
- Hochgeladene Videos (`.mp4`) werden gespeichert, erscheinen aber nicht unter „Dokumente“.
- Die Qualitätsprüfung deckt normale Lernseiten-Gespräche nur mit zwei Regeln ab; für den Planer gibt es keine Modellprüfung.
