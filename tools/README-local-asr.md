# Lokale Video-Transkription

`transcribe_local_videos.py` verarbeitet MP4-Dateien mit einer bereits lokal vorhandenen Whisper-Modelldatei. Es lädt keine Modelle herunter und nutzt keinen externen Transkriptionsdienst. Python, NumPy, PyTorch und Whisper sowie FFmpeg müssen vorher lokal vorhanden sein. Die Pfade sind konfigurierbar; temporäre Caches können nach einer Bereinigung fehlen.

Beispiel, aus dem Projektordner:

```bash
python3 tools/transcribe_local_videos.py \
  --source-dir '<Studienordner>/10001 Lernen lernen (Demo)/Videos' \
  --work-root /private/tmp/hub-transkription \
  --transcript-root docs/quellen \
  --model-path <Ordner>/small.pt \
  --ffmpeg-path <Pfad zu ffmpeg>
```

Der Ablauf prüft zuerst die Videodauern über FFmpeg. Jede vollständige Tonspur wird als mono WAV mit 16 kHz und 16-Bit-PCM extrahiert. Whisper wird auf der CPU mit vier Threads ausgeführt (`language='de'`, `fp16=False`, `temperature=0`). Die originale MP4-Datei bleibt unverändert.

- `--work-root`: je Quellordner ein Unterordner für WAV, JSON, TXT und Dauerinventar. Diese Arbeitsdateien gehören nicht ins Projekt.
- `--transcript-root`: je Quellordner ein Unterordner für ausdrücklich markierte TXT-Rohtranskripte und `duration-inventory.json`. Der Name des Quellordners wird kleingeschrieben, beispielsweise `Session4` zu `session4`.
- `--inventory-only`: nur die Videodauern prüfen; keine Spracherkennung ausführen.
- `--initial-prompt`: optionaler kurzer Hinweis für die Spracherkennung; ersetzt keine Prüfung an den Quellen.

Ein erneuter Aufruf verwendet vollständige JSON-Ausgaben nur mit passender Manifestdatei weiter. Diese hält den aufgelösten Quellpfad, Dateigröße und Änderungszeit in Nanosekunden fest, ebenso die Identität von Modell/FFmpeg und die ASR-/Audio-Konfiguration. Fehlt das Manifest oder hat sich eine Identität/Konfiguration geändert, werden Tonextraktion und ASR erneut ausgeführt; ein altes `video1.json` wird nicht still für eine veränderte MP4 übernommen. Eine bei passendem Manifest trotzdem unvollständige JSON-Datei löst einen Fehler aus. Auch eine Änderung von Quelle/Modell/FFmpeg während der Verarbeitung wird erkannt. Neue Ausgaben werden zunächst temporär geschrieben und erst nach vollständigem Schreiben ersetzt. Ein abgebrochener WAV-Export wird beim nächsten Lauf wiederholt.

Im Lauf vom 14. Oktober 2026 wurde die Manifestprüfung nach Abschluss des ersten ASR-Prozesses ergänzt, um diesen Prozess nicht zu unterbrechen. Für seine elf soeben erzeugten und inhaltlich gelesenen JSON-Ausgaben wurden die Identitäten der unveränderten Originale und tatsächlich verwendeten Konfiguration nachgetragen. Danach übersprang ein realer Wiederaufruf alle elf ASR-Ergebnisse. Geänderte erwartete Quell-Änderungszeit oder Prompt-Konfiguration wurden zusätzlich als nicht fortsetzbar geprüft. Das ist kein allgemeines automatisches Übernehmen beliebiger älterer Dateien ohne Provenienz.

Rohtranskripte sind keine freigegebenen Lerntexte. Fachbegriffe, Namen, Zahlen und Satzgrenzen müssen anhand der Folien und bei Bedarf der Originalaufnahme geprüft werden. Die Segmentmarken sind automatisch erzeugt. Die lokale Transkription bedeutet zudem nicht, dass eine anschließende Ausarbeitung mit Codex vollständig offline ist: im Werkzeug angezeigte Texte und Bilder gelangen in dessen Modellkontext.
