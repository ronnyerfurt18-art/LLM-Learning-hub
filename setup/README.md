# Laufzeiten außerhalb des Hubs

Der Hub erwartet zwei optionale Laufzeiten in eigenen Ordnern (Standard `~/.learning-hub/runtimes/`, einstellbar in `tutor.local.json`). `install.sh` richtet sie künftig ein; bis dahin gilt diese Beschreibung der geprüften Installation.

## Sprache (`voice_runtime`)

| Bestandteil | Inhalt |
|---|---|
| `.venv/` | Python 3.13 mit den Paketen aus `setup/voice/requirements.txt` |
| `worker.py` | aus `setup/voice/worker.py` |
| `models/whisper-small/` | Whisper Small im MLX-Format (`config.json`, `weights.npz`), ca. 460 MB |
| `models/de_DE-thorsten-medium.onnx` und `.onnx.json` | Piper-Stimme Thorsten, ca. 61 MB |
| `ready.json` | `{"transcription": "Whisper Small", "speech": "Piper · Thorsten"}` |

## Bonsai (`bonsai_runtime`)

Checkout von https://github.com/PrismML-Eng/Bonsai-demo (Apache-Lizenz 2.0), eingerichtet mit dessen `setup.sh`. Der Hub startet `scripts/start_mlx_server.sh` auf Port 8081 und erwartet `.venv-vlm/` sowie `models/Ternary-Bonsai-2-27B-mlx-2bit/` (ca. 8 GB). Details: `docs/bonsai.md`.

Das Hersteller-Repository bietet Bonsai 2 auch in kleineren Größen an (9B, 4B, 2B). Der Hub ist bisher fest auf 27B eingestellt.
