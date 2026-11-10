#!/usr/bin/env python3
"""Transcribe local video files with an already cached Whisper model.

No model name, model download, remote ASR, or upload is accepted. Dependencies
must already exist in the selected Python environment (or its PYTHONPATH).
WAV and JSON working files stay in --work-root; only marked raw TXT transcripts
and compact duration inventories are written to --transcript-root.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import wave


def stamp(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def atomic_text(path: Path, text: str) -> None:
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(text, encoding="utf-8")
    pending.replace(path)


def video_key(path: Path) -> tuple[int, str]:
    number = re.search(r"(\d+)$", path.stem)
    return (int(number.group(1)) if number else 0, path.name)


def file_identity(path: Path) -> dict:
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    return {"path": str(resolved), "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def expected_manifest(video: Path, args: argparse.Namespace, whisper_version: str) -> dict:
    return {
        "manifest_version": 1,
        "source": file_identity(video),
        "model": file_identity(args.model_path),
        "ffmpeg": file_identity(args.ffmpeg_path),
        "configuration": {
            "whisper_version": whisper_version,
            "device": "cpu", "threads": args.threads,
            "language": "de", "task": "transcribe", "fp16": False,
            "temperature": 0, "condition_on_previous_text": True,
            "initial_prompt": args.initial_prompt,
            "audio_channels": 1, "audio_sample_rate": 16000,
            "audio_codec": "pcm_s16le",
        },
    }


def can_resume(target: Path, manifest_path: Path, expected: dict) -> bool:
    if not target.is_file() or not manifest_path.is_file():
        return False
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")) == expected
    except (OSError, json.JSONDecodeError):
        return False


def duration(ffmpeg: Path, video: Path) -> float:
    probe = subprocess.run(
        [str(ffmpeg), "-nostdin", "-hide_banner", "-i", str(video)],
        capture_output=True, text=True, check=False,
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    if not match:
        raise RuntimeError(f"FFmpeg could not determine duration: {video}\n{probe.stderr}")
    hours, minutes, seconds = map(float, match.groups())
    return hours * 3600 + minutes * 60 + seconds


def raw_text(result: dict, source: Path, seconds: float, model_path: Path) -> str:
    header = [
        "ROHTRANSKRIPT – automatische lokale Spracherkennung, nicht redaktionell korrigiert",
        f"Quelle: {source}",
        f"Videodauer: {stamp(seconds)} ({seconds:.2f} Sekunden)",
        f"Modell: vorhandene lokale Datei {model_path.name}; Whisper, Sprache de, CPU",
        "Hinweis: Fachbegriffe, Namen, Zahlen und Satzgrenzen können falsch erkannt sein.",
        "Die Zeitmarken stammen aus der automatischen Segmentierung.",
        "",
    ]
    segments = [
        f"[{stamp(item['start'])}–{stamp(item['end'])}] {item['text'].strip()}"
        for item in result["segments"]
    ]
    return "\n".join(header + segments + [""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, action="append", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--transcript-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--ffmpeg-path", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--initial-prompt", default="Vorlesung an einer Hochschule.")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    if not args.model_path.is_file():
        parser.error("The local model file is missing; downloading models is not supported.")
    if not args.ffmpeg_path.is_file():
        parser.error("The local FFmpeg executable is missing.")
    if args.threads < 1:
        parser.error("--threads must be positive.")

    jobs = []
    for source_dir in args.source_dir:
        source_dir = source_dir.resolve(strict=True)
        session = source_dir.name.lower()
        work = args.work_root / session
        transcripts = args.transcript_root / session
        work.mkdir(parents=True, exist_ok=True)
        transcripts.mkdir(parents=True, exist_ok=True)
        videos = sorted(source_dir.glob("*.mp4"), key=video_key)
        if not videos:
            parser.error(f"No MP4 files in {source_dir}")
        inventory = {"session": session, "duration_method": "FFmpeg container duration", "videos": []}
        for video in videos:
            seconds = duration(args.ffmpeg_path, video)
            inventory["videos"].append({"file": video.name, "duration_seconds": seconds, "duration": stamp(seconds)})
            print(f"{session}/{video.name}: duration {stamp(seconds)} ({seconds:.2f}s)", flush=True)
            jobs.append((session, video, seconds, work, transcripts))
        inventory["total_duration_seconds"] = round(sum(row["duration_seconds"] for row in inventory["videos"]), 2)
        inventory["total_duration"] = stamp(inventory["total_duration_seconds"])
        serialized = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
        atomic_text(work / "duration-inventory.json", serialized)
        atomic_text(transcripts / "duration-inventory.json", serialized)
    if args.inventory_only:
        return

    import numpy as np
    import torch
    import whisper

    torch.set_num_threads(args.threads)
    print(f"Loading cached model {args.model_path.name} on CPU with {args.threads} threads", flush=True)
    model = whisper.load_model(str(args.model_path.resolve(strict=True)), device="cpu")
    print("Model ready", flush=True)
    for session, video, seconds, work, transcripts in jobs:
        started = time.monotonic()
        target = work / f"{video.stem}.json"
        manifest_path = work / f"{video.stem}.manifest.json"
        manifest = expected_manifest(video, args, whisper.__version__)
        resume = can_resume(target, manifest_path, manifest)
        if resume:
            result = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(result.get("segments"), list) or not result.get("text"):
                raise RuntimeError(f"Existing transcript is incomplete: {target}")
            print(f"{session}/{video.name}: using completed JSON transcript", flush=True)
        else:
            wav_path = work / f"{video.stem}.wav"
            if not wav_path.exists() or not resume:
                print(f"{session}/{video.name}: extracting local audio", flush=True)
                pending = wav_path.with_suffix(".pending.wav")
                subprocess.run([
                    str(args.ffmpeg_path), "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(pending),
                ], check=True)
                pending.replace(wav_path)
            with wave.open(str(wav_path), "rb") as wav:
                if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                    raise ValueError(f"Expected 16 kHz mono PCM16 audio: {wav_path}")
                audio_seconds = wav.getnframes() / wav.getframerate()
                if abs(audio_seconds - seconds) > 2:
                    raise ValueError(f"Audio duration differs from video: {video}")
                audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            print(f"{session}/{video.name}: transcribing locally", flush=True)
            result = model.transcribe(
                audio, language="de", task="transcribe", fp16=False,
                temperature=0, verbose=None, initial_prompt=args.initial_prompt,
                condition_on_previous_text=True,
            )
            if expected_manifest(video, args, whisper.__version__) != manifest:
                raise RuntimeError(f"Source, model, or FFmpeg changed during transcription: {video}")
            atomic_text(target, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            atomic_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        text = raw_text(result, video, seconds, args.model_path)
        atomic_text(work / f"{video.stem}.txt", text)
        atomic_text(transcripts / f"{video.stem}.txt", text)
        print(f"{session}/{video.name}: COMPLETE; {len(result['segments'])} segments; {time.monotonic() - started:.1f}s; {transcripts / (video.stem + '.txt')}", flush=True)
    print("ALL REQUESTED VIDEOS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
