import { useState } from 'react';
import { api, errorText } from './api';

type Review = { clean: boolean; review: string; findings: string[]; model: string; follow_up: string };

/** On-demand second look at one tutor answer by the local model; the correction is only prepared, never sent. */
export function AnswerReview({ question, answer, disabled, onFollowUp }: { question: string; answer: string; disabled: boolean; onFollowUp: (text: string) => void }) {
  const [loading, setLoading] = useState(false);
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState('');
  const run = async () => {
    setLoading(true); setError('');
    try { setReview(await api<Review>('/quality/review', { message: question, answer })); }
    catch (problem) { setError(errorText(problem)); }
    finally { setLoading(false); }
  };
  return <section className="tutor-review" aria-label="Qualitätsprüfung dieser Antwort">
    <button type="button" className="text-button" disabled={disabled || loading} onClick={() => void run()}>{loading ? 'Antwort wird geprüft …' : review ? 'Erneut prüfen' : 'Antwort prüfen'}</button>
    {loading && <p className="tutor-notice" role="status">Das lokale Modell vergleicht die Antwort mit den Lerndaten. Das dauert etwa so lange wie eine Antwort; der Lernchat wartet solange.</p>}
    {error && <p className="tutor-notice" role="alert">{error}</p>}
    {review && !loading && <div className="tutor-review-result" role="status">
      <strong>{review.clean && !review.findings.length ? 'Prüfung ohne Beanstandung' : 'Prüfung mit Hinweisen'}</strong>
      {review.findings.length > 0 && <ul>{review.findings.map(item => <li key={item}>{item}</li>)}</ul>}
      {!review.clean && <p className="preserve-lines">{review.review}</p>}
      <p className="tutor-notice">Geprüft von {review.model} anhand der Lerndaten dieser Antwort. Auch die Prüfung kann irren; maßgeblich bleibt die Belegstelle.</p>
      {review.follow_up && <button type="button" className="text-button" disabled={disabled} onClick={() => onFollowUp(review.follow_up)}>Korrektur als nächste Nachricht vorbereiten</button>}
    </div>}
  </section>;
}
