/** Agent 360° self-service scorecard. Zero-LLM deterministic data, shown first-person. */

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ArrowDownRight, ArrowUpRight, Loader2, RefreshCw, Target, TrendingUp, Users } from 'lucide-react';
import { apiFetch } from '../../../lib/apiClient';
import type { Agent360Profile } from '../../../types';

interface Agent360ScorecardProps {
  onAskAboutKpi?: (kpiName: string) => void;
  compact?: boolean;
}

const GRADE_STYLE: Record<string, string> = {
  A: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20',
  B: 'bg-blue-500/10 text-blue-700 border-blue-500/20',
  C: 'bg-amber-500/10 text-amber-700 border-amber-500/20',
  D: 'bg-orange-500/10 text-orange-700 border-orange-500/20',
  E: 'bg-rose-500/10 text-rose-700 border-rose-500/20',
};

export function Agent360Scorecard({ onAskAboutKpi, compact = false }: Agent360ScorecardProps) {
  const [profile, setProfile] = useState<Agent360Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<Agent360Profile & { detail?: string }>('/api/ai/agent-360');
      // Backend returns the profile object directly; HTTP errors are thrown by apiFetch.
      if (!res || !res.employee_code) {
        setError(' Unable to load your 360° scorecard.');
      } else {
        setProfile(res);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : ' Unable to load your 360° scorecard.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500">
        <Loader2 size={16} className="animate-spin" /> Loading your 360° scorecard…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200/70 bg-rose-50/40 p-5">
        <div className="flex items-start gap-2 text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold">{error}</p>
            <p className="mt-1 text-xs text-rose-600/80">
              Your account may not be linked to an employee profile yet. Contact your manager.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-bold text-rose-700 hover:border-rose-400"
        >
          <RefreshCw size={12} /> Retry
        </button>
      </div>
    );
  }

  if (!profile) return null;

  const score = profile.overall_score;
  const grade = profile.overall_grade || (score !== null ? gradeOf(score) : null);
  const trend = profile.score_trend || [];
  const lastScore = trend.length >= 2 ? trend[trend.length - 1]?.score : null;
  const prevScore = trend.length >= 2 ? trend[trend.length - 2]?.score : null;
  const delta = lastScore !== null && prevScore !== null ? lastScore - prevScore : null;

  return (
    <section className={`space-y-4 ${compact ? '' : 'max-w-3xl'}`} data-testid="agent-360-scorecard">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-slate-400">My 360° Scorecard</p>
            <h2 className="mt-1 text-lg font-bold text-slate-900">Your performance at a glance</h2>
            <p className="mt-0.5 text-xs text-slate-500">{profile.current_period || 'Latest period'} · {profile.performance_classification}</p>
          </div>
          {grade && (
            <span className={`inline-flex h-12 w-12 items-center justify-center rounded-xl border text-lg font-extrabold ${GRADE_STYLE[grade] || GRADE_STYLE.C}`}>
              {grade}
            </span>
          )}
        </div>

        <div className="mt-4 flex items-end gap-3">
          <span className="text-4xl font-black text-slate-900">{score !== null ? `${score.toFixed(1)}%` : '—'}</span>
          {delta !== null && (
            <span className={`mb-1.5 inline-flex items-center gap-0.5 text-sm font-bold ${delta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
              {delta >= 0 ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
              {Math.abs(delta).toFixed(1)} pts
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MiniStat label="Trend" value={trend.length ? `${trend.length} mo` : '—'} Icon={TrendingUp} />
          <MiniStat label="KPIs" value={String(profile.kpi_scores?.length || 0)} Icon={Target} />
          <MiniStat label="Open actions" value={String(profile.active_corrective_actions || 0)} Icon={AlertCircle} />
          <MiniStat label="Peers" value={profile.cohort ? `${profile.cohort.cohort_size}` : '—'} Icon={Users} />
        </div>
      </div>

      {profile.kpi_scores && profile.kpi_scores.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">Your KPI breakdown</h3>
          <ul className="mt-3 space-y-2.5">
            {profile.kpi_scores.slice(0, 8).map((kpi, i) => (
              <li key={`${kpi.name}-${i}`} className="flex items-center justify-between gap-3">
                <span className="truncate text-sm text-slate-700">{kpi.name}</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900">{kpi.score !== null ? `${kpi.score.toFixed(1)}%` : '—'}</span>
                  {onAskAboutKpi && (
                    <button
                      type="button"
                      onClick={() => onAskAboutKpi(kpi.name)}
                      className="text-xs font-semibold text-blue-600 hover:underline"
                    >
                      Ask AI
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {profile.cohort && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">How you compare</h3>
          <p className="mt-1 text-xs text-slate-500">Among peers in the same role and branch</p>
          <div className="mt-3 flex items-center gap-3">
            <span className="rounded-full bg-blue-500/10 px-3 py-1 text-sm font-bold text-blue-700">
              {profile.cohort.percentile_band}
            </span>
            <span className="text-xs text-slate-500">Peer average {profile.cohort.cohort_avg_score.toFixed(1)}%</span>
          </div>
        </div>
      )}
    </section>
  );
}

function MiniStat({ label, value, Icon }: { label: string; value: string; Icon: typeof Target }) {
  return (
    <div className="rounded-xl border border-slate-200/70 bg-slate-50/60 px-3 py-2">
      <div className="flex items-center gap-1 text-slate-400"><Icon size={12} /><span className="text-[10px] font-bold uppercase">{label}</span></div>
      <p className="mt-0.5 text-sm font-bold text-slate-800">{value}</p>
    </div>
  );
}

function gradeOf(score: number): string {
  if (score >= 95) return 'A';
  if (score >= 90) return 'B';
  if (score >= 80) return 'C';
  if (score >= 70) return 'D';
  return 'E';
}
