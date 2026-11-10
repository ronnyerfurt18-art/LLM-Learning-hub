# Architektur

> Aktualisierung 06.11.2026: Der gemeinsame Starter und lokale Ollama-Tutor sind umgesetzt. Aktuelle Bedienung und Zustände: [Lokaler Tutor](lokaler-tutor-start.md). Die Angaben zur deaktivierten Modellverbindung im folgenden früheren Entwurfsstand sind dadurch überholt.

Browser → React/TypeScript → gleichursprüngliche JSON-API → FastAPI → SQLite. Im Standardbetrieb gibt es keine Drittanbieteraufrufe zur Laufzeit. CSS und SVG-Diagramme werden lokal ausgeliefert. Die bevorzugten Alternativen SM‑2 und hashbasierte regelmäßige Dateiprüfung kommen ohne Modell- oder Watcher-Abhängigkeit aus. PDF-Texte werden mit pypdf gelesen, optional kann ein vorhandenes PyMuPDF verwendet werden.

`backend/core.py` verwaltet Module, Originale, Fragen, Lernversuche, Fortschritt, Klausuren und Abdeckung. `backend/documents.py` liest Quellen und liefert Vorschläge; es schreibt nie in Quelldateien. `backend/main.py` verbindet API, Dateiprüfung, Importbestätigung, Sicherung und statische Oberfläche. `backend/ai.py` bleibt die deaktivierte Erweiterungsgrenze für Fragenimport und Bewertung. Der getrennte Text-Lernbegleiter in `backend/tutor.py` besitzt vorbereitete OpenAI-/Ollama-Anschlüsse und ist standardmäßig nicht eingerichtet. `backend/tutor_context.py` stellt begrenzte, quellenbelegte Lernkontexte zusammen. Das Öffnen oder Exportieren eines Lernauftrags löst keine Modellanfrage aus. Erst eine ausdrücklich gesendete Nachricht bei eingerichteter Konfiguration kann einen Modellaufruf ausführen; dieser schreibt keine Lernversuche oder Bewertungen. Details: [Lernchat](lernchat.md).

SQLite speichert strukturiert abfragbare Schlüssel und flexible JSON-Nutzdaten. Versionierte Migrationen stehen in `migrations`; Version 1 erstellt alle Tabellen idempotent. Fremdschlüssel und Transaktionen sichern Beziehungen. WAL erlaubt Lesen während Schreibvorgängen. API-Schreibzugriffe auf Versuche und Klausuren werden pro Prozess serialisiert; die Anwendung wird mit einem Serverprozess gestartet.

Quellen und importierte Originaltexte bleiben unverändert. Import-IDs sind global eindeutig; wiederholte Importe überspringen vorhandene IDs und überschreiben keine Originale oder Fortschritte. Änderungen können bewusst mit neuen IDs importiert werden. Neue/verschobene/gelöschte Quelldateien ändern den Dokumentenindex, nicht schon gelernte Fragen.

Das reguläre Training wertet Auswahl, Zuordnung und Lücken automatisch aus. Freitext wird ausschließlich auf hinterlegte Worttreffer geprüft und kann selbst bewertet werden. Jede Bewertung erzeugt einen persistenten Versuch. Korrekturen wiederholen die SM‑2-Berechnung über die gespeicherte Reihenfolge, damit spätere Wiederholungen erhalten bleiben.

Klausuren speichern ID-Reihenfolge, Beginn, unveränderliche Frist, Antworten und aktuelle Position. Aktive Klausurantworten enthalten keine Musterlösungen oder Bewertungsbegriffe. Zuordnungsaufgaben liefern getrennte Begriffe und gemischte Definitionen. Der Server prüft die Frist unabhängig vom Browser. Automatische und selbst bewertete Ergebnisse werden getrennt gekennzeichnet.

Der Import ist eine Vertrauensgrenze für Inhaltsqualität: Schema-/Typprüfung ersetzt keine fachliche Prüfung. `verified=false` kennzeichnet ungeprüfte Fragen. Importvorschau und Quellenanzeige erlauben Kontrolle. Inhaltliche Abdeckung aus dem Arbeitsauftrag ist getrennt von Schlagwortsuche und menschlicher Bestätigung gespeichert.

Die Oberfläche ist ein lokaler Build, keine veröffentlichte Site. Der Backendserver ist ausschließlich unter Loopback erreichbar. Host-/Originprüfung schützt Schreibzugriffe über fremde Webseiten. Originalquellen-Downloads werden auf das gewählte Studienverzeichnis begrenzt. Keine Zugangsdaten oder API-Schlüssel sind nötig.
