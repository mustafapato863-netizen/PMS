import type { ReactNode } from 'react';
import { GRADE_PALETTE, getGradeClassOrNull } from '../../constants/grades';
import { SLIDE_COUNT, REGION_LABEL, kpiMovementTone, movementArrow, type KpiBadge, type Readiness, type Tone } from './model';
import type { DeckData } from './deckTypes';

const fmtNum = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${Number(v.toFixed(d))}`);
const toneClass = (t: Tone) => `mp-tone-${t}`;

export function NoDataBadge({ label = 'No data' }: { label?: string }) {
  return <span className="mp-badge mp-badge-nodata" data-testid="no-data-badge">{label}</span>;
}
export function StatusBadge({ badge }: { badge: KpiBadge }) {
  if (badge === 'no_data') return <NoDataBadge />;
  const text = badge === 'on_track' ? 'On track' : badge === 'at_risk' ? 'At risk' : 'Critical';
  return <span className={`mp-badge mp-badge-${badge}`}>{text}</span>;
}
const READY_TEXT: Record<Readiness, string> = { ready: 'Ready', partial: 'Partial', not_ready: 'Not ready', no_data: 'No data' };
export function ReadyBadge({ status }: { status: Readiness }) {
  if (status === 'no_data') return <NoDataBadge />;
  return <span className={`mp-badge mp-ready-${status}`}>{READY_TEXT[status]}</span>;
}
export function GradeBadge({ score }: { score: number | null | undefined }) {
  const g = getGradeClassOrNull(score);
  if (!g) return <NoDataBadge />;
  const p = GRADE_PALETTE[g];
  return <span className="mp-badge" style={{ color: p.text, background: p.background, borderColor: p.border }}>Grade {g}</span>;
}
export function Movement({ delta, direction, suffix = ' pts' }: { delta: number | null | undefined; direction: string | null | undefined; suffix?: string }) {
  if (delta == null || !Number.isFinite(delta)) return <span className="mp-tone-neutral">MoM not available</span>;
  const tone = kpiMovementTone(delta, direction);
  return <span className={toneClass(tone)} data-tone={tone}>{movementArrow(delta)} {fmtNum(Math.abs(delta))}{suffix}</span>;
}

export function SlideFrame({ n, kicker, title, sub, data, children, insightsHref }: {
  n: number; kicker: string; title: ReactNode; sub?: ReactNode; data: DeckData; children?: ReactNode; insightsHref: string;
}) {
  const id = `s${String(n).padStart(2, '0')}`;
  return (
    <section id={id} className="mp-slide" aria-label={`Slide ${n} of ${SLIDE_COUNT}: ${kicker}`} data-slide={n}>
      <header className="mp-slide-head">
        <div className="mp-row"><span className="mp-pill mp-pill-n">{String(n).padStart(2, '0')} / {SLIDE_COUNT}</span><span className="mp-kicker">{kicker}</span></div>
        <div className="mp-row">
          <span className="mp-pill">{REGION_LABEL[data.code]}</span>
          <span className="mp-pill mp-pill-lock" data-testid="period-lock">Period locked · {data.period.label}</span>
          {data.status === 'Final' && <span className="mp-pill mp-pill-frozen">Frozen</span>}
        </div>
      </header>
      <h2 className="mp-title">{title}</h2>
      {sub && <p className="mp-sub">{sub}</p>}
      <div className="mp-body">{children}</div>
      <footer className="mp-slide-foot">
        <span>{REGION_LABEL[data.code]} (region={data.code}) only · {data.period.short} {data.period.year}{data.previousLabel ? ` vs ${data.previousLabel}` : ''} · data as of: not available</span>
        <a href={insightsHref} className="mp-link">Open in Insights →</a>
      </footer>
    </section>
  );
}


export function SlideEmpty({ title, body, children }: { title: string; body?: string; children?: ReactNode }) {
  return <div className="mp-empty"><div className="mp-hatch" aria-hidden /><strong>{title}</strong>{body && <p>{body}</p>}{children}</div>;
}


export function Bar({ parts }: { parts: Array<readonly [string, number, string]> }) {
  const total = parts.reduce((a, p) => a + p[1], 0) || 1;
  return (
    <>
      <div className="mp-bar" role="img" aria-label={parts.map((p) => `${p[0]} ${p[1]}`).join(', ')}>
        {parts.filter((p) => p[1] > 0).map((p) => <span key={p[0]} className={p[2] === 'hatch' ? 'mp-hatch' : ''} style={{ width: `${(p[1] / total) * 100}%`, background: p[2] === 'hatch' ? undefined : p[2] }} />)}
      </div>
      <div className="mp-row mp-gap mp-small">{parts.map((p) => <span key={p[0]}><i className={`mp-dot ${p[2] === 'hatch' ? 'mp-hatch' : ''}`} style={{ background: p[2] === 'hatch' ? undefined : p[2] }} /> {p[0]} {p[1]}</span>)}</div>
    </>
  );
}
