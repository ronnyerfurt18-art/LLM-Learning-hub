"""Bounded, local-only speech jobs; recordings live only in temporary files."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response

from .local_model import runtime_dir

RUNTIME = runtime_dir('voice', 'MLH_VOICE_RUNTIME')
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_SECONDS = 90
AUDIO_TYPES = {'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav', 'audio/x-wav'}


class VoiceService:
    def __init__(self, runtime=RUNTIME):
        self.runtime = Path(runtime)
        self.lock = asyncio.Lock()

    def status(self):
        ready = all((self.runtime / path).is_file() for path in (
            'ready.json', '.venv/bin/python', 'worker.py',
            'models/whisper-small/config.json', 'models/whisper-small/weights.npz',
            'models/de_DE-thorsten-medium.onnx', 'models/de_DE-thorsten-medium.onnx.json',
        ))
        return {'available': ready, 'local': True, 'transcription': 'Whisper Small',
                'speech': 'Piper · Thorsten', 'max_seconds': MAX_SECONDS,
                'message': 'Sprache wird auf deinem Mac verarbeitet.' if ready else 'Die lokale Sprachfunktion ist noch nicht eingerichtet.'}

    async def run(self, mode, content):
        if not self.status()['available']:
            raise HTTPException(503, 'Die lokale Sprachfunktion ist noch nicht eingerichtet.')
        if self.lock.locked():
            raise HTTPException(409, 'Die Sprachfunktion arbeitet gerade. Bitte kurz warten.')
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix='mlh-voice-') as folder:
                source, target = Path(folder) / 'input', Path(folder) / 'output'
                source.write_bytes(content)
                env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                       'NUMBA_CACHE_DIR': str(Path(folder) / 'numba')}
                proc = await asyncio.create_subprocess_exec(
                    str(self.runtime / '.venv/bin/python'), str(self.runtime / 'worker.py'),
                    mode, str(source), str(target), env=env,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=120)
                except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
                    if proc.returncode is None:
                        proc.kill()
                    await proc.wait()
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    raise HTTPException(504, 'Die Sprachverarbeitung hat zu lange gedauert. Bitte kürzer aufnehmen.')
                if proc.returncode != 0 or not target.is_file():
                    raise HTTPException(422, 'Die Aufnahme konnte nicht verarbeitet werden. Bitte erneut aufnehmen.' if mode == 'transcribe' else 'Die Antwort konnte nicht vorgelesen werden. Bitte erneut versuchen.')
                if target.stat().st_size > 24 * 1024 * 1024:
                    raise HTTPException(413, 'Die Sprachausgabe ist zu lang.')
                return target.read_bytes()


async def bounded_body(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(413, 'Die Aufnahme oder Anfrage ist zu groß. Bitte kürzen.')
        data.extend(chunk)
    if not data:
        raise HTTPException(400, 'Die Aufnahme oder Anfrage ist leer.')
    return bytes(data)


def register_voice_routes(app, service=None):
    service = service or VoiceService()

    @app.get('/api/tutor/voice/status')
    def voice_status():
        return service.status()

    @app.post('/api/tutor/voice/transcribe')
    async def transcribe(request: Request):
        if request.headers.get('content-type', '').split(';')[0].lower() not in AUDIO_TYPES:
            raise HTTPException(415, 'Dieses Aufnahmeformat wird nicht unterstützt.')
        data = await bounded_body(request, MAX_AUDIO_BYTES)
        raw = await service.run('transcribe', data)
        try:
            result = json.loads(raw)
            text = result['text'].strip()
            duration = float(result['seconds'])
            if not text:
                raise HTTPException(422, 'Keine Sprache erkannt. Bitte näher am Mikrofon sprechen.')
            if len(text) > 4000:
                raise HTTPException(413, 'Der erkannte Text ist zu lang. Bitte die Frage kürzer aufnehmen.')
            if not 0 < duration <= MAX_SECONDS + .5:
                raise ValueError('duration')
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(502, 'Die Spracherkennung hat keine gültige Antwort geliefert.')
        return {'text': text, 'seconds': duration, 'local': True}

    @app.post('/api/tutor/voice/speak')
    async def speak(request: Request):
        try:
            body = json.loads(await bounded_body(request, 64 * 1024))
        except ValueError:
            raise HTTPException(400, 'Ungültige Anfrage für die Sprachausgabe.')
        text = body.get('text') if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise HTTPException(400, 'Zum Vorlesen ist ein Text mit höchstens 12.000 Zeichen erforderlich.')
        audio = await service.run('speak', text.encode('utf-8'))
        return Response(audio, media_type='audio/wav', headers={'Cache-Control': 'no-store'})
