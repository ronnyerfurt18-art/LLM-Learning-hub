# Live-Prüfung der lokalen Modelle am 12.11.2026

## Abendfortsetzung am 12.11.2026

Die Bonsai-Anbindung wurde korrigiert und einschließlich PDF-Textcache und Performance-Anzeige in den privaten Hub übernommen. Sicherung vor Übernahme ist `data/backups/bonsai-deploy-20261112-183321/private-hub-before.tar.gz`. Der vorhandene Server mit PID 55524 wurde anhand seines nativen Startbefehls geprüft und weiterverwendet. Eine kurze Anfrage lud das zuvor entladene Modell. Nach kontrolliertem Neustart des privaten Hubs meldeten dessen Status-API und die Oberfläche im Chrome-Lernchat „Tutor bereit“. Die Prüfung über die native Browseroberfläche ist jetzt möglich.

Der Wechsel zu Bonsai entlädt das gemeinsam mit anderen Apps verwendete Ollama-Modell künftig nicht mehr. Eine echte Frage über die Oberfläche wurde gestartet. Während dieser Prüfung lud eine andere App Qwen erneut. Die Anfrage scheiterte im nativen Server um 18:40:43 mit `[METAL] Insufficient Memory`. Eine vollständige echte Tutorantwort ist in dieser Abendprüfung damit noch nicht bestätigt. Ergänzt wurden eine vorsorgliche Speicherprüfung vor Laden und Anfrage sowie eine konkrete Fehlermeldung für GPU-Speicherfehler im Stream. Auf dem 32-GB-Rechner kann Bonsai damit auf die Freigabe des großen Ollama-Modells warten. Zusätzliche gezielte Prüfungen von Bonsai, Messwerten und Nachtlauf ergaben anschließend 58 bestandene Tests.

66 gezielte Tests sowie Frontend-Build und drei Rendering-Tests waren erfolgreich. Die erste Gesamtsuite ergab 494 bestandene Tests und einen Fehlschlag im bestehenden OCR-Test `test_scanned_pdf_is_read_with_the_local_engine`. Derselbe OCR-Test scheiterte im bisherigen privaten Programmstand mit identischer Ausgabe. Nach Ergänzung der Nachtlauf-Tests wurden weitere 33 gezielte Tests erfolgreich ausgeführt. Der abschließende Lauf und seine genaue Testzahl stehen in `data/benchmarks/2026-11-12-overnight/verification-tests.log`.

Ein lokaler Hintergrundprozess wurde für 22 Uhr bis 7 Uhr am 13.11. eingerichtet. Er verwendet die unveränderte 30-Fragen-Suite mit jeweils zwei Antworten von Bonsai, Qwen 27B und Qwen 9B. Die Modellreihenfolge rotiert je Themenblock. Vor Modellwechseln prüft er freie Laufzeiten. Er pausiert bei erkannter Aktivität anderer Apps und setzt anhand gespeicherter Antworten fort. Anschließend sind sechs gepaarte Vorladeversuche vorgesehen. Modelle werden zwischen kalten Vergleichsarmen über die API entladen. Der Bonsai-Serverprozess bleibt bestehen. Nach einem Neustart gilt eine fortgesetzte zweite Antwort als kalt, sofern die erste Antwort nicht im selben Lauf unmittelbar vorausging.

Ausgaben und Fortschritt liegen in `data/benchmarks/2026-11-12-overnight/`. `status.json` unterscheidet geplant, laufend, unterbrochen und Messungen abgeschlossen. Antworten werden einzeln mit `fsync` gesichert. Eine Sperrdatei verhindert doppelte Worker. Die Statusprüfung fremder Apps ist eine Momentaufnahme, daher muss mögliche gleichzeitige Aktivität bei der Auswertung berücksichtigt werden. Der Prozess hält den Mac gegen automatischen Leerlauf-Ruhezustand wach. Eine fachliche Bewertung nach Quellen bleibt ausstehend. Die automatische Wiederaufnahme einer KI-Sitzung nach Auffüllen ihres Nutzungsvolumens konnte mangels verfügbarem Zeitplanwerkzeug nicht eingerichtet werden.

Die nachfolgenden Abschnitte beschreiben den vorherigen Pilotstand.

Die abschließende Gesamtsuite mit Speicherprüfung ergab 507 bestandene Tests bei einem ausgeschlossenen, zuvor im bisherigen Stand reproduzierten OCR-Fehler. Zwei zusätzliche Nachtlauf-Tests prüfen inzwischen auch die echte Hub-Stream-Prüfung. Ein weiterer Oberflächenfehler wurde behoben. Der für einen erneuten Versuch behaltene Gesprächsbeitrag sperrte den Modellwechsel nach einer fehlgeschlagenen Frage. Der Auswahlknopf bleibt jetzt nur bei laufender Anfrage, Modellwechsel oder Sprachverarbeitung gesperrt. Die fehlgeschlagene Frage bleibt für einen erneuten Versuch erhalten.

Die zweite private Sicherung vor Übernahme der Speicherprüfung liegt unter `data/backups/bonsai-deploy-20261112-193202/`. Ein für 22 Uhr gestarteter Nacht-Worker führt vor dem Modellvergleich zusätzlich die echte `/api/tutor/chat/stream`-Prüfung durch, sobald die Laufzeiten frei sind. Bei Erfolg speichert er `hub-smoke.json` mit fertiger Antwort und Performance-Werten. Die Abendprüfung hat die Speichermeldung im Browser bestätigt. Die vollständige Antwort unter freien Ressourcen bleibt bis zum Nachtlauf offen.

## Umfang und Ausgangszustand

Der Zugriff auf Ollama und Bonsai funktioniert wieder. Gemessen wurden drei eingefrorene Fragen zum Lernziel „Ziele, Strategie und Governance“, jeweils zweimal mit drei Modellen: **18 vollständige Antworten, keine am Tokenlimit abgeschnitten**. Dies ist ein Pilot, kein abgeschlossener 30-Fragen-Qualitätsvergleich.

Rohdaten, Prompts, Quellenauszüge, Skripte und Prüfsummen: `data/benchmarks/2026-11-12-live-resume/`. Die Pilotdatei enthält unverändert die ersten drei Fragen der vorbereiteten Suite. Alle Manifeste nennen den Hash derselben Suite.

Bonsai lief beim Beginn bereits seit dem 09.11.; Ollama hatte kein Modell geladen. Nach sechs Bonsai-Antworten wurde bei null aktiven Anfragen dessen Modell über `/unload` entladen. `/health` bestätigte leere Modellbelegung. Danach liefen Qwen 27B und Qwen 9B nacheinander; jedes wurde anschließend entladen. Der Bonsai-Prozess wurde nicht beendet.

Parameter: Thinking aus, Temperatur 0,7, maximal 1.400 Ausgabe-Tokens, fünf Sekunden Pause zwischen Anfragen. Ollama: Kontextfenster 32.768, Seed 42. Bonsai: vorhandene Laufzeitparameter ohne nachgewiesenen Seed. Die erste Bonsai-Anfrage hatte einen Cache-Miss, aber keinen kontrollierten Laufzeitneustart. Die ersten Qwen-Anfragen enthalten Modellladezeit. Weitere neue Fragen liefen mit dem vorhandenen Cache; identische Wiederholungen direkt danach.

## Antwortbeginn im direkten Provider-Aufruf

Die Zeiten enthalten weder Kontextaufbau noch Hub-/Browsertransport. „Neue Frage“ bedeutet nicht automatisch kalter Cache.

| Modell | Frage | Neue Frage | Wiederholung | Cache-Tokens neu / wiederholt |
|---|---|---:|---:|---:|
| Bonsai 2 27B / MLX 2 Bit | Wissen | 88.36 s | 0.79 s | 0 / 2431 |
| Bonsai 2 27B / MLX 2 Bit | Transfer | 9.74 s | 0.59 s | 2048 / 2440 |
| Bonsai 2 27B / MLX 2 Bit | Anwendung | 10.35 s | 0.68 s | 2048 / 2467 |
| Qwen 3.8 27B / MLX nvfp4 | Wissen | 101.23 s | 0.71 s | 0 / 2427 |
| Qwen 3.8 27B / MLX nvfp4 | Transfer | 47.61 s | 0.68 s | 0 / 2436 |
| Qwen 3.8 27B / MLX nvfp4 | Anwendung | 1.79 s | 0.72 s | 2403 / 2463 |
| Qwen 3.5 9B / GGUF Q4_K_M | Wissen | 33.63 s | 0.23 s | 0 / 2428 |
| Qwen 3.5 9B / GGUF Q4_K_M | Transfer | 6.30 s | 0.23 s | 1408 / 2437 |
| Qwen 3.5 9B / GGUF Q4_K_M | Anwendung | 6.24 s | 0.22 s | 1417 / 2464 |

## Laden, Einlesen und Ausgabe getrennt

| Modell | Laden bei erster Frage | Prefill bei erster Frage | Median Ausgabe (6 Antworten) |
|---|---:|---:|---:|
| Bonsai 2 27B / MLX 2 Bit | bereits geladen; nicht gemessen | 80.88 s | 6.2 Tokens/s |
| Qwen 3.8 27B / MLX nvfp4 | 34.04 s | 66.65 s | 11.8 Tokens/s |
| Qwen 3.5 9B / GGUF Q4_K_M | 19.70 s | 13.90 s | 17.1 Tokens/s |

Bonsais Prefix-Cache ist für diesen Pilot erstmals live belegt: Bei der ersten identischen Wiederholung wurden 2.431 von 2.432 Tokens wiederverwendet. Auch die beiden anderen Fragen nutzten jeweils 2.048 Präfix-Tokens. Bei Qwen 27B wurde die Transferfrage vollständig neu gelesen, die folgende Anwendungsfrage dagegen teilweise aus dem Cache bedient. Eine pauschale Regel „andere Frage = immer kalt“ ist daher nicht haltbar.

Der kleinere Qwen war in diesen Anfragen beim Prefill und bei der Ausgabe schneller. Eine allgemeine Modellrangliste folgt daraus nicht: ein Lernziel, feste Modellreihenfolge, keine kontrollierten Thermik-/Speicherdruckdaten. Systemwerte für Swap und Speicherdruck blieben unbekannt. Der Effekt des PDF-Textcaches lässt sich aus diesen direkten Aufrufen nicht ableiten.

## Erste inhaltliche Durchsicht

Die Durchsicht war **nicht verblindet**. Die Rohdaten behalten `quality_review: null`; es wurden keine Qualitätsnoten eingetragen. Grundlage waren die tatsächlichen Fragen, Antworten und mitgelieferten Quellenauszüge.

- **Bonsai:** Alle sechs Antworten bestanden aus einem neuen Arbeitsauftrag. Bereits die direkte Wissensfrage nach der Beziehung zwischen Unternehmensziel, Anforderungen und Informatikstrategie blieb unbeantwortet. Bei Übungen kann eine Rückfrage angemessen sein; bei dieser Wissensfrage widerspricht sie dem Systemauftrag zur vollständigen Erklärung.
- **Qwen 27B:** Die Wissensfrage wurde inhaltlich mit Quellenmarker beantwortet. Die erste Transferantwort beginnt jedoch mit „Du hast den Kern der Frage richtig erkannt“, obwohl die Person nur eine Frage gestellt und keinen Lösungsversuch abgegeben hat. Dies verletzt die Vorgabe, keine nicht geäußerte Leistung zuzuschreiben.
- **Qwen 9B:** Die Wissensantwort beschreibt vier Phasen einer angeblich gezeigten Abbildung. Im eingefrorenen Kontext wird Abbildung 8 lediglich angekündigt; Abbildung und Phasenliste sind nicht enthalten. Die Anwendungsantwort verbindet konkrete Logistiktechnik mit [S1], obwohl Förderbänder, Roboter und Pick-to-Light im mitgegebenen S1-Auszug nicht vorkommen. Als gekennzeichnete Beispiele wären solche Übertragungen anders zu bewerten; hier ist die Zuordnung zum Beleg nicht sauber.

**Entscheidung:** Die Standardmodellauswahl bleibt unverändert. Für einen Wechsel fehlen der vollständige Vergleich über 30 Fragen, kontrollierte Wiederholungen und die fachliche Quellenprüfung.

## Laufzeit und Oberfläche

Der Test-Hub auf Port 8011 verwendet ein SQLite-Backup, ohne initialen Scan oder Hintergrundscan. Seine Ollama-Bereitschaft wurde live bestätigt. Die Bonsai-Bereitschaft scheiterte an der bereits belegten Portnummer: `start_runtime()` übernimmt absichtlich keinen fremden Prozess, selbst wenn dessen Modellliste passt. Dies bleibt ein Problem des vorhandenen verwaisten Prozesses.

Die interaktive Browserprüfung wurde versucht, konnte aber wegen „The browser access host is unavailable“ nicht ausgeführt werden. Rendering-Tests und Build ersetzen diese Prüfung nicht.

## Noch offene Abnahme

- Vollständiger 30-Fragen-Vergleich samt Quellenprüfung und kontrollierter Messreihenfolge.
- Gepaarte Vorladeexperimente mit identischen Cache-Ausgangszuständen.
- Bonsai-Integration mit einer vom Hub gestarteten Laufzeit.
- Sichtprüfung im Browser und Übernahme in den privaten Hub.

## Cache-Prüfung über den vollständigen Hub

Alle zehn Chat-Anfragen über `POST /api/tutor/chat/stream` endeten ohne Fehler und mit vollständiger `performance`-Struktur. Der HTTP-Client misst ab Absenden der Frage; die Hub-Uhr beginnt nach dem Kontextaufbau. Dies ist eine echte HTTP-Prüfung, keine Browser-/Paint-Messung.

| Schritt | Erster Text am HTTP-Client | Erster Text im Hub | Cache / Prompt-Tokens | Kontextaufbau |
|---|---:|---:|---:|---:|
| A kalt: Lernziel 1, Frage 1 | 76.76 s | 76.50 s | 0 / 3441 | 207 ms |
| B identisch wiederholt | 0.54 s | 0.45 s | 3436 / 3441 | 80 ms |
| C andere Frage, neues Gespräch | 85.12 s | 84.93 s | 0 / 3443 | 177 ms |
| C2 Folgefrage im Verlauf | 7.40 s | 7.27 s | 3438 / 3702 | 128 ms |
| C3 zweite Folgefrage | 1.52 s | 1.34 s | 4008 / 4039 | 178 ms |
| D1 Lernziel 2 | 99.97 s | 99.72 s | 0 / 3546 | 242 ms |
| D2 zurück zu Lernziel 1, Frage 1 | 0.80 s | 0.62 s | 3440 / 3441 | 175 ms |
| M1 Modulchat ohne Lernziel | 97.03 s | 96.69 s | 0 / 3683 | 343 ms |
| M2 Modulchat Folgefrage | 1.35 s | 1.26 s | 3864 / 3887 | 85 ms |
| E2 nach Modellwechsel: Lernziel 1, Frage 1 | 84.20 s | 83.99 s | 0 / 3441 | 207 ms |

Die leeren Ladeanfragen vor A und E sind aus diesen TTFT-Zeiten ausgeschlossen. Der Wechsel wurde durch erfolgreiche Lade-/Entladeaufrufe für Qwen 27B, Qwen 9B und erneut Qwen 27B ausgeführt. Ein zusätzlicher `/api/ps`-Beobachter brach während des Ladens mit einem Timeout ab; seine unvollständige Aufzeichnung ist kein unabhängiger Nachweis der gesamten Modellfolge. Die eigentliche Messfolge lief fehlerfrei weiter.

Nach Rückkehr zum zuvor genutzten Lernziel (D2) war der Cache weiterhin nutzbar; nach Entladen und zwischenzeitlichem Laden des anderen Modells (E2) wurden alle 3.441 Prompt-Tokens neu gelesen. Die alten Baseline-Befunde sind damit im aktuellen Hub reproduziert. Daraus folgt **kein neuer TTFT-Gewinn durch die Softwareänderungen**. Der zuvor nachgewiesene PDF-Cache-Vorteil bleibt eine separate Messung des Kontextaufbaus.

Die statische Oberfläche wurde mit HTTP 200 ausgeliefert; ihr JavaScript-Bundle enthält die Performance-Anzeige und die Beschriftung für die Browser-Ankunftszeit (`static-ui-check.json`). Eine visuelle Prüfung bleibt offen.

Rohdaten: `hub-cache.json`; genaue Aktionen: `hub-cache-scenario.json`. Nach dem Lauf wurden die Ollama-Modelle entladen und der eigene Test-Hub beendet. Der fremde Bonsai-Server bleibt vorhanden, sein Modell ist entladen. Der private Hub auf Port 8000 und seine Konfiguration wurden nicht geändert.

