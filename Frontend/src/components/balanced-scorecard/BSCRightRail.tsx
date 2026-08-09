import React from "react";
import { pc } from "./types";
import GaugeSVG from "./GaugeSVG";
import { getGaugeTone } from "./gaugeTone";
import LineChart from "./LineChart";
import MultiPerspectiveChart from "./MultiPerspectiveChart";
import type { ManagerSnapshot } from "./managerSnapshots";

interface TrendPoint {
  month: string;
  year: number;
  score?: number | null;
  perspective_scores?: Record<string, number | null>;
  target?: number | null;
  target_value?: number | null;
  targetValue?: number | null;
  overall_target?: number | null;
  [key: string]: unknown;
}

interface PerspectiveSummary {
  key: string;
  label: string;
}

interface SelectedKpiRow {
  kpi_label?: string;
  target_value?: number | null;
  actual_value?: number | null;
  unit?: string;
  perspective?: string;
}

interface BSCRightRailProps {
  perspectives: PerspectiveSummary[];
  overallScore: number | null;
  selectedKpiRow: SelectedKpiRow | null;
  kpiHistory: TrendPoint[];
  overallHistory: TrendPoint[];
  subjectLabel?: string;
  overallTarget?: number | null;
  rosterManagers?: ManagerSnapshot[];
  activeManagerSnapshot?: ManagerSnapshot | null;
  view?: string;
  selectedMonth?: string;
}

function valueOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getDelta(current: number | null, previous: number | null) {
  return current != null && previous != null ? current - previous : null;
}

function getHistoryTarget(
  latest: TrendPoint | undefined,
  overallTarget?: number | null,
) {
  return (
    valueOrNull(latest?.overall_target) ??
    valueOrNull(latest?.target_value) ??
    valueOrNull(latest?.targetValue) ??
    valueOrNull(latest?.target) ??
    valueOrNull(overallTarget)
  );
}

function TrendBadge({
  delta,
  compact = false,
}: {
  delta: number | null;
  compact?: boolean;
}) {
  if (delta == null) return null;

  const direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  const color =
    direction === "up"
      ? "#1A8C53"
      : direction === "down"
        ? "#D03B3B"
        : "var(--bsc-panel-muted)";
  const background =
    direction === "up"
      ? "var(--bsc-excellent-bg)"
      : direction === "down"
        ? "var(--bsc-poor-bg)"
        : "var(--bsc-na-bg)";
  const prefix = delta > 0 ? "+" : delta < 0 ? "−" : "";

  return (
    <span
      title={`${prefix}${Math.abs(delta).toFixed(1)}% versus the previous available month`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: compact ? 3 : 4,
        padding: compact ? "2px 6px" : "3px 8px",
        borderRadius: 999,
        background,
        color,
        fontSize: compact ? 10 : 11,
        fontWeight: 850,
        whiteSpace: "nowrap",
        border: `1px solid color-mix(in srgb, ${color} 18%, transparent)`,
      }}
    >
      {prefix}
      {Math.abs(delta).toFixed(1)}%
    </span>
  );
}

function MicroStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: string;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 9.5,
          fontWeight: 800,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--bsc-panel-muted)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 12.5,
          fontWeight: 900,
          color: tone || "var(--bsc-panel-text)",
          marginTop: 2,
        }}
      >
        {value}
      </div>
    </div>
  );
}

export function BSCRightRail({
  perspectives,
  overallScore,
  overallHistory,
  subjectLabel,
  overallTarget,
  rosterManagers,
  view = "strategy_map",
  selectedMonth = "All",
}: BSCRightRailProps) {
  const latestHistory = overallHistory[overallHistory.length - 1];
  const previousHistory = overallHistory[overallHistory.length - 2];
  const isAllMonths = selectedMonth === "All";

  const score = overallScore ?? valueOrNull(latestHistory?.score);
  const scorePrevious = isAllMonths ? null : valueOrNull(previousHistory?.score);
  const scoreDelta = getDelta(score, scorePrevious);

  const scoreTarget = getHistoryTarget(latestHistory, overallTarget);
  const tone = getGaugeTone(score);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 w-full mb-2" aria-label="Executive Performance Summary">
      {/* ── CARD 1: Overall Performance & Gauge ── */}
      <section
        className="bsc-panel bsc-rail-glass-panel p-4 flex flex-col justify-between rounded-2xl border border-[var(--border-light)] h-full"
        aria-label={subjectLabel ? `${subjectLabel} overall performance score` : "Overall performance score"}
        style={{
          background: `
            radial-gradient(circle at 86% 18%, ${tone.glow} 0%, transparent 31%),
            linear-gradient(145deg, color-mix(in srgb, ${tone.color} 8%, var(--bsc-panel-bg-solid) 92%) 0%, color-mix(in srgb, var(--bsc-panel-bg) 97%, transparent) 100%)
          `,
          backdropFilter: "blur(18px)",
          WebkitBackdropFilter: "blur(18px)",
          borderColor: `color-mix(in srgb, ${tone.color} 18%, transparent)`,
          boxShadow: `0 0 0 1px color-mix(in srgb, ${tone.color} 7%, transparent), 0 10px 25px ${tone.glow}, var(--bsc-shadow-sm)`,
        }}
      >
        <div>
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--bsc-panel-muted)]">
              {subjectLabel ? `${subjectLabel} performance` : "Overall performance"}
            </span>
            {scoreDelta != null && <TrendBadge delta={scoreDelta} compact />}
          </div>

          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-3xl font-black tracking-tight leading-none" style={{ color: tone.color }}>
                {score != null ? `${score.toFixed(1)}%` : "N/A"}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <span
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-extrabold"
                  style={{
                    background: tone.background,
                    color: tone.color,
                    border: `1px solid color-mix(in srgb, ${tone.color} 17%, transparent)`,
                  }}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: tone.color, boxShadow: `0 0 6px ${tone.color}` }} />
                  {tone.label}
                </span>
              </div>
            </div>

            <div className="w-24 shrink-0 flex items-center justify-center">
              <GaugeSVG score={score} size={92} />
            </div>
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-[var(--border-light)] grid grid-cols-2 gap-2">
          <MicroStat label={isAllMonths ? "Average" : "Current"} value={score != null ? `${score.toFixed(1)}%` : "N/A"} tone={tone.color} />
          <MicroStat
            label={isAllMonths ? "Period" : scoreDelta != null ? "Monthly change" : "Data status"}
            value={isAllMonths ? "All months average" : scoreDelta != null ? <TrendBadge delta={scoreDelta} compact /> : "No comparison"}
          />
        </div>
      </section>

      {/* ── CARD 2: Score Trend Curve ── */}
      <section
        className="bsc-panel bsc-rail-glass-panel p-4 flex flex-col justify-between rounded-2xl border border-[var(--border-light)] h-full"
        aria-label="Overall score trend"
      >
        <div>
          <div className="flex items-start justify-between gap-2 mb-2">
            <div>
              <h3 className="text-xs font-black text-[var(--bsc-panel-text)] tracking-tight">Score trend</h3>
              <p className="text-[10px] font-semibold text-[var(--bsc-panel-muted)] mt-0.5">
                Monthly movement in overall performance
              </p>
            </div>
            {scoreDelta != null && <TrendBadge delta={scoreDelta} compact />}
          </div>

          <div className="h-28 w-full mt-1">
            <LineChart
              history={overallHistory}
              color={tone.color}
              height={100}
            />
          </div>
        </div>

        <div className="mt-2 pt-2 border-t border-[var(--border-light)] flex items-center justify-between text-[10px]">
          <span className="font-semibold text-[var(--bsc-panel-muted)]">Target Baseline</span>
          <span className="font-extrabold text-[var(--text-primary)]">{scoreTarget != null ? `${scoreTarget.toFixed(1)}%` : '90.0%'}</span>
        </div>
      </section>

      {/* ── CARD 3: Perspective Trends / Manager Comparison ── */}
      <section
        className="bsc-panel bsc-rail-glass-panel p-4 flex flex-col justify-between rounded-2xl border border-[var(--border-light)] h-full md:col-span-2 xl:col-span-1"
        aria-label="Perspective trends"
      >
        {view === 'strategy_map' ? (
          <div>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <h3 className="text-xs font-black text-[var(--bsc-panel-text)] tracking-tight">Perspective trends</h3>
                <p className="text-[10px] font-semibold text-[var(--bsc-panel-muted)] mt-0.5">
                  Latest movement across 4 perspectives
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 mb-2 flex-wrap text-[9px] font-semibold">
              {perspectives.map((perspective) => (
                <div key={perspective.key} className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full" style={{ background: pc(perspective.key) }} />
                  <span className="text-[var(--text-muted)]">{perspective.label.split(" ")[0]}</span>
                </div>
              ))}
            </div>

            <div className="h-28 w-full mt-1 flex items-center">
              <MultiPerspectiveChart
                history={overallHistory}
                perspectives={perspectives}
                height={95}
                hideSummary
              />
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <h3 className="text-xs font-black text-[var(--bsc-panel-text)] tracking-tight">Manager comparison</h3>
                <p className="text-[10px] font-semibold text-[var(--bsc-panel-muted)] mt-0.5">
                  Top performing team leaders
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              {(rosterManagers || []).slice(0, 3).map((m, idx) => (
                <div key={m.employeeId} className="flex items-center justify-between text-[11px] p-1.5 rounded-lg bg-[var(--bg-sunken)]/60">
                  <span className="font-bold text-[var(--text-primary)] truncate max-w-[140px]">{idx + 1}. {m.employeeName}</span>
                  <span className="font-extrabold text-blue-600 dark:text-blue-400">{(m.score ?? 0).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-2 pt-2 border-t border-[var(--border-light)] flex items-center justify-between text-[10px]">
          <span className="font-semibold text-[var(--bsc-panel-muted)]">Data Status</span>
          <span className="inline-flex items-center gap-1.5 font-extrabold text-emerald-600 dark:text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            Live Measured
          </span>
        </div>
      </section>
    </div>
  );
}

export default BSCRightRail;
