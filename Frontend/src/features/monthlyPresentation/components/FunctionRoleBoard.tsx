import { useState } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  UserCheck,
  Users,
} from 'lucide-react';
import { GRADE_STYLES } from '../monthlyOverviewData';
import type { FunctionRoleCard } from '../roleDetailData';
import { FullWordGradeBadge } from './TeamDeepDiveView';

const ROLES_PER_ROW = 4;

function Movement({
  change,
  previousMonthLabel,
  compact = false,
}: {
  change: number | null;
  previousMonthLabel: string;
  compact?: boolean;
}) {
  if (change === null) {
    return (
      <span className="text-slate-400">
        {compact ? '—' : `No ${previousMonthLabel} baseline`}
      </span>
    );
  }
  const up = change >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 font-bold tabular-nums ${
        up ? 'text-emerald-700' : 'text-rose-700'
      }`}
    >
      {up ? (
        <ArrowUpRight className="size-3 shrink-0" aria-hidden />
      ) : (
        <ArrowDownRight className="size-3 shrink-0" aria-hidden />
      )}
      {up ? '+' : ''}
      {change.toFixed(1)}%
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/*  Dragging Role Card — Compact Single-Row Card with Clear Problem Emphasis  */
/* -------------------------------------------------------------------------- */

function DraggingRoleCard({
  role,
  previousMonthLabel,
  onSelectRole,
}: {
  role: FunctionRoleCard;
  previousMonthLabel: string;
  onSelectRole: (roleSlug: string) => void;
}) {
  const gradeStyle = GRADE_STYLES[role.grade];
  const isSevere = role.score < 80;

  return (
    <button
      type="button"
      data-testid={`role-card-${role.roleSlug}`}
      onClick={() => onSelectRole(role.roleSlug)}
      aria-label={`Open ${role.roleTitle} role detail`}
      className={`group relative flex h-full w-full flex-col justify-between overflow-hidden rounded-xl border bg-white p-3.5 text-left shadow-2xs transition-all duration-150 hover:-translate-y-0.5 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 ${
        isSevere
          ? 'border-rose-200/95 hover:border-rose-300'
          : 'border-amber-200/95 hover:border-amber-300'
      }`}
    >
      <div className="w-full">
        {/* 1. Role Headcount Tag & Full-Word Grade */}
        <div className="flex items-center justify-between gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase ${
              isSevere
                ? 'border-rose-200/80 bg-rose-50/80 text-rose-800'
                : 'border-amber-200/80 bg-amber-50/80 text-amber-800'
            }`}
          >
            <Users className="size-2.5 shrink-0" aria-hidden />
            {role.headcount} {role.headcount === 1 ? 'person' : 'people'}
          </span>
          <FullWordGradeBadge
            grade={role.grade}
            gradeFullLabel={role.gradeFullLabel}
            size="sm"
          />
        </div>

        {/* 2. Aggregated Role Title */}
        <h3
          className="mt-2 truncate text-sm font-bold tracking-tight text-slate-900 transition-colors group-hover:text-rose-700"
          title={role.roleTitle}
        >
          {role.roleTitle}
        </h3>

        {/* 3. Compact Score + Gap + Movement Metric Box */}
        <div
          className={`mt-2 flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2 ${
            isSevere
              ? 'border-rose-100/90 bg-rose-50/35'
              : 'border-amber-100/90 bg-amber-50/30'
          }`}
        >
          <div>
            <div className="text-[9px] font-bold tracking-wider text-slate-400 uppercase">
              {role.headcount > 1 ? 'Combined' : 'Score'}
            </div>
            <p
              className={`text-xl font-extrabold tracking-tight tabular-nums sm:text-2xl ${gradeStyle.scoreText}`}
            >
              {role.score.toFixed(1)}%
            </p>
          </div>

          <dl className="flex items-center gap-2 text-[11px]">
            <div className="text-right">
              <dt className="text-[9px] font-medium text-slate-400">Gap</dt>
              <dd className="font-bold text-rose-600 tabular-nums">
                {role.gap.toFixed(1)}%
              </dd>
            </div>
            <div className="h-5 w-px bg-slate-200/80" />
            <div className="text-right">
              <dt className="text-[9px] font-medium text-slate-400">
                vs {previousMonthLabel.slice(0, 3)}
              </dt>
              <dd>
                <Movement
                  change={role.changeVsPrev}
                  previousMonthLabel={previousMonthLabel}
                  compact
                />
              </dd>
            </div>
          </dl>
        </div>

        {/* 4. Compact Primary Drag Box */}
        <div
          className={`mt-2 line-clamp-2 rounded-lg border px-2.5 py-1.5 text-[11px] leading-snug ${
            isSevere
              ? 'border-rose-200/70 bg-rose-50/50 text-slate-700'
              : 'border-amber-200/70 bg-amber-50/45 text-slate-700'
          }`}
          title={role.signal}
        >
          <span
            className={`font-bold ${
              isSevere ? 'text-rose-900' : 'text-amber-900'
            }`}
          >
            Primary drag:{' '}
          </span>
          {role.signal}
        </div>
      </div>

      {/* 5. Compact Footer CTA */}
      <div className="mt-2.5 flex w-full items-center justify-end border-t border-slate-100 pt-2">
        <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-blue-700 underline-offset-2 transition-colors group-hover:text-blue-950 group-hover:underline">
          View role
          <ArrowRight
            className="size-3 shrink-0 transition-transform group-hover:translate-x-1"
            aria-hidden
          />
        </span>
      </div>
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Carrying Role Card — Visually Quieter & Compact                           */
/* -------------------------------------------------------------------------- */

function CarryingRoleCard({
  role,
  previousMonthLabel,
  onSelectRole,
}: {
  role: FunctionRoleCard;
  previousMonthLabel: string;
  onSelectRole: (roleSlug: string) => void;
}) {
  const gradeStyle = GRADE_STYLES[role.grade];

  return (
    <button
      type="button"
      data-testid={`role-card-${role.roleSlug}`}
      onClick={() => onSelectRole(role.roleSlug)}
      aria-label={`Open ${role.roleTitle} role detail`}
      className="group relative flex h-full w-full flex-col justify-between overflow-hidden rounded-xl border border-slate-200/85 bg-white/95 p-3 text-left transition-all duration-150 hover:border-emerald-300 hover:bg-white hover:shadow-2xs focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
    >
      <div className="w-full">
        {/* Top Row: Headcount + Full-Word Grade */}
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold tracking-wider text-slate-500 uppercase">
            <Users className="size-2.5 shrink-0 text-slate-400" aria-hidden />
            {role.headcount} {role.headcount === 1 ? 'person' : 'people'}
          </span>
          <FullWordGradeBadge
            grade={role.grade}
            gradeFullLabel={role.gradeFullLabel}
            size="sm"
          />
        </div>

        {/* Aggregated Role Title */}
        <h3
          className="mt-1 truncate text-xs font-bold tracking-tight text-slate-800 transition-colors group-hover:text-emerald-700 sm:text-sm"
          title={role.roleTitle}
        >
          {role.roleTitle}
        </h3>

        {/* Compact Score & Gap Row */}
        <div className="mt-2 flex items-baseline justify-between gap-2 border-y border-slate-100 py-1.5">
          <p
            className={`text-lg font-extrabold tracking-tight tabular-nums sm:text-xl ${gradeStyle.scoreText}`}
          >
            {role.score.toFixed(1)}%
          </p>
          <div className="flex items-center gap-1.5 text-[10px] text-slate-500 tabular-nums">
            <span>Gap {role.gap.toFixed(1)}%</span>
            <span>·</span>
            <Movement
              change={role.changeVsPrev}
              previousMonthLabel={previousMonthLabel}
              compact
            />
          </div>
        </div>

        {/* Key Strength */}
        <p className="mt-1.5 line-clamp-1 text-[11px] leading-snug text-slate-600">
          <span className="font-semibold text-emerald-800">Carrying: </span>
          {role.signal}
        </p>
      </div>

      {/* Quiet Footer Link */}
      <div className="mt-2 flex w-full items-center justify-end border-t border-slate-100 pt-2">
        <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-blue-700 underline-offset-2 transition-colors group-hover:text-blue-950 group-hover:underline">
          View role
          <ArrowRight
            className="size-3 shrink-0 transition-transform group-hover:translate-x-1"
            aria-hidden
          />
        </span>
      </div>
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Main FunctionRoleBoard                                                    */
/* -------------------------------------------------------------------------- */

export default function FunctionRoleBoard({
  roles,
  previousMonthLabel,
  onSelectRole,
}: {
  roles: FunctionRoleCard[];
  previousMonthLabel: string;
  onSelectRole: (roleSlug: string) => void;
}) {
  const dragging = roles
    .filter((role) => role.score < 90)
    .sort((a, b) => a.score - b.score || a.roleTitle.localeCompare(b.roleTitle));
  const carrying = roles
    .filter((role) => role.score >= 90)
    .sort((a, b) => b.score - a.score || a.roleTitle.localeCompare(b.roleTitle));

  const [draggingStart, setDraggingStart] = useState(0);
  const [carryingStart, setCarryingStart] = useState(0);

  const maxDraggingStart = Math.max(0, dragging.length - ROLES_PER_ROW);
  const safeDraggingStart = Math.min(draggingStart, maxDraggingStart);
  const visibleDragging = dragging.slice(
    safeDraggingStart,
    safeDraggingStart + ROLES_PER_ROW,
  );

  const maxCarryingStart = Math.max(0, carrying.length - ROLES_PER_ROW);
  const safeCarryingStart = Math.min(carryingStart, maxCarryingStart);
  const visibleCarrying = carrying.slice(
    safeCarryingStart,
    safeCarryingStart + ROLES_PER_ROW,
  );

  return (
    <div id="presentation-section-function-roles" data-section-label="Roles" className="scroll-mt-24 space-y-5">
      {/* 1. ROLES DRAGGING PERFORMANCE (Compact Single-Row Carousel, Worst to Best) */}
      <section
        aria-labelledby="roles-dragging-heading"
        data-testid="roles-dragging"
        className="rounded-2xl border border-rose-200/90 bg-gradient-to-b from-rose-50/40 via-rose-50/10 to-white p-4 shadow-2xs sm:p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-rose-200/60 pb-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-1 rounded-md border border-rose-200 bg-rose-100/80 px-2 py-0.5 text-[10px] font-bold tracking-wider text-rose-800 uppercase">
              <AlertTriangle className="size-3 text-rose-600" aria-hidden />
              Where the Score Is Lost
            </span>
            <h2
              id="roles-dragging-heading"
              className="text-base font-bold tracking-tight text-slate-900 sm:text-lg"
            >
              Roles Dragging Performance
            </h2>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 text-[11px] font-bold text-rose-700">
              <span className="size-1.5 rounded-full bg-rose-500" />
              {dragging.length} {dragging.length === 1 ? 'role' : 'roles'} below 90%
            </span>
          </div>

          {dragging.length > ROLES_PER_ROW && (
            <div
              data-testid="dragging-roles-carousel"
              className="inline-flex items-center gap-1.5 rounded-xl border border-rose-200/80 bg-white px-2 py-1 shadow-2xs"
            >
              <span className="px-1 text-[11px] font-bold text-slate-500 tabular-nums">
                {safeDraggingStart + 1}–
                {Math.min(dragging.length, safeDraggingStart + ROLES_PER_ROW)} of{' '}
                {dragging.length}
              </span>
              <button
                type="button"
                data-testid="dragging-roles-prev"
                aria-label="Previous dragging roles"
                disabled={safeDraggingStart === 0}
                onClick={() => setDraggingStart((prev) => Math.max(0, prev - 1))}
                className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronLeft className="size-3.5" aria-hidden />
              </button>
              <button
                type="button"
                data-testid="dragging-roles-next"
                aria-label="Next dragging roles"
                disabled={safeDraggingStart >= maxDraggingStart}
                onClick={() =>
                  setDraggingStart((prev) => Math.min(maxDraggingStart, prev + 1))
                }
                className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronRight className="size-3.5" aria-hidden />
              </button>
            </div>
          )}
        </div>

        {dragging.length ? (
          <div className="mt-3.5">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {visibleDragging.map((role) => (
                <DraggingRoleCard
                  key={role.roleSlug}
                  role={role}
                  previousMonthLabel={previousMonthLabel}
                  onSelectRole={onSelectRole}
                />
              ))}
            </div>

            {dragging.length > ROLES_PER_ROW && (
              <div className="mt-2.5 flex items-center justify-center gap-1.5">
                {Array.from({ length: maxDraggingStart + 1 }, (_, idx) => (
                  <button
                    key={idx}
                    type="button"
                    aria-label={`Show dragging roles starting at ${idx + 1}`}
                    onClick={() => setDraggingStart(idx)}
                    className={`h-1.5 rounded-full transition-all ${
                      idx === safeDraggingStart
                        ? 'w-5 bg-rose-600'
                        : 'w-1.5 bg-rose-200 hover:bg-rose-300'
                    }`}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="mt-3.5 flex items-center gap-2.5 rounded-xl border border-emerald-200/80 bg-emerald-50/60 px-4 py-3 text-xs font-medium text-emerald-900">
            <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-hidden />
            <span>No roles are below the 90% threshold this month.</span>
          </div>
        )}
      </section>

      {/* 2. ROLES CARRYING PERFORMANCE (Compact Single-Row Carousel) */}
      <section
        aria-labelledby="roles-carrying-heading"
        data-testid="roles-carrying"
        className="rounded-2xl border border-slate-200/85 bg-slate-50/55 p-4 sm:p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-200/70 pb-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200/80 bg-emerald-50/80 px-2 py-0.5 text-[10px] font-bold tracking-wider text-emerald-800 uppercase">
              <UserCheck className="size-3 text-emerald-600" aria-hidden />
              Where the Score Is Held
            </span>
            <h2
              id="roles-carrying-heading"
              className="text-sm font-bold tracking-tight text-slate-800 sm:text-base"
            >
              Roles Carrying Performance
            </h2>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200/80 bg-white px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {carrying.length} at or above 90%
            </span>
          </div>

          {carrying.length > ROLES_PER_ROW && (
            <div className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2 py-1 shadow-2xs">
              <span className="px-1 text-[11px] font-bold text-slate-500 tabular-nums">
                {safeCarryingStart + 1}–
                {Math.min(carrying.length, safeCarryingStart + ROLES_PER_ROW)} of{' '}
                {carrying.length}
              </span>
              <button
                type="button"
                aria-label="Previous carrying roles"
                disabled={safeCarryingStart === 0}
                onClick={() => setCarryingStart((prev) => Math.max(0, prev - 1))}
                className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronLeft className="size-3.5" aria-hidden />
              </button>
              <button
                type="button"
                aria-label="Next carrying roles"
                disabled={safeCarryingStart >= maxCarryingStart}
                onClick={() =>
                  setCarryingStart((prev) => Math.min(maxCarryingStart, prev + 1))
                }
                className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronRight className="size-3.5" aria-hidden />
              </button>
            </div>
          )}
        </div>

        {carrying.length ? (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {visibleCarrying.map((role) => (
              <CarryingRoleCard
                key={role.roleSlug}
                role={role}
                previousMonthLabel={previousMonthLabel}
                onSelectRole={onSelectRole}
              />
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs text-slate-600">
            No roles are at or above 90% this month.
          </p>
        )}
      </section>
    </div>
  );
}
