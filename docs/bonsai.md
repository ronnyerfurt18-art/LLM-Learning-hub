# Bonsai 2 im Lernhub

Im Lernchat unter „Lokales Modell“ zwischen „Bonsai 2 27B · MLX“ und dem bisherigen Ollama-Modell wechseln. Der Wechsel wird in tutor.local.json gespeichert und bleibt nach Neustart erhalten. Während einer Antwort oder Wiki-Erzeugung ist kein Wechsel möglich. Die Lernstände, Quellen und gespeicherten Musterlösungen bleiben bestehen. Die Herkunft neuer Antworten wird wie bisher mit dem Modellnamen geliefert; bestehende Wiki-Einträge werden nicht automatisch neu erzeugt.

## Laufzeit

Eigene Installation: Ordner aus `bonsai_runtime` in `tutor.local.json` (oder `MLH_BONSAI_RUNTIME`), sonst `~/.learning-hub/runtimes/bonsai-demo`.
Hersteller-Repository: https://github.com/PrismML-Eng/Bonsai-demo
Getesteter Checkout: `de058d0bfcb846cf0d8374eae8623376708673ed`.
Abhängigkeiten aus `scripts/requirements-mlx-vlm.txt`: mlx 0.32.3, mlx-vlm 0.7.8, mlx-lm 0.32.0, transformers 5.19.0.
Modell: `prism-ml/Ternary-Bonsai-2-27B-mlx-2bit`, Revision `24b5937a4a104a44f790b6ccbd0c79b6fabd4299`.
Modellgewichte: 8.595.477.990 Bytes; SHA-256 `130de5925082c168b7866b2e91b52e44abbafc99017e3ca352b77b5b55a269ed`.

Bonsai startet über das Hersteller-Skript mit dem nativen Hadamard-fähigen mlx-vlm-Lader. Der Dienst bindet ausschließlich 127.0.0.1:8081. Ein vorhandener Server wird anhand seines Listener-Prozesses, Python-Pfads, nativen Servermoduls, Modellpfads und seiner Loopback-Bindung geprüft. Passt er zur eingerichteten Laufzeit, verwendet der Hub ihn weiter. Nach einem Entladen lädt eine kurze lokale Anfrage das Modell erneut. Eine leere Modellliste wird als entladen erkannt. Unbekannte Laufzeiten werden abgelehnt. Der Lernhub beendet ausschließlich selbst gestartete Prozesse. Es erfolgt kein automatischer Modelldownload beim Seitenaufruf. Protokoll für selbst gestartete Server ist `runtimes/bonsai-demo/logs/learning-hub.log`.

## Chat und Nachdenken

Texte werden ausschließlich lokal an `/v1/chat/completions` übertragen. SSE-Antworten werden in das bestehende Chatformat umgesetzt; reasoning_content wird getrennt als ungeprüfte Überlegung dargestellt. Thinking ist pro Anfrage optional, mit 2048 Token Denkbudget. Die vorhandenen Grenzen für Antwort und Lernkontext bleiben bestehen. Truncated streams oder finish_reason=length werden als Fehler behandelt und nicht als fertige Wiki-Antwort gespeichert. Der aktuelle Lernhub sendet nur Text, keine Bilder an Bonsai.

Beim Wechsel zu Bonsai bleibt das bisherige Ollama-Modell für andere Apps verfügbar. `ollama_model` in tutor.local.json bewahrt den bisherigen Namen. Ollama muss für die Rückkehr verfügbar sein. Gleichzeitig geladene Modelle teilen sich den Arbeitsspeicher. Beim Modellwechsel bleibt der aktuelle Chat erhalten und neue Antworten verwenden den gewählten Anbieter.

Vor dem Laden und vor einer Bonsai-Anfrage prüft der Hub die geladenen Ollama-Gewichte und den physischen Arbeitsspeicher. Er reserviert für Bonsai vorsorglich das 1,6-Fache seiner Gewichte sowie 4 GiB für das System. Reicht das geschätzte Budget bei parallel geladenen Modellen nicht aus, wartet das Laden mit einer sichtbaren Meldung. Nach Freigabe des anderen Modells läuft der Start automatisch weiter. Für eine zuvor abgewiesene Chat-Anfrage kann „Erneut prüfen“ genutzt werden. Die Abschätzung ersetzt keine genaue Messung der dynamischen GPU-Speicherbelegung. Ein tatsächlicher Metal-Speicherfehler im Antwortstream wird mit einer konkreten Speichermeldung angezeigt.

## Wiederherstellung einer laufenden Installation

Nach Übernahme der Serveränderungen den Hub neu starten und im Lernchat „Bonsai 2 27B · MLX“ auswählen. Ist Bonsai schon ausgewählt, lädt „Erneut prüfen“ das entladene Modell. Der Status wechselt währenddessen von „wird geladen“ zu „bereit“. Die Prüfung einer vorhandenen Laufzeit benötigt auf macOS lesenden Zugriff auf `lsof` und `ps`.

## Prüfung

Tests decken Thinking/Text-Trennung, abbrechende Streams, unvollständige Antworten, lokale Endpunkte ohne Cloud-Schlüssel, Kontextgrenzen, unzulässige Modelle, belegte Generierung und Rückkehr zum gespeicherten Ollama-Modell ab. Fachliche Tutorqualität muss anhand gleicher Lernaufgaben verglichen werden; erfolgreiche Integration beweist keine höhere fachliche Genauigkeit.

## Abschlussprüfung am 08.11.2026

Modell vollständig geladen und SHA-256 bestätigt. Herstellerlaufzeit meldet erfolgreich geladenes Modell. Gesamte Testsuite: 239 bestanden; TypeScript und Produktionsbuild erfolgreich. Im Browser: Bonsai ausgewählt, Tutor bereit. Rückwechsel zu qwen3.8:27b-mlx und erneute Aktivierung von Bonsai erfolgreich; beide meldeten bereit. Aktive Auswahl zum Abschluss: Bonsai.

Einzelne echte Testanfragen mit dem Strategie-Lernziel (keine allgemeine Leistungsmessung):

| Modell/Modus | Erster Antworttext | Vollständige Antwort |
|---|---:|---:|
| Qwen3.8:27b-mlx, ohne Thinking | 101,6 s | 126,1 s |
| Bonsai 2 27B, ohne Thinking, gleiche Frage | 111,4 s | 140,9 s |
| Bonsai 2 27B, mit Thinking, kürzere Frage | 240,5 s | 254,3 s |

Thinking wurde separat übertragen, anschließend vollständige Antwort mit Quellenmarkern. Keine Testbewertungen oder Musterlösungen in der Lerndatenbank gespeichert. Die Prüfung bestätigt Funktionsfähigkeit, keine Überlegenheit bei fachlicher Genauigkeit.
