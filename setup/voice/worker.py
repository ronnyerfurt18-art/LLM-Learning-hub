"""Disposable speech worker. Models are preinstalled, never fetched during use."""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def spoken_text(text):
    text = re.sub(r'```[\s\S]*?```', ' Codebeispiel siehe Chat. ', text)
    text = re.sub(r'\[S\d+\]', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(?m)^\s*[#>*-]+\s*', '', text)
    text = re.sub(r'[*_`|]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def transcribe(source, target):
    import imageio_ffmpeg
    import numpy as np
    import mlx_whisper
    with source.open('rb') as recording:
        header = recording.read(12)
    if header.startswith(b'\x1a\x45\xdf\xa3'):
        audio_format = 'matroska'
    elif header.startswith(b'OggS'):
        audio_format = 'ogg'
    elif header.startswith(b'RIFF') and header[8:12] == b'WAVE':
        audio_format = 'wav'
    elif header[4:8] == b'ftyp':
        audio_format = 'mov'
    else:
        raise ValueError('Unsupported recording format')
    # Only decode supported audio containers, never playlists.
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error',
        '-protocol_whitelist', 'file,pipe', '-f', audio_format, '-i', str(source), '-t', '91', '-vn',
        '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1'],
        capture_output=True, check=True, timeout=25)
    audio = np.frombuffer(result.stdout, dtype=np.float32).copy()
    duration = len(audio) / 16000
    if not .15 <= duration <= 90.5:
        raise ValueError('Recording duration outside limits')
    # Empty/silent clips must not become hallucinated questions.
    if float(np.sqrt(np.mean(audio ** 2))) < .001:
        text = ''
    else:
        result = mlx_whisper.transcribe(audio, path_or_hf_repo=str(ROOT / 'models/whisper-small'),
            language='de', temperature=0, condition_on_previous_text=False,
            verbose=None, no_speech_threshold=.6)
        text = result['text'].strip()
    target.write_text(json.dumps({'text': text, 'seconds': duration}, ensure_ascii=False))


def speak(source, target):
    import onnxruntime
    from piper import PiperVoice
    onnxruntime.disable_telemetry_events()
    text = spoken_text(source.read_text())
    if not text:
        raise ValueError('No spoken text')
    voice = PiperVoice.load(str(ROOT / 'models/de_DE-thorsten-medium.onnx'))
    with wave.open(str(target), 'wb') as output:
        voice.synthesize_wav(text, output)


if __name__ == '__main__':
    mode, source, target = sys.argv[1:]
    {'transcribe': transcribe, 'speak': speak}[mode](Path(source), Path(target))
