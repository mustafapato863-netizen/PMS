/** Agent 360° self-service scorecard. Zero-LLM deterministic data, shown first-person. */

import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingUp,
  Users,
} from 'lucide-react';
import { apiFetch } from '../../../lib/apiClient';
import type { Agent360Profile, Agent360WhatIfResult } from '../../../types';

interface DirectoryEntry {
  employee_code: string;
  employee_name: string;
  team: string;
  position: string;
}

interface Agent360ScorecardProps {
  employeeCode?: string;
  canSwitchEmployee?: boolean;
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

const ONBOARDING_DISMISSED_KEY = 'pms_ai_agent360_welcome_dismissed';

export function Agent360Scorecard({
  employeeCode,
  canSwitchEmployee = false,
  onAskAboutKpi,
  compact = false,
}: Agent360ScorecardProps) {
  const [selectedEmployeeCode, setSelectedEmployeeCode] = useState<string>(employeeCode ?? '');
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [profile, setProfile] = useState<Agent360Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState<boolean>(() => {
    if (canSwitchEmployee || compact) return false;
    try {
      return window.localStorage.getItem(ONBOARDING_DISMISSED_KEY) !== '1';
    } catch {
      return false;
    }
  });

  const dismissOnboarding = useCallback(() => {
    setShowOnboarding(false);
    try {
      window.localStorage.setItem(ONBOARDING_DISMISSED_KEY, '1');
    } catch {
      // Ignore storage errors in private browsing modes
    }
  }, []);

  // What-If interactive simulator state
  const [selectedKpi, setSelectedKpi] = useState<string>('');
  const [improvementStep, setImprovementStep] = useState<number>(5);
  const [simResult, setSimResult] = useState<Agent360WhatIfResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  useEffect(() => {
    if (!canSwitchEmployee) return;
    let active = true;
    apiFetch<{ employees: DirectoryEntry[] }>('/api/ai/agent-360/directory')
      .then((res) => {
        if (active && Array.isArray(res?.employees)) {
          setDirectory(res.employees);
        }
      })
      .catch(() => {
        if (active) setDirectory([]);
      });
    return () => {
      active = false;
    };
  }, [canSwitchEmployee]);

  const activeEmployeeCode = selectedEmployeeCode.trim();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSimResult(null);
    try {
      const qs = activeEmployeeCode ? `?employee_code=${encodeURIComponent(activeEmployeeCode)}` : '';
      const res = await apiFetch<Agent360Profile & { detail?: string }>(`/api/ai/agent-360${qs}`);
      if (!res || !res.employee_code) {
        setError('Unable to load your 360° scorecard.');
      } else {
        setProfile(res);
        const firstSimulatable = (res.kpi_scores || []).find(
          (k) => k.target !== null && k.target > 0 && k.weight !== null && k.weight > 0,
        );
        if (firstSimulatable) {
          setSelectedKpi(firstSimulatable.name);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load your 360° scorecard.');
    } finally {
      setLoading(false);
    }
  }, [activeEmployeeCode]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const runSimulation = useCallback(async () => {
    if (!selectedKpi) return;
    setSimLoading(true);
    setSimError(null);
    try {
      const res = await apiFetch<Agent360WhatIfResult>('/api/ai/agent-360/what-if', {
        method: 'POST',
        body: JSON.stringify({
          kpi_name: selectedKpi,
          improvement_pct: improvementStep,
          ...(activeEmployeeCode ? { employee_code: activeEmployeeCode } : {}),
        }),
      });
      setSimResult(res);
    } catch (e) {
      setSimError(e instanceof Error ? e.message : 'Unable to simulate this KPI right now.');
    } finally {
      setSimLoading(false);
    }
  }, [activeEmployeeCode, improvementStep, selectedKpi]);

  if (loading) {
    return (
      <div
        className={`space-y-4 ${compact ? '' : 'max-w-3xl'}`}
        role="status"
        aria-label="Loading your 360° scorecard"
      >
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <div className="h-3 w-28 animate-pulse rounded bg-slate-200" />
              <div className="h-5 w-52 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-36 animate-pulse rounded bg-slate-100" />
            </div>
            <div className="h-12 w-12 animate-pulse rounded-xl bg-slate-200" />
          </div>
          <div className="mt-4 h-9 w-28 animate-pulse rounded bg-slate-200" />
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((idx) => (
              <div key={idx} className="h-14 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        </div>
        <div className="h-36 animate-pulse rounded-2xl border border-slate-200 bg-white p-5" />
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
  const simulatableKpis = (profile.kpi_scores || []).filter(
    (k) => k.target !== null && k.target > 0 && k.weight !== null && k.weight > 0,
  );

  return (
    <section className={`space-y-4 ${compact ? '' : 'max-w-3xl'}`} data-testid="agent-360-scorecard">
      {/* First-Time Self-Service Agent Onboarding Walkthrough (Spec Phase 3.4) */}
      {showOnboarding && !canSwitchEmployee && (
        <div
          data-testid="agent-360-onboarding"
          className="flex flex-col gap-2 rounded-2xl border border-blue-200/80 bg-blue-50/60 p-4 text-xs text-slate-700 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="space-y-1">
            <p className="font-bold text-slate-900">Welcome to your 360° AI Coach</p>
            <p className="leading-relaxed text-slate-600">
              Review your monthly score and KPIs, test targets in the What-If simulator, or click <strong>Ask AI</strong> on any metric. Your chats and Memory preferences are private to you.
            </p>
          </div>
          <button
            type="button"
            onClick={dismissOnboarding}
            className="shrink-0 self-start rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800 sm:self-center"
          >
            Got it
          </button>
        </div>
      )}

      {/* Manager / Admin Direct-Report Switcher */}
      {canSwitchEmployee && directory.length > 0 && (
        <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <label htmlFor="agent-360-employee-picker" className="text-xs font-bold text-slate-700">
            Inspect employee 360°
          </label>
          <select
            id="agent-360-employee-picker"
            aria-label="Inspect employee 360°"
            value={selectedEmployeeCode}
            onChange={(e) => setSelectedEmployeeCode(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 sm:w-72"
          >
            <option value="">My own profile</option>
            {directory.map((emp) => (
              <option key={emp.employee_code} value={emp.employee_code}>
                {emp.employee_name} ({emp.employee_code}){emp.team ? ` · ${emp.team}` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Summary Header Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
              {activeEmployeeCode ? `${profile.employee_name} · 360° Scorecard` : 'My 360° Scorecard'}
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-900">
              {activeEmployeeCode ? `${profile.employee_name}'s performance at a glance` : 'Your performance at a glance'}
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {profile.current_period || 'Latest period'} · {profile.performance_classification}
            </p>
          </div>
          {grade && (
            <span
              className={`inline-flex h-12 w-12 items-center justify-center rounded-xl border text-lg font-extrabold ${
                GRADE_STYLE[grade] || GRADE_STYLE.C
              }`}
            >
              {grade}
            </span>
          )}
        </div>

        <div className="mt-4 flex items-end gap-3">
          <span className="text-4xl font-black text-slate-900">{score !== null ? `${score.toFixed(1)}%` : '—'}</span>
          {delta !== null && (
            <span
              className={`mb-1.5 inline-flex items-center gap-0.5 text-sm font-bold ${
                delta >= 0 ? 'text-emerald-600' : 'text-rose-600'
              }`}
            >
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

      {/* 6-Month Score Trend */}
      {trend.length >= 2 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-800">6-month score trend</h3>
            <span className="text-xs text-slate-500">{profile.performance_classification}</span>
          </div>
          <div className="mt-4 grid grid-cols-6 gap-2" aria-label="Monthly score progression">
            {trend.map((pt, idx) => {
              const val = pt.score ?? 0;
              const pct = Math.max(8, Math.min(100, Math.round(val)));
              return (
                <div key={`${pt.year}-${pt.month}-${idx}`} className="flex flex-col items-center gap-1">
                  <span className="text-xs font-bold tabular-nums text-slate-700">
                    {pt.score !== null ? `${pt.score.toFixed(0)}%` : '—'}
                  </span>
                  <div className="flex h-20 w-full items-end rounded-lg bg-slate-100 p-1">
                    <div
                      className="w-full rounded-md bg-blue-500/80 transition-all duration-200"
                      style={{ height: `${pct}%` }}
                    />
                  </div>
                  <span className="truncate text-xs text-slate-500">{pt.month.slice(0, 3)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* KPI Breakdown */}
      {profile.kpi_scores && profile.kpi_scores.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-bold text-slate-800">Your KPI breakdown</h3>
            {profile.top_opportunity && (
              <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
                Focus: {profile.top_opportunity}
              </span>
            )}
          </div>
          <ul className="mt-3 space-y-3">
            {profile.kpi_scores.slice(0, 8).map((kpi, i) => {
              const pct = kpi.score !== null ? Math.max(0, Math.min(100, kpi.score)) : 0;
              return (
                <li key={`${kpi.name}-${i}`} className="space-y-1">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <span className="truncate text-sm font-medium text-slate-700">{kpi.name}</span>
                      {kpi.weight !== null && kpi.weight > 0 && (
                        <span className="ml-2 text-xs text-slate-400">
                          Weight {(kpi.weight * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold tabular-nums text-slate-900">
                        {kpi.score !== null ? `${kpi.score.toFixed(1)}%` : '—'}
                      </span>
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
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full transition-all duration-200 ${
                        pct >= 90 ? 'bg-emerald-500' : pct >= 80 ? 'bg-blue-500' : 'bg-amber-500'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Interactive What-If Simulator */}
      {simulatableKpis.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="what-if-simulator">
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={15} className="text-blue-600" />
            <h3 className="text-sm font-bold text-slate-800">What-If score simulator</h3>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Test how improving one KPI affects your overall score and grade (respects achievement caps).
          </p>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="text-xs font-semibold text-slate-600">
              KPI
              <select
                value={selectedKpi}
                onChange={(e) => {
                  setSelectedKpi(e.target.value);
                  setSimResult(null);
                }}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-normal text-slate-800"
              >
                {simulatableKpis.map((k) => (
                  <option key={k.name} value={k.name}>
                    {k.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold text-slate-600">
              Improvement (+{improvementStep})
              <input
                type="range"
                min={1}
                max={25}
                step={1}
                value={improvementStep}
                onChange={(e) => setImprovementStep(Number(e.target.value))}
                className="mt-2.5 w-full accent-blue-600"
              />
            </label>
            <div className="flex items-end">
              <button
                type="button"
                disabled={simLoading || !selectedKpi}
                onClick={() => void runSimulation()}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                <Sparkles size={13} />
                {simLoading ? 'Calculating…' : 'Simulate impact'}
              </button>
            </div>
          </div>

          {simError && <p className="mt-2 text-xs text-rose-600">{simError}</p>}

          {simResult && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-blue-200/70 bg-blue-50/50 px-3.5 py-2.5 text-xs">
              <div>
                <span className="font-semibold text-slate-700">Projected score: </span>
                <span className="text-sm font-black text-blue-700">{simResult.projected_score.toFixed(1)}%</span>
                <span className="ml-1.5 font-bold text-emerald-700">
                  ({simResult.score_delta >= 0 ? '+' : ''}
                  {simResult.score_delta.toFixed(1)} pts)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-white px-2 py-0.5 font-bold text-slate-700">
                  Grade {simResult.current_grade} → {simResult.projected_grade}
                </span>
                {simResult.capped && (
                  <span className="rounded-md bg-amber-100 px-2 py-0.5 font-semibold text-amber-800">
                    100% cap applied
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Privacy-Safe Cohort Benchmarking */}
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
      <div className="flex items-center gap-1 text-slate-400">
        <Icon size={12} />
        <span className="text-xs font-bold uppercase">{label}</span>
      </div>
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
