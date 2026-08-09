// Skeleton shimmer building blocks
import type { CSSProperties, ReactNode } from 'react';

const Shimmer = ({ className, style }: { className: string; style?: CSSProperties }) => (
  <div
    aria-hidden="true"
    style={{
      background: 'linear-gradient(100deg, var(--bg-sunken) 20%, var(--bg-elevated) 42%, var(--bg-sunken) 64%)',
      backgroundSize: '240% 100%',
      ...style,
    }}
    className={`animate-pulse rounded-xl ${className}`}
  />
);

type PageLoadingVariant = 'dashboard' | 'table' | 'detail' | 'form' | 'builder';

const SkeletonPanel = ({ className = '', children }: { className?: string; children: ReactNode }) => (
  <div className={`rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm ${className}`}>{children}</div>
);

export const PageLoadingSkeleton = ({
  variant = 'dashboard',
  label = 'Loading workspace',
  compact = false,
}: {
  variant?: PageLoadingVariant;
  label?: string;
  compact?: boolean;
}) => {
  const cards = variant === 'form' ? 0 : variant === 'builder' ? 3 : 4;
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={label}
      className={`mx-auto w-full max-w-[1700px] space-y-4 p-4 md:p-6 ${compact ? 'min-h-[420px]' : 'min-h-[55vh]'}`}
    >
      <span className="sr-only">{label}</span>
      <SkeletonPanel className="flex items-center justify-between gap-6 p-5">
        <div className="min-w-0 flex-1 space-y-3"><Shimmer className="h-6 w-44 max-w-[60%]" /><Shimmer className="h-3 w-72 max-w-[85%]" /></div>
        <Shimmer className="hidden h-10 w-32 sm:block" />
      </SkeletonPanel>

      {variant === 'form' ? (
        <SkeletonPanel className="mx-auto max-w-4xl space-y-6 p-6 md:p-8">
          <div className="space-y-2"><Shimmer className="h-3 w-28" /><Shimmer className="h-12 w-full" /></div>
          <div className="grid gap-5 md:grid-cols-2">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="space-y-2"><Shimmer className="h-3 w-24" /><Shimmer className="h-12 w-full" /></div>)}</div>
          <Shimmer className="h-px w-full" />
          <div className="grid gap-5 md:grid-cols-2">{Array.from({ length: 2 }).map((_, index) => <div key={index} className="space-y-2"><Shimmer className="h-3 w-20" /><Shimmer className="h-12 w-full" /></div>)}</div>
        </SkeletonPanel>
      ) : (
        <>
          <div className={`grid gap-4 ${cards === 3 ? 'md:grid-cols-3' : 'sm:grid-cols-2 xl:grid-cols-4'}`}>
            {Array.from({ length: cards }).map((_, index) => <SkeletonPanel key={index} className="space-y-4 p-5"><div className="flex items-center justify-between"><Shimmer className="h-3 w-24" /><Shimmer className="h-9 w-9" /></div><Shimmer className="h-8 w-28" /><Shimmer className="h-3 w-36 max-w-full" /></SkeletonPanel>)}
          </div>
          {variant === 'detail' ? (
            <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]"><SkeletonPanel className="space-y-4 p-5"><Shimmer className="h-16 w-16 rounded-full" />{Array.from({ length: 5 }).map((_, index) => <Shimmer key={index} className="h-4 w-full" />)}</SkeletonPanel><SkeletonPanel className="space-y-5 p-5"><Shimmer className="h-6 w-52" /><div className="grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }).map((_, index) => <Shimmer key={index} className="h-28 w-full" />)}</div></SkeletonPanel></div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.7fr)]"><SkeletonPanel className="space-y-5 p-5"><Shimmer className="h-5 w-52" /><Shimmer className="h-64 w-full" /></SkeletonPanel><SkeletonPanel className="space-y-4 p-5"><Shimmer className="h-5 w-36" />{Array.from({ length: 5 }).map((_, index) => <Shimmer key={index} className="h-12 w-full" />)}</SkeletonPanel></div>
          )}
          {variant === 'table' && <SkeletonPanel className="space-y-3 p-4">{Array.from({ length: 6 }).map((_, index) => <Shimmer key={index} className="h-12 w-full" />)}</SkeletonPanel>}
        </>
      )}
    </div>
  );
};

export const PanelLoadingSkeleton = ({ rows = 5, label = 'Loading details' }: { rows?: number; label?: string }) => (
  <div role="status" aria-label={label} aria-busy="true" className="space-y-4 p-5">
    <span className="sr-only">{label}</span>
    <div className="flex items-center justify-between"><Shimmer className="h-6 w-48" /><Shimmer className="h-9 w-24" /></div>
    <Shimmer className="h-px w-full" />
    {Array.from({ length: rows }).map((_, index) => <Shimmer key={index} className="h-16 w-full" />)}
  </div>
);

export const ListLoadingSkeleton = ({ rows = 5, label = 'Loading items' }: { rows?: number; label?: string }) => (
  <div role="status" aria-label={label} aria-busy="true" className="space-y-3">
    <span className="sr-only">{label}</span>
    {Array.from({ length: rows }).map((_, index) => <Shimmer key={index} className="h-16 w-full" />)}
  </div>
);

export const InlineLoadingBadge = ({ label = 'Loading' }: { label?: string }) => (
  <span
    role="status"
    aria-live="polite"
    className="inline-flex min-h-7 items-center gap-2 rounded-full border border-blue-500/15 bg-blue-500/[0.07] px-2.5 text-[10px] font-extrabold uppercase tracking-[0.08em] text-blue-600 dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-300"
  >
    <span aria-hidden="true" className="relative h-3.5 w-3.5 shrink-0">
      <span className="absolute inset-0 rounded-full border-2 border-blue-500/20 dark:border-blue-300/20" />
      <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-blue-600 border-r-blue-600 motion-reduce:animate-none dark:border-t-blue-300 dark:border-r-blue-300" />
    </span>
    {label}
  </span>
);

// Skeleton for a single StatCard
export const StatCardSkeleton = () => (
  <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100/60">
    <div className="flex justify-between items-start mb-4">
      <Shimmer className="w-11 h-11 rounded-xl" />
      <Shimmer className="w-20 h-5 rounded-md" />
    </div>
    <Shimmer className="w-24 h-3 mb-3 rounded" />
    <Shimmer className="w-28 h-9 mb-2 rounded" />
    <Shimmer className="w-36 h-3 mb-4 rounded" />
    <div className="pt-3 border-t border-slate-100/60">
      <Shimmer className="w-32 h-3 rounded" />
    </div>
  </div>
);

// Skeleton for a Hero/Score card
export const HeroSkeleton = () => (
  <div className="lg:col-span-4 bg-gradient-to-r from-violet-200 to-violet-300 p-6 rounded-2xl animate-pulse">
    <div className="flex items-center gap-6">
      <div className="w-20 h-20 rounded-full bg-white/30" />
      <div className="space-y-3">
        <Shimmer className="w-48 h-3 rounded bg-white/50" />
        <Shimmer className="w-32 h-12 rounded bg-white/50" />
      </div>
    </div>
  </div>
);

// Skeleton for a chart panel
export const ChartSkeleton = ({ height = 280 }: { height?: number }) => (
  <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
    <Shimmer className="w-40 h-4 mb-1 rounded" />
    <Shimmer className="w-56 h-3 mb-6 rounded" />
    <div className="flex items-end gap-3" style={{ height }}>
      {[60, 85, 55, 90, 70, 95, 65].map((h, i) => (
        <div key={i} className="flex-1 flex flex-col justify-end">
          <Shimmer className="w-full rounded-t-lg animate-pulse" style={{ height: `${h}%` }} />
        </div>
      ))}
    </div>
  </div>
);

// Skeleton for a table row
export const TableRowSkeleton = () => (
  <div className="flex items-center gap-4 px-4 py-4 bg-white rounded-xl border border-slate-100 shadow-sm">
    <Shimmer className="w-6 h-4 rounded" />
    <div className="flex items-center gap-3 flex-1">
      <Shimmer className="w-9 h-9 rounded-full shrink-0" />
      <Shimmer className="w-36 h-4 rounded" />
    </div>
    <Shimmer className="w-16 h-4 rounded" />
    <Shimmer className="w-20 h-6 rounded-lg" />
    <Shimmer className="w-20 h-6 rounded-lg" />
    <Shimmer className="w-14 h-4 rounded" />
    <Shimmer className="w-14 h-4 rounded" />
    <Shimmer className="w-14 h-4 rounded" />
    <Shimmer className="w-16 h-4 rounded font-mono" />
    <Shimmer className="w-16 h-4 rounded font-mono" />
    <Shimmer className="w-14 h-4 rounded" />
  </div>
);

// Full Executive View Skeleton
export const ExecutiveViewSkeleton = () => (
  <div className="p-4 md:p-8 max-w-[1600px] mx-auto space-y-8">
    {/* Hero + Stats */}
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      <HeroSkeleton />
      <StatCardSkeleton />
      <StatCardSkeleton />
      <StatCardSkeleton />
      <StatCardSkeleton />
    </div>

    {/* Funnel */}
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
      <Shimmer className="w-40 h-4 mb-1 rounded" />
      <Shimmer className="w-56 h-3 mb-6 rounded" />
      <div className="flex flex-col lg:flex-row gap-4">
        {[1,2,3].map(i => (
          <div key={i} className="flex-1">
            <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5">
              <div className="flex items-center gap-3 mb-3">
                <Shimmer className="w-9 h-9 rounded-xl" />
                <Shimmer className="w-28 h-3 rounded" />
              </div>
              <Shimmer className="w-24 h-9 rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>

    {/* KPI Chart */}
    <ChartSkeleton height={180} />

    {/* Two charts side by side */}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ChartSkeleton height={220} />
      <ChartSkeleton height={220} />
    </div>

    {/* Leakage + Insights */}
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
        <Shimmer className="w-40 h-4 mb-4 rounded" />
        <div className="flex justify-center gap-6 mt-4">
          {[1, 2].map(i => (
            <div key={i} className="flex flex-col items-center gap-2">
              <Shimmer className="w-28 h-28 rounded-full" />
              <Shimmer className="w-20 h-3 rounded" />
              <Shimmer className="w-24 h-5 rounded-md" />
            </div>
          ))}
        </div>
      </div>
      <div className="lg:col-span-2 bg-slate-900 rounded-2xl p-6">
        <Shimmer className="w-48 h-4 mb-5 rounded bg-white/20" />
        {[1, 2, 3].map(i => (
          <div key={i} className="bg-white/5 rounded-xl p-4 mb-4">
            <Shimmer className="w-56 h-3 mb-3 rounded bg-white/20" />
            <Shimmer className="w-full h-3 mb-2 rounded bg-white/10" />
            <Shimmer className="w-4/5 h-3 mb-2 rounded bg-white/10" />
            <Shimmer className="w-3/5 h-3 rounded bg-white/10" />
          </div>
        ))}
      </div>
    </div>

    {/* Agent Ranking */}
    <div className="bg-slate-50/50 rounded-2xl p-6 border border-slate-200/60">
      <Shimmer className="w-48 h-4 mb-5 rounded" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {[0, 1].map(col => (
          <div key={col} className="space-y-3">
            <Shimmer className="w-32 h-3 mb-3 rounded" />
            {[1, 2, 3].map(i => (
              <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-white border border-slate-100">
                <div className="flex items-center gap-3">
                  <Shimmer className="w-10 h-10 rounded-full" />
                  <div>
                    <Shimmer className="w-28 h-3 mb-1.5 rounded" />
                    <Shimmer className="w-16 h-2.5 rounded" />
                  </div>
                </div>
                <Shimmer className="w-20 h-5 rounded-full" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  </div>
);

// Full Operational View Skeleton
export const OperationalViewSkeleton = () => (
  <div className="p-4 md:p-8 max-w-[1600px] mx-auto space-y-6">
    {/* Alert bar */}
    <div className="bg-white rounded-2xl p-4 border border-slate-100">
      <Shimmer className="w-56 h-4 rounded" />
    </div>
    {/* Search bar */}
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-4 rounded-2xl border border-slate-100">
      <div className="flex items-center gap-6 flex-wrap">
        {[1,2,3,4,5].map(i => <Shimmer key={i} className="w-24 h-4 rounded" />)}
      </div>
      <Shimmer className="w-full sm:w-80 h-10 rounded-xl" />
    </div>
    {/* Table rows */}
    <div className="space-y-2">
      {Array.from({ length: 10 }).map((_, i) => (
        <TableRowSkeleton key={i} />
      ))}
    </div>
  </div>
);

// Generic SkeletonLoader for cards/lists layout
export const SkeletonLoader = ({ rows = 3 }: { rows?: number }) => (
  <div className="space-y-6 animate-pulse">
    <div className="flex items-center gap-4 bg-white p-6 rounded-3xl border border-slate-200/50 shadow-sm">
      <div className="w-16 h-16 rounded-2xl bg-slate-100 shrink-0" />
      <div className="flex-1 space-y-2.5">
        <div className="w-48 h-4 bg-slate-100 rounded" />
        <div className="w-32 h-3 bg-slate-100 rounded" />
      </div>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="bg-white p-6 rounded-2xl border border-slate-200/50 shadow-sm space-y-4">
          <div className="flex justify-between items-center">
            <div className="w-24 h-4 bg-slate-100 rounded" />
            <div className="w-12 h-6 bg-slate-100 rounded-lg" />
          </div>
          <div className="border-t border-slate-100 pt-3 flex justify-between">
            <div className="w-14 h-3 bg-slate-100 rounded" />
            <div className="w-14 h-3 bg-slate-100 rounded" />
            <div className="w-14 h-3 bg-slate-100 rounded" />
          </div>
          <div className="w-full h-9 bg-slate-100 rounded-xl" />
        </div>
      ))}
    </div>
  </div>
);

