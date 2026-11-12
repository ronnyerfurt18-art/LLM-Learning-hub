# Lernchat direkt in den Lernpages

> Aktualisierung 06.11.2026: Der gemeinsame Starter, lokale Ollama-Tutor und eigenständige Menüpunkt **Mit KI lernen** sind umgesetzt. Aktuelle Bedienung und Zustände: [Lokaler Tutor](lokaler-tutor-start.md). Die Angaben zum eingebetteten Chat und zur deaktivierten Modellverbindung im folgenden früheren Entwurfsstand sind überholt.

Stand: 15. Oktober 2026. Beauftragter Umfang: **zunächst Oberfläche und Anschluss vorbereiten**. Kein Modell wurde aktiviert und es wurden keine echten Modellanfragen ausgeführt. MCP ist für diesen Lernchat nicht erforderlich.

## Bereits nutzbar

In einer Lernpage oder beim ausgewählten Big-Picture-Baustein führt **Thema besprechen** zum Lernbegleiter. Du kannst den Kontext auswählen, eine Verständnisfrage oder einen Lernauftrag formulieren und passende Vorschläge übernehmen. Zu den ausgewählten Inhalten erscheinen konkrete Quellen mit PDF-Seiten oder Videostellen. Eine aufklappbare Vorschau zeigt die für ein späteres Gespräch vorbereiteten Texte.

**Lernauftrag kopieren** und der Textdatei-Export funktionieren ohne Modell. Damit lässt sich der vorbereitete Auftrag bei Bedarf auch manuell in einer anderen Lernunterhaltung verwenden. Eine Übertragung dorthin erfolgt erst durch dich.

Ohne eingerichteten Modellzugang bleibt das Senden deaktiviert. Es erscheinen weder Demoantworten noch vorgetäuschte KI-Ergebnisse. Sprache und Mikrofonzugriff sind noch nicht eingerichtet.

## Herkunft und Grenzen des Kontexts

Das Backend liest den gewählten Abschnitt, die Lernseite oder den Big-Picture-Baustein aus den vorhandenen lokalen Lernpaketen. Es stellt die zugehörigen Absätze, Lernziele, Tabellen und Quellnachweise zusammen und ergänzt begrenzte Textauszüge von tatsächlich referenzierten PDF-Seiten. Die Homepage lädt hierfür weder die gesamte Dokumentensammlung hoch noch analysiert sie Videos erneut. Videohinweise verlinken die bereits zugeordneten Originalstellen; ein Zeitlink bedeutet keine neue Transkription.

Quellen erhalten Bezeichnungen wie **S1**. Ein späteres Modell kann darauf mit **[S1]** verweisen. Klickbare Originalpfade kommen ausschließlich aus der geprüften lokalen Kontextauswahl, nicht aus frei erzeugten Modelllinks. PDF-Auszüge und Lerntexte werden als Daten behandelt, nicht als Handlungsanweisungen an die Anwendung.

Begrenzungen oder fehlende Originalauszüge werden im Kontext vermerkt. Der Lernchat ist eine Lernhilfe mit Quellen, keine offizielle Musterlösung oder verbindliche Bewertung. Die vorhandene Schlagwortauswertung und Selbstbewertung bleiben davon unabhängig.

## Was lokal bleibt und was später übertragen würde

| Schritt | Ort | Daten |
| --- | --- | --- |
| Thema auswählen und Kontext zusammenstellen | Mac, vorhandenes FastAPI-Backend | Gewählte Lernabschnitte und begrenzte Originalauszüge |
| Quellen öffnen | Lokaler Quellen-Endpunkt | Originaldatei im Studienordner |
| Auftrag vorbereiten, Vorschau lesen, Text exportieren | Browser auf dem Mac | Ausgewählter Kontext und Entwurf |
| Späterer Chat mit lokalem Modell | Ollama auf diesem Mac, nur nach Einrichtung | Lernregeln, ausgewählter Kontext, begrenzter Verlauf und neue Nachricht |
| Späterer Chat mit OpenAI API | OpenAI, nur nach Einrichtung und Senden | Dieselben ausgewählten Texte; keine vollständige Sammlung und keine automatische Übertragung beim Öffnen |

Liegt der Studienordner in einem synchronisierten Cloud-Ordner, werden die Dateien unabhängig vom Lernchat dorthin synchronisiert. Die Homepage selbst bleibt unter Loopback erreichbar und wird nicht öffentlich veröffentlicht.

Ein Gespräch ändert keine Fragen, Lernversuche, Wiederholungen oder Klausurergebnisse. Der vorbereitete Anschluss bietet keine Werkzeuge, die Moodle-Abgaben, Kalender oder Lernstände verändern. Der Gesprächsverlauf wird nicht in der Lern-Datenbank gespeichert.

## Vorbereiteter Anschluss für eine spätere Einrichtung

Der Server besitzt einen standardmäßig deaktivierten Textanschluss. Die Einrichtung erfolgt später ausdrücklich über die Umgebung des gestarteten Servers; es gibt keinen API-Schlüssel im Frontend, Lernpaket oder Datenbankexport.

| Einstellung | Bedeutung |
| --- | --- |
| `MLH_TUTOR_PROVIDER` | `none` als Standard; später `openai` oder `ollama` |
| `MLH_TUTOR_MODEL` | Ausdrücklich gewählte, beim Anbieter verfügbare Modell-ID |
| `MLH_OPENAI_API_KEY` | Nur bei OpenAI notwendig; alternativ bestehendes `OPENAI_API_KEY` |

Ein Schlüssel allein aktiviert den Chat nicht. Provider und Modell müssen ebenfalls gesetzt sein. Bei Ollama muss das gewählte Modell später auf dem Mac verfügbar sein. Der Anschluss ruft ausschließlich den festen lokalen Ollama-Endpunkt oder den festen HTTPS-Endpunkt der OpenAI Responses API auf. Es werden keine Modelle heruntergeladen, Dienste installiert oder Konten eingerichtet.

**Zugang eingerichtet** bedeutet, dass die benötigten Einstellungen vorliegen. Diese Anzeige ist kein Verbindungstest und kein Nachweis, dass ein Schlüssel oder Modell beim Anbieter funktioniert. Erst eine später ausdrücklich gesendete Nachricht stellt eine Modellanfrage. Kosten entstehen nach den Bedingungen des dann gewählten Anbieters.

Die OpenAI-Anbindung übergibt den Verlauf ausdrücklich im jeweiligen Aufruf und setzt `store: false`; sie nutzt keine dauerhafte Conversations-ID. Das ist keine allgemeine Zusage zur Aufbewahrung durch den Anbieter. Technischer Bezug: [Textgenerierung](https://developers.openai.com/api/docs/guides/text), [Gesprächskontext](https://developers.openai.com/api/docs/guides/conversation-state). Ollama-Vertrag: [Chat-API](https://docs.ollama.com/api/chat).

## Technischer Aufbau

`backend/tutor_context.py` erstellt den lesenden Lernkontext. `backend/tutor.py` verwaltet Status, Eingabegrenzen und die vorbereiteten Provider. `frontend/src/LearningTutor.tsx` zeigt Auswahl, Vorschau, Entwurf und später Antworten an. Die Endpunkte sind `GET /api/tutor/status`, `GET /api/tutor/context` und `POST /api/tutor/chat`. Details stehen im [API-Vertrag](api-contract.md).

Die Schnittstelle ist durch die bestehende lokale Host-/Origin-Prüfung geschützt. Es gibt keine zusätzlichen Pakete, MCP-Server, öffentlichen Ports oder Hintergrund-Modellaufrufe. Tests verwenden temporäre Datenbanken und simulierte Modellantworten; sie ersetzen keinen späteren Verbindungstest mit einem tatsächlichen Modellzugang.


## 11.11.2026 – Lernchat wählt Belege passend zur Frage

Der Modulchat sucht anhand der Fachbegriffe in der aktuellen Frage eine eindeutig passende Lernseite und daraus den am besten passenden Abschnitt. Bei Bezugnahmen wie „dazu“ oder „Abbildung 7“ zieht er frühere Nutzernachrichten für das Thema heran. Eine ausdrücklich gewählte Lernseite oder ein Lernziel bestimmt weiterhin den Bereich.

Seiten- und Abbildungsangaben werden in den belegten PDF-Bereichen gesucht. Eine passende Seite erhält beim Zusammenstellen der Auszüge Vorrang. Abbildungsverzeichnisse werden dabei ausgespart. Mehrdeutige Treffer in mehreren PDFs führen zu keiner willkürlichen Priorisierung. Die Suche untersucht je Quellenbereich höchstens 20 Seiten.

Unter „Zum Nachlesen“ stehen die Auszüge der jeweiligen Antwort. Die Vorschau zeigt den Ausgangskontext vor der Auswahl anhand der Frage. Das lokale Modell erhält Text und vorhandene Bildbeschriftungen.
