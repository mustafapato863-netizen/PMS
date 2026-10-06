import type { ReactNode } from 'react';
import { ArrowRight, Calendar, CheckCircle2, Clock, Eye, Inbox, Info, Lock, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveDataStatus } from '../../../features/executive/types';
import { fmtDate } from '../../../features/executive/format';
import { formatPeriod } from '../../../features/executive/compose';

/** Shown when the requested month has no data but an earlier one does (default f). */
export function FallbackNotice({ notice }: { notice: string }) {
  return (
    <div role="status" className="flex items-start gap-[8px] rounded-[10px] border border-[var(--exec-warning-bg)] bg-[var(--exec-warning-bg)] px-[14px] py-[10px] text-[12px] font-medium text-[var(--exec-warning-text)]">
      <Info aria-hidden="true" className="mt-px size-[14px] shrink-0" strokeWidth={2} />
      <span>{notice}</span>
    </div>
  );
}

export function ScopeBanner({ children, icon = 'lock' }: { children: ReactNode; icon?: 'lock' | 'eye' }) {
  const Icon = icon === 'lock' ? Lock : Eye;
  return (
    <div role="note" className="flex items-start gap-[8px] rounded-[10px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[14px] py-[10px] text-[12px] text-[var(--insights-accent-text)]">
      <Icon aria-hidden="true" className="mt-px size-[14px] shrink-0" strokeWidth={2} />
      <span>{children}</span>
    </div>
  );
}

export function ReadOnlyBadge() {
  return (
    <span className="inline-flex items-center gap-[4px] rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--exec-chip-text)]">
      <Eye aria-hidden="true" className="size-[11px]" strokeWidth={2} />Read-only
    </span>
  );
}

const CHECKLIST = [
  ['Company score vs target', 'Gap, grade, vs last month and a 6-month trend'],
  ['Function scorecards', 'Call Center, RCM, Pre-Approvals, Marketing — click through to Function Summary'],
  ['Region split', 'EGY vs UAE score, grade, gap and headcount'],
  ['Direction-aware drivers', 'Top 3 negative and positive KPI movements (↑/↓ better)'],
  ['Teams at risk + grade mix', 'Grade D/E or falling 2 months; A–E distribution with movement'],
  ['Corrective actions', 'Open, overdue and due-this-week with the most urgent items'],
];

/** Full empty state (Figma 49:2 / 49:394): only when the scope has no data at all. */
export function ExecutiveEmptyState({ monthLabel, canUpload, dataStatus, onPickMonth }: {
  monthLabel: string; canUpload: boolean; dataStatus: ExecutiveDataStatus; onPickMonth: () => void;
}) {
  const upload = dataStatus.last_upload;
  const month = monthLabel.split(' ')[0];
  return (
    <div className="flex flex-col gap-[16px]" data-testid="executive-empty">
      <section aria-labelledby="exec-empty-title" className="flex flex-col items-center gap-[16px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[24px] py-[36px] text-center shadow-[var(--exec-card-shadow)]">
        <span aria-hidden="true" className="flex size-[120px] items-center justify-center rounded-full bg-[var(--insights-accent-soft)]">
          <span className="flex size-[88px] items-center justify-center rounded-full bg-[var(--insights-accent-tag)]">
            <span className="flex size-[52px] items-center justify-center rounded-[12px] bg-[var(--bg-surface)] shadow-[var(--exec-card-shadow)]">
              <Inbox className="size-[24px] text-[var(--insights-accent)]" strokeWidth={1.75} />
            </span>
          </span>
        </span>
        <span className="inline-flex items-center gap-[4px] rounded-full bg-[var(--exec-warning-bg)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--exec-warning-text)]">
          <Info aria-hidden="true" className="size-[11px]" />No data · {monthLabel}
        </span>
        <h2 id="exec-empty-title" className="text-[24px] font-bold text-[var(--insights-heading)]">No performance data for {monthLabel}</h2>
        <p className="max-w-[560px] text-[14px] leading-[1.5] text-[var(--text-secondary)]">
          Scores, grades and drivers appear after the {month} performance file is uploaded and processed. Your filters are fine — this month simply has no data yet.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-[10px]">
          {canUpload ? (
            <Link to="/settings" className="inline-flex items-center gap-[8px] rounded-[8px] bg-gradient-to-r from-[#0069B4] to-[#00A859] px-[16px] py-[10px] text-[13px] font-semibold text-white">
              <Upload aria-hidden="true" className="size-[15px]" />Upload performance data
            </Link>
          ) : (
            <span className="inline-flex items-center gap-[8px] rounded-[8px] bg-[var(--exec-chip-bg)] px-[14px] py-[10px] text-[13px] font-medium text-[var(--exec-chip-text)]">
              Ask your admin to upload {month} data.
            </span>
          )}
          <button type="button" onClick={onPickMonth} className="inline-flex items-center gap-[8px] rounded-[8px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[14px] py-[10px] text-[13px] font-semibold text-[var(--insights-heading)]">
            <Calendar aria-hidden="true" className="size-[15px]" />Pick another month
          </button>
        </div>
        {upload && (
          <p className="flex flex-wrap items-center justify-center gap-[8px] border-t border-[var(--insights-row-border)] pt-[14px] text-[12px] text-[var(--text-secondary)]">
            <Clock aria-hidden="true" className="size-[13px]" />
            Last upload: {formatPeriod(upload.period)} · {upload.employees} employees{upload.uploaded_at ? ` · uploaded ${fmtDate(upload.uploaded_at)}` : ''}{upload.uploaded_by ? ` by ${upload.uploaded_by}` : ''}
          </p>
        )}
      </section>
      <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
        <section aria-labelledby="exec-empty-what" className="flex flex-col gap-[12px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[20px] py-[18px]">
          <div className="flex items-center gap-[10px]">
            <span aria-hidden="true" className="flex size-[30px] items-center justify-center rounded-[8px] bg-[var(--exec-pos-bg)]"><CheckCircle2 className="size-[16px] text-[var(--insights-positive)]" /></span>
            <div>
              <h3 id="exec-empty-what" className="text-[15px] font-semibold text-[var(--insights-heading)]">What appears once {month} data exists</h3>
              <p className="text-[12px] text-[var(--text-muted)]">Same layout as a normal month — nothing to configure</p>
            </div>
          </div>
          <ul className="grid gap-[10px] md:grid-cols-2">
            {CHECKLIST.map(([title, text]) => (
              <li key={title} className="flex gap-[8px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] px-[12px] py-[10px]">
                <CheckCircle2 aria-hidden="true" className="mt-px size-[14px] shrink-0 text-[var(--insights-positive)]" />
                <span className="flex flex-col text-left">
                  <span className="text-[13px] font-semibold text-[var(--insights-heading)]">{title}</span>
                  <span className="text-[11px] text-[var(--text-muted)]">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
        {canUpload && (
          <section aria-labelledby="exec-empty-how" className="flex flex-col gap-[12px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[20px] py-[18px]">
            <div className="flex items-center gap-[10px]">
              <span aria-hidden="true" className="flex size-[30px] items-center justify-center rounded-[8px] bg-[var(--exec-info-bg)]"><Upload className="size-[16px] text-[var(--exec-info-text)]" /></span>
              <div>
                <h3 id="exec-empty-how" className="text-[15px] font-semibold text-[var(--insights-heading)]">How to publish {month}</h3>
                <p className="text-[12px] text-[var(--text-muted)]">Admin · about 5 minutes</p>
              </div>
            </div>
            <ol className="flex flex-col gap-[12px]">
              {[
                ['Download the KPI template', 'Same columns as last month; one row per employee per KPI'],
                [`Upload the ${month} file`, 'Validation checks targets, directions (↑/↓ better) and team mapping'],
                ['Review and publish', 'Scores and grades go live for every role at once'],
              ].map(([title, text], index) => (
                <li key={title} className="flex gap-[10px]">
                  <span className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-[var(--exec-info-bg)] text-[11px] font-bold text-[var(--exec-info-text)]">{index + 1}</span>
                  <span className="flex flex-col">
                    <span className="text-[13px] font-semibold text-[var(--insights-heading)]">{title}</span>
                    <span className="text-[11px] text-[var(--text-muted)]">{text}</span>
                  </span>
                </li>
              ))}
            </ol>
            <Link to="/settings" className="inline-flex items-center gap-[4px] self-start text-[12px] font-semibold text-[var(--insights-accent-text)]">Open data upload <ArrowRight aria-hidden="true" className="size-[13px]" /></Link>
          </section>
        )}
      </div>
    </div>
  );
}
