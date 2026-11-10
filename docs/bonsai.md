# Bonsai 2 im Lernhub

Im Lernchat unter „Lokales Modell“ zwischen „Bonsai 2 27B · MLX“ und dem bisherigen Ollama-Modell wechseln. Der Wechsel wird in tutor.local.json gespeichert und bleibt nach Neustart erhalten. Während einer Antwort oder Wiki-Erzeugung ist kein Wechsel möglich. Die Lernstände, Quellen und gespeicherten Musterlösungen bleiben bestehen. Die Herkunft neuer Antworten wird wie bisher mit dem Modellnamen geliefert; bestehende Wiki-Einträge werden nicht automatisch neu erzeugt.

## Laufzeit

Eigene Installation: Ordner aus `bonsai_runtime` in `tutor.local.json` (oder `MLH_BONSAI_RUNTIME`), sonst `~/.learning-hub/runtimes/bonsai-demo`.
Hersteller-Repository: https://github.com/PrismML-Eng/Bonsai-demo
Getesteter Checkout: `de058d0bfcb846cf0d8374eae8623376708673ed`.
Abhängigkeiten aus `scripts/requirements-mlx-vlm.txt`: mlx 0.32.3, mlx-vlm 0.7.8, mlx-lm 0.32.0, transformers 5.19.0.
Modell: `prism-ml/Ternary-Bonsai-2-27B-mlx-2bit`, Revision `24b5937a4a104a44f790b6ccbd0c79b6fabd4299`.
Modellgewichte: 8.595.477.990 Bytes; SHA-256 `130de5925082c168b7866b2e91b52e44abbafc99017e3ca352b77b5b55a269ed`.

Bonsai startet über das Hersteller-Skript mit dem nativen Hadamard-fähigen mlx-vlm-Lader. Kein generischer mlx-lm-Lader. Der Dienst bindet ausschließlich 127.0.0.1:8081. Bereits fremd belegte Ports werden nicht übernommen. Der Lernhub beendet nur seinen eigenen Bonsai-Prozess. Es erfolgt kein automatischer Modelldownload beim Seitenaufruf. Protokoll: `runtimes/bonsai-demo/logs/learning-hub.log`.

## Chat und Nachdenken

Texte werden ausschließlich lokal an `/v1/chat/completions` übertragen. SSE-Antworten werden in das bestehende Chatformat umgesetzt; reasoning_content wird getrennt als ungeprüfte Überlegung dargestellt. Thinking ist pro Anfrage optional, mit 2048 Token Denkbudget. Die vorhandenen Grenzen für Antwort und Lernkontext bleiben bestehen. Truncated streams oder finish_reason=length werden als Fehler behandelt und nicht als fertige Wiki-Antwort gespeichert. Der aktuelle Lernhub sendet nur Text, keine Bilder an Bonsai.

Beim Wechsel zu Bonsai wird das bisherige Ollama-Modell aus dem Arbeitsspeicher entladen, aber nicht gelöscht. `ollama_model` in tutor.local.json bewahrt den bisherigen Namen. Ollama muss für die Rückkehr verfügbar sein. Beim Modellwechsel bleibt der aktuelle Chat erhalten; neue Antworten verwenden den gewählten Anbieter.

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
