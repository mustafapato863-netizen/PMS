import { useEffect, useMemo, useState } from 'react';
import { Check, CheckCheck, Minus, Plus, RotateCcw, SlidersHorizontal } from 'lucide-react';
import { getGradeTone } from '../../../constants/grades';

export type ComplianceFunction = {
  slug: string;
  functionName: string;
  score?: number;
  teamsCount?: number;
  headcount?: number;
  teamsList?: string;
};

export type ComplianceUnitItem = {
  slug: string;
  name: string;
  score: number;
  kind: 'team' | 'role';
  hasIssue?: boolean;
};

export type ComplianceTimelineFunction = {
  slug: string;
  functionName: string;
  score: number;
  subKindLabel: 'Teams' | 'Roles';
  subItems: ComplianceUnitItem[];
  allUnits?: ComplianceUnitItem[];
};

type StoredCount = {
  done: number;
  total: number;
  pendingSlugs?: string[];
};

type ComplianceRow = {
  id: string;
  name: string;
  done: number;
  total: number;
  defaultDone: number;
  defaultTotal: number;
  unitLabel: 'Teams' | 'Roles';
  units: ComplianceUnitItem[];
  pendingSlugs: string[];
};

function storageKey(region: string, periodKey: string): string {
  return `pms-monthly-pad:${region}:${periodKey}:compliance`;
}

function clampCount(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.min(99999, Math.round(parsed));
}

export function compliancePercent(done: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((done / total) * 100);
}

function readCounts(region: string, periodKey: string): Record<string, StoredCount> {
  try {
    const raw = localStorage.getItem(storageKey(region, periodKey));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    const entries: Array<[string, StoredCount]> = [];
    if (Array.isArray(parsed)) {
      for (const item of parsed) {
        if (!item || typeof item !== 'object') continue;
        const row = item as { id?: unknown; done?: unknown; total?: unknown; pendingSlugs?: unknown };
        if (typeof row.id !== 'string' || !row.id.trim()) continue;
        const done = clampCount(row.done);
        const total = clampCount(row.total);
        if (done === 0 && total === 0) continue;
        entries.push([
          row.id,
          {
            done,
            total,
            pendingSlugs: Array.isArray(row.pendingSlugs)
              ? row.pendingSlugs.filter((s): s is string => typeof s === 'string')
              : undefined,
          },
        ]);
      }
    } else if (parsed && typeof parsed === 'object') {
      for (const [id, value] of Object.entries(parsed)) {
        if (!value || typeof value !== 'object') continue;
        const row = value as { done?: unknown; total?: unknown; pendingSlugs?: unknown };
        const done = clampCount(row.done);
        const total = clampCount(row.total);
        if (done === 0 && total === 0) continue;
        entries.push([
          id,
          {
            done,
            total,
            pendingSlugs: Array.isArray(row.pendingSlugs)
              ? row.pendingSlugs.filter((s): s is string => typeof s === 'string')
              : undefined,
          },
        ]);
      }
    }
    return Object.fromEntries(entries);
  } catch {
    return {};
  }
}

function writeCounts(region: string, periodKey: string, counts: Record<string, StoredCount>) {
  try {
    localStorage.setItem(storageKey(region, periodKey), JSON.stringify(counts));
  } catch {
    // The visit draft stays in memory when storage is blocked.
  }
}

function extractUnitsForFunction(
  fn: ComplianceFunction,
  timelineItem?: ComplianceTimelineFunction,
): { units: ComplianceUnitItem[]; unitLabel: 'Teams' | 'Roles'; defaultTotal: number; defaultDone: number } {
  const fromTimeline =
    timelineItem?.allUnits && timelineItem.allUnits.length > 0
      ? timelineItem.allUnits
      : timelineItem?.subItems && timelineItem.subItems.length > 0
        ? timelineItem.subItems
        : [];

  if (fromTimeline.length > 0) {
    const unitLabel = timelineItem?.subKindLabel ?? (fromTimeline[0]?.kind === 'team' ? 'Teams' : 'Roles');
    const defaultTotal = fromTimeline.length;
    const activeCount = fromTimeline.filter((u) => u.score > 0).length;
    const defaultDone = activeCount > 0 ? activeCount : defaultTotal;
    return { units: fromTimeline, unitLabel, defaultTotal, defaultDone };
  }

  const parsedNames = fn.teamsList
    ? fn.teamsList
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    : [];

  const isMultiTeam = (fn.teamsCount ?? parsedNames.length) > 1;
  const units: ComplianceUnitItem[] = parsedNames.map((name) => ({
    slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    name,
    score: fn.score ?? 100,
    kind: isMultiTeam ? 'team' : 'role',
  }));

  const fallbackTotal =
    units.length > 0 ? units.length : Math.max(1, fn.teamsCount || fn.headcount || 1);
  return {
    units,
    unitLabel: isMultiTeam ? 'Teams' : 'Roles',
    defaultTotal: fallbackTotal,
    defaultDone: fallbackTotal,
  };
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    Boolean(target.closest('input, textarea, select, button, [data-edit-control="true"]'))
  );
}

export function DataComplianceCard({
  region,
  periodKey,
  functions,
  timelineItems,
}: {
  region: string;
  periodKey: string;
  functions: ComplianceFunction[];
  timelineItems?: ComplianceTimelineFunction[];
}) {
  const padKey = `${region}:${periodKey}`;
  const [counts, setCounts] = useState<Record<string, StoredCount>>(() => readCounts(region, periodKey));
  const [loadedKey, setLoadedKey] = useState(padKey);
  const [editing, setEditing] = useState(false);

  if (loadedKey !== padKey) {
    setCounts(readCounts(region, periodKey));
    setLoadedKey(padKey);
    setEditing(false);
  }

  const timelineBySlug = useMemo(() => {
    const map = new Map<string, ComplianceTimelineFunction>();
    if (timelineItems) {
      for (const item of timelineItems) {
        map.set(item.slug, item);
      }
    }
    return map;
  }, [timelineItems]);

  const rows = useMemo<ComplianceRow[]>(() => {
    return functions.map((fn) => {
      const { units, unitLabel, defaultTotal, defaultDone } = extractUnitsForFunction(
        fn,
        timelineBySlug.get(fn.slug),
      );
      const stored = counts[fn.slug];
      const pendingSlugs = stored?.pendingSlugs ?? [];
      const total = stored ? stored.total : defaultTotal;
      const done = stored ? stored.done : defaultDone;

      return {
        id: fn.slug,
        name: fn.functionName,
        done,
        total,
        defaultDone,
        defaultTotal,
        unitLabel,
        units,
        pendingSlugs,
      };
    });
  }, [counts, functions, timelineBySlug]);

  const totals = useMemo(() => {
    let done = 0;
    let total = 0;
    for (const row of rows) {
      done += row.done;
      total += row.total;
    }
    const percent = compliancePercent(done, total);
    return { done, total, percent, tone: getGradeTone(total > 0 ? percent : null) };
  }, [rows]);

  useEffect(() => {
    if (!editing) return;
    const leaveEdit = (event: MouseEvent) => {
      if (isInteractiveTarget(event.target)) return;
      if (
        event.target instanceof Element &&
        event.target.closest('[data-testid="presentation-compliance-pad-close"]')
      ) {
        return;
      }
      setEditing(false);
    };
    document.addEventListener('click', leaveEdit);
    return () => document.removeEventListener('click', leaveEdit);
  }, [editing]);

  const updateRow = (
    row: ComplianceRow,
    patch: { done?: number; total?: number; pendingSlugs?: string[] },
  ) => {
    setCounts((current) => {
      const existing = current[row.id];
      const nextDone = clampCount(patch.done ?? existing?.done ?? row.done);
      const nextTotal = clampCount(patch.total ?? existing?.total ?? row.total);
      const nextPending = patch.pendingSlugs ?? existing?.pendingSlugs ?? row.pendingSlugs;
      const next: Record<string, StoredCount> = {
        ...current,
        [row.id]: {
          done: nextDone,
          total: nextTotal,
          pendingSlugs: nextPending,
        },
      };
      writeCounts(region, periodKey, next);
      return next;
    });
  };

  const toggleUnit = (row: ComplianceRow, unitSlug: string) => {
    const isPending = row.pendingSlugs.includes(unitSlug);
    const nextPending = isPending
      ? row.pendingSlugs.filter((slug) => slug !== unitSlug)
      : [...row.pendingSlugs, unitSlug];
    const unitTotal = row.units.length > 0 ? row.units.length : row.total;
    const nextDone = Math.max(0, unitTotal - nextPending.length);
    updateRow(row, {
      done: nextDone,
      total: unitTotal,
      pendingSlugs: nextPending,
    });
  };

  const handleMarkAllComplete = () => {
    setCounts((current) => {
      const next: Record<string, StoredCount> = { ...current };
      for (const row of rows) {
        const targetTotal = row.total > 0 ? row.total : row.defaultTotal;
        next[row.id] = {
          done: targetTotal,
          total: targetTotal,
          pendingSlugs: [],
        };
      }
      writeCounts(region, periodKey, next);
      return next;
    });
  };

  const handleSyncFromActual = () => {
    try {
      localStorage.removeItem(storageKey(region, periodKey));
    } catch {
      // Ignore storage removal errors
    }
    setCounts({});
  };

  return (
    <div className="bg-[var(--bg-surface)] text-[var(--text-primary)]">
      <style>{'@keyframes compliance-flip{from{transform:perspective(900px) rotateY(72deg);opacity:.4}to{transform:perspective(900px) rotateY(0);opacity:1}}'}</style>

      {/* Top Executive Summary & Quick Action Bar */}
      <div className="flex items-center justify-between gap-2 border-b border-[var(--border-light)] bg-[var(--bg-sunken)]/55 px-4 py-2.5">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold tabular-nums"
            style={{
              background: totals.tone.badgeBg,
              color: totals.tone.text,
              border: `1px solid ${totals.tone.border}`,
            }}
          >
            {totals.percent}%
          </span>
          <div className="min-w-0">
            <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">
              {totals.done}/{totals.total} Active Units Submitted
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {Object.keys(counts).length > 0 && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleSyncFromActual();
              }}
              title="Reset to actual extracted teams and roles"
              className="compact-control inline-flex !min-h-0 items-center gap-1 rounded-lg border border-[var(--border-light)] bg-[var(--bg-surface)] px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
            >
              <RotateCcw size={11} aria-hidden="true" />
              <span>Sync Actual</span>
            </button>
          )}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setEditing((prev) => !prev);
            }}
            className="compact-control inline-flex !min-h-0 items-center gap-1 rounded-lg border border-[var(--border-light)] bg-[var(--bg-surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-sunken)]"
          >
            {editing ? (
              <>
                <Check size={12} className="text-[var(--sgh-emerald-primary)]" aria-hidden="true" />
                <span>Done</span>
              </>
            ) : (
              <>
                <SlidersHorizontal size={12} className="text-[var(--sgh-cyan-primary)]" aria-hidden="true" />
                <span>Quick Edit</span>
              </>
            )}
          </button>
        </div>
      </div>

      {editing ? (
        <div
          data-testid="presentation-compliance-edit"
          onClick={(event) => {
            if (isInteractiveTarget(event.target)) return;
            setEditing(false);
          }}
          className="max-h-[min(68vh,30rem)] overflow-y-auto bg-[var(--bg-surface)] px-4 py-3 [animation:compliance-flip_180ms_ease-out]"
        >
          {/* Quick batch actions + clickable header to flip back */}
          <div className="mb-2 flex items-center justify-between gap-2 pb-1.5 border-b border-[var(--border-light)]">
            <span className="text-[11px] text-[var(--text-muted)]">
              Tap a team pill to toggle or adjust numbers
            </span>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleMarkAllComplete();
              }}
              className="compact-control inline-flex !min-h-0 items-center gap-1 rounded-md bg-[var(--bg-sunken)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              <CheckCheck size={12} aria-hidden="true" />
              <span>Mark All 100%</span>
            </button>
          </div>

          <div
            title="Click header to return to chart"
            className="grid cursor-pointer grid-cols-[minmax(0,1fr)_4.25rem_4.25rem] gap-2 px-0.5 pb-2 text-[10px] font-semibold tracking-wide text-[var(--text-muted)] uppercase select-none hover:text-[var(--text-primary)]"
          >
            <span>Department</span>
            <span className="text-right">Done</span>
            <span className="text-right">Total</span>
          </div>

          {rows.length === 0 ? (
            <p className="px-0.5 py-6 text-sm text-[var(--text-muted)]">No functions in this region.</p>
          ) : (
            <ul className="space-y-2">
              {rows.map((row) => {
                const percent = compliancePercent(row.done, row.total);
                const tone = getGradeTone(row.total > 0 ? percent : null);
                return (
                  <li
                    key={row.id}
                    className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/40 p-2.5 transition-colors"
                  >
                    <div className="grid grid-cols-[minmax(0,1fr)_4.25rem_4.25rem] items-center gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className="truncate text-xs font-semibold text-[var(--text-primary)]"
                            title={row.name}
                          >
                            {row.name}
                          </span>
                          <span
                            className="shrink-0 rounded px-1.5 py-0.2 text-[10px] font-bold tabular-nums"
                            style={{ background: tone.badgeBg, color: tone.text }}
                          >
                            {percent}%
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-1">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              updateRow(row, { done: Math.max(0, row.done - 1) });
                            }}
                            aria-label={`Decrease ${row.name} done`}
                            className="compact-control inline-flex size-5 !min-h-0 items-center justify-center rounded border border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]"
                          >
                            <Minus size={10} aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              updateRow(row, { done: Math.min(row.total, row.done + 1) });
                            }}
                            aria-label={`Increase ${row.name} done`}
                            className="compact-control inline-flex size-5 !min-h-0 items-center justify-center rounded border border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]"
                          >
                            <Plus size={10} aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              updateRow(row, { done: row.total, pendingSlugs: [] });
                            }}
                            className="compact-control inline-flex !min-h-0 items-center rounded border border-[var(--border-light)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                          >
                            All ({row.total})
                          </button>
                        </div>
                      </div>

                      <input
                        aria-label={`${row.name} done`}
                        data-testid={`compliance-done-${row.id}`}
                        type="number"
                        min={0}
                        inputMode="numeric"
                        value={row.done}
                        onChange={(event) =>
                          updateRow(row, { done: clampCount(event.target.value) })
                        }
                        className="compact-control h-8 rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-2 text-right text-sm font-semibold text-[var(--input-text)] tabular-nums outline-none focus:border-[var(--input-focus)]"
                      />
                      <input
                        aria-label={`${row.name} total`}
                        data-testid={`compliance-total-${row.id}`}
                        type="number"
                        min={0}
                        inputMode="numeric"
                        value={row.total}
                        onChange={(event) =>
                          updateRow(row, { total: clampCount(event.target.value) })
                        }
                        className="compact-control h-8 rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-2 text-right text-sm font-semibold text-[var(--input-text)] tabular-nums outline-none focus:border-[var(--input-focus)]"
                      />
                    </div>

                    {/* Extracted Actual Teams / Roles 1-Click Toggle Pills */}
                    {row.units.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1 border-t border-[var(--border-light)] pt-2">
                        {row.units.map((unit) => {
                          const isPending = row.pendingSlugs.includes(unit.slug);
                          return (
                            <button
                              key={unit.slug}
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                toggleUnit(row, unit.slug);
                              }}
                              className={`compact-control inline-flex !min-h-0 items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                                isPending
                                  ? 'border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-muted)] line-through opacity-75'
                                  : 'border-[var(--pms-grade-a-border)] bg-[var(--pms-grade-a-badge-bg)] text-[var(--pms-grade-a-text)]'
                              }`}
                            >
                              <span>{isPending ? '○' : '✓'}</span>
                              <span className="truncate max-w-[10rem]">{unit.name}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : (
        <button
          type="button"
          data-testid="presentation-compliance-chart"
          aria-label="Department Completion. Click to edit counts."
          onClick={(event) => {
            event.stopPropagation();
            setEditing(true);
          }}
          className="block w-full cursor-pointer bg-[var(--bg-surface)] px-4 py-3.5 text-left text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-sunken)]/25 [animation:compliance-flip_180ms_ease-out]"
        >
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-xs font-bold tracking-wide text-[var(--text-secondary)] uppercase">
              Department Completion
            </h3>
            <span className="text-[11px] text-[var(--text-muted)]">
              Click any row to customize
            </span>
          </div>
          {rows.length === 0 ? (
            <p className="mt-4 text-sm text-[var(--text-muted)]">No functions in this region.</p>
          ) : (
            <ul className="mt-3 space-y-2.5">
              {rows.map((row) => {
                const percent = compliancePercent(row.done, row.total);
                const tone = getGradeTone(row.total > 0 ? percent : null);
                return (
                  <li
                    key={row.id}
                    className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_auto] items-center gap-2.5 rounded-lg px-1.5 py-1 transition-colors hover:bg-[var(--bg-sunken)]/60"
                  >
                    <span
                      className="truncate text-xs font-semibold text-[var(--text-primary)]"
                      title={row.name}
                    >
                      {row.name}
                    </span>
                    <span className="h-2 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
                      <span
                        data-grade={tone.grade ?? 'na'}
                        className="block h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${row.total > 0 ? Math.min(100, percent) : 0}%`,
                          background: tone.gauge,
                        }}
                      />
                    </span>
                    <span className="flex items-baseline gap-2 text-[11px] tabular-nums">
                      <span className="font-medium text-[var(--text-muted)]">
                        {row.done}/{row.total}
                      </span>
                      <span
                        className="w-9 text-right font-bold"
                        style={{ color: tone.text }}
                      >
                        {percent}%
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </button>
      )}
    </div>
  );
}
