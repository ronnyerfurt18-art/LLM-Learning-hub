import { useEffect, useRef, useState } from 'react';

type CaptureState = 'idle' | 'requesting' | 'recording' | 'transcribing';
type VoiceStatus = { available: boolean; message: string; max_seconds: number };
const MAX_BYTES = 10 * 1024 * 1024;

async function responseError(response: Response) {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
  } catch { /* Use the readable fallback. */ }
  return 'Die Sprachfunktion ist gerade nicht erreichbar. Bitte erneut versuchen.';
}

export function useTutorVoice(scopeKey: string, onTranscript: (text: string) => void) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [capture, setCapture] = useState<CaptureState>('idle');
  const [seconds, setSeconds] = useState(0);
  const [notice, setNotice] = useState('');
  const [readReplies, setReadReplies] = useState(false);
  const [speechLoading, setSpeechLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const audioElement = useRef<HTMLAudioElement>(null);
  const alive = useRef(true);
  const generation = useRef(0);
  const state = useRef<CaptureState>('idle');
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const request = useRef<AbortController | null>(null);
  const speechRequest = useRef<AbortController | null>(null);
  const speechGeneration = useRef(0);
  const currentUrl = useRef('');
  const callback = useRef(onTranscript);
  callback.current = onTranscript;
  const supported = !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';
  const maxSeconds = Math.min(status?.max_seconds ?? 90, 90);

  const changeState = (value: CaptureState) => { state.current = value; if (alive.current) setCapture(value); };
  const stopTracks = () => {
    window.clearInterval(timer.current); timer.current = undefined;
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
  };
  const stopSpeaking = () => {
    speechGeneration.current++;
    speechRequest.current?.abort(); speechRequest.current = null;
    audioElement.current?.pause();
    if (currentUrl.current) URL.revokeObjectURL(currentUrl.current);
    currentUrl.current = '';
    if (alive.current) { setAudioUrl(''); setSpeechLoading(false); }
  };
  const cancel = () => {
    generation.current++;
    request.current?.abort(); request.current = null;
    if (recorder.current?.state === 'recording') recorder.current.stop();
    recorder.current = null; stopTracks(); changeState('idle');
  };

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/tutor/voice/status', { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(); return response.json() as Promise<VoiceStatus>; })
      .then(value => setStatus(value))
      .catch(() => { if (!controller.signal.aborted) setStatus({ available: false, max_seconds: 90, message: 'Sprachfunktion noch nicht erreichbar. Bitte die Lernseite neu starten.' }); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    alive.current = true;
    setNotice('');
    return () => { alive.current = false; cancel(); stopSpeaking(); };
  }, []);

  useEffect(() => { cancel(); stopSpeaking(); setNotice(''); }, [scopeKey]);

  const toggleRecording = async () => {
    if (state.current === 'recording') {
      if (recorder.current?.state === 'recording') recorder.current.stop();
      return;
    }
    if (state.current !== 'idle' || !status?.available || !supported) return;
    const token = ++generation.current;
    stopSpeaking(); setNotice(''); setSeconds(0); changeState('requesting');
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
      if (!alive.current || token !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm']
        .find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error('Dieser Browser unterstützt kein passendes Aufnahmeformat. Bitte Chrome oder Safari verwenden.');
      const recording = new MediaRecorder(media, { mimeType });
      recorder.current = recording;
      const chunks: Blob[] = [];
      let size = 0;
      recording.ondataavailable = event => {
        if (event.data.size) { chunks.push(event.data); size += event.data.size; }
        if (size > MAX_BYTES && token === generation.current) { cancel(); setNotice('Die Aufnahme ist zu groß. Bitte kürzer sprechen.'); }
      };
      recording.onerror = () => { if (token === generation.current) { cancel(); setNotice('Die Aufnahme wurde unterbrochen. Bitte erneut versuchen.'); } };
      recording.onstop = async () => {
        if (token !== generation.current || !alive.current) return;
        stopTracks(); recorder.current = null;
        if (!size) { changeState('idle'); setNotice('Die Aufnahme war leer. Bitte erneut versuchen.'); return; }
        changeState('transcribing');
        const controller = new AbortController(); request.current = controller;
        const timeout = window.setTimeout(() => controller.abort(), 125000);
        try {
          const response = await fetch('/api/tutor/voice/transcribe', { method: 'POST',
            headers: { 'Content-Type': recording.mimeType }, body: new Blob(chunks, { type: recording.mimeType }), signal: controller.signal });
          if (!response.ok) throw new Error(await responseError(response));
          const result = await response.json();
          if (!alive.current || token !== generation.current) return;
          if (typeof result.text !== 'string' || !result.text.trim()) throw new Error('Keine Sprache erkannt. Bitte erneut sprechen.');
          callback.current(result.text.trim());
          setNotice('Frage eingefügt. Prüfe den Text und drücke auf Senden.');
        } catch (error) {
          if (alive.current && token === generation.current) setNotice(controller.signal.aborted
            ? 'Die Spracherkennung hat zu lange gedauert. Bitte erneut versuchen.'
            : error instanceof Error ? error.message : 'Die Aufnahme konnte nicht verarbeitet werden.');
        } finally {
          window.clearTimeout(timeout);
          if (token === generation.current) { request.current = null; changeState('idle'); }
        }
      };
      recording.start(250); changeState('recording');
      const start = performance.now();
      timer.current = window.setInterval(() => {
        const elapsed = Math.floor((performance.now() - start) / 1000);
        setSeconds(elapsed);
        if (elapsed >= maxSeconds && recording.state === 'recording') recording.stop();
      }, 250);
    } catch (error) {
      if (token !== generation.current || !alive.current) return;
      stopTracks(); changeState('idle');
      const name = error instanceof Error ? error.name : '';
      setNotice(name === 'NotAllowedError' ? 'Mikrofonzugriff nicht erlaubt. Bitte das Mikrofon in den Browser-Einstellungen für diese Lernseite freigeben.'
        : name === 'NotFoundError' ? 'Kein Mikrofon gefunden. Bitte ein Mikrofon anschließen.'
        : name === 'NotReadableError' ? 'Das Mikrofon ist gerade nicht verfügbar. Bitte andere Aufnahmen beenden.'
        : error instanceof Error ? error.message : 'Das Mikrofon konnte nicht gestartet werden.');
    }
  };

  const speak = async (text: string) => {
    if (!status?.available || state.current !== 'idle') return;
    stopSpeaking(); setNotice(''); setSpeechLoading(true);
    const token = speechGeneration.current;
    const controller = new AbortController(); speechRequest.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 125000);
    try {
      const response = await fetch('/api/tutor/voice/speak', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal: controller.signal });
      if (!response.ok) throw new Error(await responseError(response));
      const blob = await response.blob();
      if (!alive.current || token !== speechGeneration.current) return;
      currentUrl.current = URL.createObjectURL(blob); setAudioUrl(currentUrl.current);
    } catch (error) {
      if (alive.current && token === speechGeneration.current) setNotice(controller.signal.aborted
        ? 'Die Sprachausgabe hat zu lange gedauert. Bitte erneut versuchen.'
        : error instanceof Error ? error.message : 'Vorlesen ist gerade nicht möglich.');
    } finally {
      window.clearTimeout(timeout);
      if (alive.current && token === speechGeneration.current) setSpeechLoading(false);
    }
  };

  useEffect(() => {
    if (!audioUrl || !audioElement.current) return;
    const url = audioUrl;
    void audioElement.current.play().catch(() => {
      if (alive.current && currentUrl.current === url) setNotice('Die Antwort ist bereit. Zum Anhören auf ▶ drücken.');
    });
  }, [audioUrl]);

  const hint = !supported ? 'Dieser Browser unterstützt keine Mikrofonaufnahme. Bitte Chrome oder Safari verwenden.'
    : status && !status.available ? status.message : '';
  return { available: !!status?.available && supported, speechAvailable: !!status?.available,
    busy: capture !== 'idle', capture, seconds, maxSeconds, hint, notice, readReplies, setReadReplies,
    toggleRecording, cancel, speak, stopSpeaking, speechLoading, audioUrl, audioElement };
}

export function VoiceIcon({ recording = false, speaker = false }: { recording?: boolean; speaker?: boolean }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {recording ? <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
      : speaker ? <><path d="M11 5 6 9H3v6h3l5 4V5Z" /><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" /></>
      : <><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" /></>}
  </svg>;
}
