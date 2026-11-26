import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../lib/apiClient';

type Summary = {
  enabled: boolean;
  window_days: number;
  scored_answers: number;
  low_score_answers: number;
  average_score: number | null;
  trend: Array<{ day: string; average: number; answers: number }>;
  top_flags: Array<{ flag: string; count: number }>;
  judged_answers: number;
  judge_failures: number;
  corrections_stored: number;
  judge: {
    model: string;
    sample_percent: number;
    max_judged_per_day: number;
    neuron_budget_per_key: number;
    neurons_used_today: Record<string, number>;
  };
};

type Failure = {
  trace_id: string;
  created_at: string | null;
  prompt: string;
  answer: string | null;
  deterministic_score: number | null;
  issues: string[];
  notes?: string | null;
  correction?: { headline: string; bullets: string[] } | null;
  correction_rejected?: string | null;
  lesson?: { text: string; status: 'pending' | 'approved' | 'rejected' } | null;
};

/** Admin view of automatic answer scoring, judged failures, corrections and lessons. */
export function AiAnswerQualityPanel() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, f] = await Promise.all([
        apiFetch<Summary>('/api/ai/quality/summary'),
        apiFetch<{ failures: Failure[] }>('/api/ai/quality/failures'),
      ]);
      setSummary(s);
      setFailures(f.failures ?? []);
      setError(null);
    } catch {
      setError('Could not load answer quality.');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const setLesson = async (traceId: string, status: 'approved' | 'rejected') => {
    setBusy(traceId);
    try {
      await apiFetch(`/api/ai/quality/lessons/${traceId}`, { method: 'POST', body: JSON.stringify({ status }) });
      await load();
    } catch {
      setError('Could not update the lesson.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-label="Answer quality" style={{ marginTop: 24 }}>
      <h2>Answer quality</h2>
      {error && <p role="alert">{error}</p>}
      {summary && !summary.enabled && (
        <p>The quality loop is off. Set PMS_AI_QUALITY_LOOP_ENABLED to turn on scoring and review.</p>
      )}
      {summary && (
        <>
          <p>
            Average score {summary.average_score ?? 'n/a'} over {summary.scored_answers} scored answers in the last{' '}
            {summary.window_days} days. {summary.low_score_answers} scored low.
          </p>
          <p>
            Judged {summary.judged_answers}, failed {summary.judge_failures}, corrections stored {summary.corrections_stored}.
            Judge {summary.judge.model}, sample {summary.judge.sample_percent}%, up to {summary.judge.max_judged_per_day} per day.
          </p>
          <p>
            Free allowance used today (budget {summary.judge.neuron_budget_per_key} neurons per key):{' '}
            {Object.entries(summary.judge.neurons_used_today).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}
          </p>
          {summary.top_flags.length > 0 && (
            <p>Top flags: {summary.top_flags.map(f => `${f.flag} (${f.count})`).join(', ')}</p>
          )}
          {summary.trend.length > 0 && (
            <table>
              <thead><tr><th>Day</th><th>Average score</th><th>Answers</th></tr></thead>
              <tbody>
                {summary.trend.map(t => (
                  <tr key={t.day}><td>{t.day}</td><td>{t.average}</td><td>{t.answers}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      <h3>Judged failures</h3>
      {failures.length === 0 && <p>No judged failures yet.</p>}
      {failures.map(f => (
        <article key={f.trace_id} style={{ marginBottom: 16 }}>
          <p><strong>Question:</strong> {f.prompt}</p>
          <p><strong>Answer:</strong> {f.answer} (score {f.deterministic_score ?? 'n/a'})</p>
          <p><strong>Issues:</strong> {f.issues.join(', ') || 'none listed'} {f.notes ? `. ${f.notes}` : ''}</p>
          {f.correction && <p><strong>Corrected:</strong> {f.correction.headline}</p>}
          {f.correction_rejected && <p>Correction rejected: {f.correction_rejected}</p>}
          {f.lesson && (
            <p>
              <strong>Lesson ({f.lesson.status}):</strong> {f.lesson.text}{' '}
              <button type="button" disabled={busy === f.trace_id || f.lesson.status === 'approved'} onClick={() => void setLesson(f.trace_id, 'approved')}>Approve</button>{' '}
              <button type="button" disabled={busy === f.trace_id || f.lesson.status === 'rejected'} onClick={() => void setLesson(f.trace_id, 'rejected')}>Reject</button>
            </p>
          )}
        </article>
      ))}
    </section>
  );
}
