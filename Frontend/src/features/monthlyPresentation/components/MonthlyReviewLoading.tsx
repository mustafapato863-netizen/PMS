import type { ReactNode } from 'react';

function Bone({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/80 motion-reduce:animate-none ${className}`} />;
}

/**
 * Placeholder for the Monthly Review overview while authorized records load.
 * The bars match the score, trend, and function cards that replace them.
 */
export function MonthlyReviewLoading({ toolbar }: { toolbar?: ReactNode }) {
  return (
    <main className="mx-auto max-w-7xl space-y-5 px-4 py-8 sm:px-6 lg:px-8">
      {toolbar && <div className="flex flex-wrap items-center gap-3">{toolbar}</div>}
      <section
        data-testid="monthly-loading"
        role="status"
        aria-live="polite"
        aria-busy="true"
        className="space-y-5"
      >
        <div className="rounded-2xl border border-slate-200/90 bg-white px-4 py-4 shadow-xs sm:px-5">
          <h1 className="text-lg font-bold text-slate-900">Loading Monthly Review</h1>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-600">
            Gathering the teams and scores available to your account.
          </p>
        </div>

        <div data-testid="monthly-loading-preview" aria-hidden="true" className="space-y-5">
          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs sm:p-5">
            <Bone className="h-5 w-28" />
            <Bone className="mt-3 h-8 w-72 max-w-full" />
            <Bone className="mt-2 h-4 w-44" />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200/70 bg-white p-6 shadow-[0_10px_32px_-18px_rgba(15,23,42,0.28)]">
              <Bone className="h-3 w-28" />
              <Bone className="mt-2 h-6 w-56 max-w-full" />
              <Bone className="mt-5 h-14 w-36" />
              <div className="mt-6 grid grid-cols-3 gap-3">
                <Bone className="h-16" />
                <Bone className="h-16" />
                <Bone className="h-16" />
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs">
              <Bone className="h-3 w-36" />
              <Bone className="mt-2 h-6 w-48 max-w-full" />
              <div className="mt-6 flex h-36 items-end gap-2 sm:gap-3">
                {[42, 58, 49, 72, 63, 84].map((height) => (
                  <div
                    key={height}
                    className="min-w-0 flex-1 animate-pulse rounded-t-md bg-slate-200/80 motion-reduce:animate-none"
                    style={{ height: `${height}%` }}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {['one', 'two', 'three', 'four'].map((slot) => (
              <div key={slot} className="rounded-2xl border border-slate-200/90 bg-white p-4">
                <Bone className="h-4 w-24" />
                <Bone className="mt-4 h-8 w-16" />
                <Bone className="mt-3 h-3 w-full" />
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
