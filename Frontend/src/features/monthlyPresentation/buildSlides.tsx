import type { ReactNode } from 'react';
import { GRADE_PALETTE, getGradeClassOrNull, type GradeClass } from '../../constants/grades';
import {
  REGION_FUNCTIONS, REGION_LABEL, SLIDE_COUNT, actionMix, displayActionState, expectedImpact, isCriticalKpi, kpiBadge,
  kpiMovementTone, MASKED_DETAILS_LABEL, movementArrow, outlookLine, regionMoM, type Readiness, type Tone,
} from './model';
import type { DeckData, SlideState } from './deckTypes';
import { Bar, GradeBadge, Movement, NoDataBadge, ReadyBadge, SlideEmpty, SlideFrame, StatusBadge } from './SlideParts';

const fmtPct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(d)}%`);
const fmtNum = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${Number(v.toFixed(d))}`);
const fmtPts = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)} pts`;
const fmtDue = (iso: string | null) => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : '—');
const toneClass = (t: Tone) => `mp-tone-${t}`;

export function buildSlides(data: DeckData, insightsHref: string, opts: { appendix: boolean; state?: (n: number) => SlideState; retry?: (n: number) => void; gradeMixState?: SlideState }): ReactNode[] {
  const { ws, code, period } = data;
  const region = REGION_LABEL[code];
  const F = (n: number, kicker: string, title: ReactNode, body: ReactNode, sub?: ReactNode) => {
    const st = opts.state?.(n) ?? { status: 'ready' as const };
    if (st.status === 'loading') return (
      <SlideFrame key={n} n={n} kicker={kicker} title={kicker} data={data} insightsHref={insightsHref}>
        <div className="mp-slide-state" role="status" data-testid={`slide-loading-${n}`}>Loading {kicker.toLowerCase()} for {region} · {period.label}…</div>
      </SlideFrame>
    );
    if (st.status === 'error') return (
      <SlideFrame key={n} n={n} kicker={kicker} title={kicker} data={data} insightsHref={insightsHref}>
        <div className="mp-slide-state mp-slide-error" role="alert" data-testid={`slide-error-${n}`}>
          <p><b>This slide could not be loaded.</b> {st.message}</p>
          <p className="mp-muted mp-small">Nothing is shown rather than partial numbers. Other slides are unaffected.</p>
          {st.retry && <button type="button" className="mp-btn" onClick={st.retry}>Retry</button>}
        </div>
      </SlideFrame>
    );
    return <SlideFrame key={n} n={n} kicker={kicker} title={title} sub={sub} data={data} insightsHref={insightsHref}>{body}</SlideFrame>;
  };
  const s = ws?.summary;
  const story = ws?.executive_story ?? null;
  const mom = regionMoM(story, Boolean(ws?.comparison?.is_adjacent));
  const counts = data.teams.reduce((acc, t) => ({ ...acc, [t.status]: (acc[t.status] ?? 0) + 1 }), {} as Record<Readiness, number>);
  const mix = actionMix(data.actions, period.endDate);
  const diag = ws?.kpi_diagnosis ?? [];
  const drivers = [...(ws?.performance_drivers ?? [])].sort((a, b) => a.impact_points - b.impact_points).slice(0, 6);
  const people = (ws?.people_contribution_analysis?.rows ?? []).slice(0, 8);
  const slides: ReactNode[] = [];
  const R = (n: number) => opts.retry ? <button type="button" className="mp-btn" onClick={() => opts.retry!(n)}>Retry</button> : null;
  const gm = opts.gradeMixState ?? { status: 'ready' as const };

  slides.push(F(1, 'Title & scope', `${region} · Monthly performance · ${period.label}`, (
    <div className="mp-grid2">
      <div className="mp-card">
        <div className="mp-label">Scope</div>
        <p>Region <b>{code}</b> only. Functions: {REGION_FUNCTIONS[code].map((f) => f.name).join(', ')}.</p>
        <p>Teams: {data.teams.map((t) => t.team).join(' · ')}</p>
        {code === 'UAE' && <p className="mp-muted">Call Center is left out of the UAE deck for now.</p>}
      </div>
      <div className="mp-card">
        <div className="mp-label">Coverage</div>
        <p className="mp-big">{s ? `${s.analyzed_kpis} / ${s.expected_kpis} KPIs` : '—'}</p>
        <p>{fmtPct(s?.coverage_percent ?? null, 0)} coverage {s && (s.coverage_percent ?? 0) < 100 && <NoDataBadge label="Some KPIs: no data" />}</p>
        <p className="mp-muted">Comparison: {ws?.comparison?.current?.key ?? period.key}{ws?.comparison?.previous ? ` vs ${ws.comparison.previous.key}` : ' · previous month not available'}</p>
        <p className="mp-muted">Last complete month opens on the 5th of the following month.</p>
      </div>
    </div>
  )));

  slides.push(F(2, 'Team compliance', `Ready for present: ${counts.ready ?? 0} of ${data.teams.length} teams`, (
    <>
      <div className="mp-rule"><b>RULE v1</b> Ready = every critical KPI (weight ≥ 0.25) is ≥100% of target AND no open High-priority corrective action. Partial = no critical KPI below 70%, but one is 70–99.9% OR a High action is open. Not ready = any critical KPI below 70%. No data = a critical KPI has no value (not a miss).</div>
      <div className="mp-row mp-gap">
        <ReadyBadge status="ready" /> {counts.ready ?? 0} Ready <ReadyBadge status="partial" /> {counts.partial ?? 0} Partial
        <ReadyBadge status="not_ready" /> {counts.not_ready ?? 0} Not ready <ReadyBadge status="no_data" /> {counts.no_data ?? 0} No data
      </div>
      <div className="mp-cards">
        {data.teams.map((t) => (
          <div key={t.team} className={`mp-card mp-card-${t.status}`} data-testid={`ready-${t.team}`}>
            <div className="mp-label">{t.fn}</div><strong>{t.team}</strong>
            <div><ReadyBadge status={t.status} /></div><p className="mp-muted">{t.detail}</p>
          </div>
        ))}
      </div>
    </>
  )));

  const g = getGradeClassOrNull(story?.current_score);
  const mixTotal = data.gradeMix ? Object.values(data.gradeMix).reduce((a, b) => a + b, 0) : 0;
  const ov = ws?.kpi_overview;
  const ovNoData = ov ? Math.max(0, (s?.expected_kpis ?? ov.total_kpis) - ov.total_kpis) : 0;
  slides.push(F(3, 'Overall snapshot',
    story?.current_score != null ? `${region} at ${fmtPct(story.current_score)}${g ? ` (Grade ${g})` : ''}${mom != null ? `, ${mom >= 0 ? 'up' : 'down'} ${Math.abs(mom).toFixed(1)} pts on ${data.previousLabel ?? 'last month'}` : ''}` : `${region}: no score for ${period.label}`,
    (
      <div className="mp-grid-snap">
        <div className="mp-card mp-score" style={g ? { background: GRADE_PALETTE[g].background, borderColor: GRADE_PALETTE[g].border, color: GRADE_PALETTE[g].text } : undefined}>
          <div className="mp-label">Region weighted score</div>
          <div className="mp-hero">{fmtPct(story?.current_score ?? null)}</div>
          <GradeBadge score={story?.current_score} />
          <p>{mom != null ? <span className={toneClass(kpiMovementTone(mom, 'higher_better'))}>{movementArrow(mom)} {fmtPts(mom)} vs {data.previousLabel}</span> : <span className="mp-tone-neutral" data-testid="mom-na">→ MoM not available{story?.basis_context?.message ? ` — ${story.basis_context.message}` : ''}</span>}</p>
          <p className="mp-muted">Target {fmtPct(story?.target_score ?? null)} · gap {story?.gap_points != null ? fmtPts(story.gap_points) : '—'}</p>
          <p className="mp-muted">Coverage {s ? `${s.analyzed_kpis} / ${s.expected_kpis} KPIs (${fmtPct(s.coverage_percent, 0)})` : '—'}</p>
        </div>
        <div className="mp-stack">
          <div className="mp-card"><div className="mp-label">KPI status distribution · {ov?.total_kpis ?? 0} scored KPIs</div>
            {ov ? <Bar parts={[['On track', ov.on_track, '#0E8749'], ['At risk', ov.at_risk, '#A66800'], ['Critical', ov.critical, '#D92D20'], ['No data', ovNoData, 'hatch']]} /> : <NoDataBadge />}
          </div>
          <div className="mp-card"><div className="mp-label">Employee grade mix · {mixTotal} people</div>
            {gm.status === 'loading' ? <p className="mp-muted" role="status" data-testid="grade-mix-loading">Loading summary records…</p>
              : gm.status === 'error' ? <p className="mp-slide-error" role="alert" data-testid="grade-mix-error">Grade mix could not be loaded. {gm.message} {gm.retry && <button type="button" className="mp-btn" onClick={gm.retry}>Retry</button>}</p>
              : data.gradeMix && mixTotal ? <Bar parts={(['A', 'B', 'C', 'D', 'E'] as GradeClass[]).map((k) => [k, data.gradeMix![k], GRADE_PALETTE[k].solid])} /> : <NoDataBadge />}
            <p className="mp-muted mp-small">Counts employees; excludes Partial teams{data.gradeMixExcluded.length ? ` (${data.gradeMixExcluded.join(', ')})` : ''}. Ready rule v1.</p>
          </div>
          <div className="mp-card mp-card-soft"><div className="mp-label">Headline</div><p className="mp-lead">{story?.headline || 'Headline not available.'}</p></div>
        </div>
      </div>
    ),
    'Weighted score = Σ(KPI achievement × KPI weight) for this region only.'));

  slides.push(F(4, 'Weighted KPI drivers', 'What moved the score', diag.length ? (
    <table className="mp-table"><thead><tr><th>KPI</th><th>Weight</th><th>Actual vs target</th><th>Achievement</th><th>Status</th><th>Effect (pts)</th><th>Movement</th></tr></thead>
      <tbody>{[...diag].sort((a, b) => (a.effect_points ?? 0) - (b.effect_points ?? 0)).slice(0, 8).map((k) => {
        const drv = drivers.find((d) => d.driver === k.label || d.driver === k.key);
        const six = k.six_months ?? [];
        const prev = six.length > 1 ? six[six.length - 2]?.actual_value : null;
        const delta = k.actual != null && prev != null ? k.actual - prev : null;
        return (
          <tr key={k.key}><td><b>{k.label}</b>{isCriticalKpi(k) && <span className="mp-chip">critical</span>}</td><td>{fmtNum(k.weight, 2)}</td>
            <td>{fmtNum(k.actual)} vs {fmtNum(k.target)}{k.unit ? ` ${k.unit}` : ''}</td><td>{fmtPct(k.achievement_percent)}</td>
            <td><StatusBadge badge={kpiBadge(k.achievement_percent, k.actual)} /></td><td>{fmtNum(drv?.impact_points ?? k.effect_points)}</td>
            <td><Movement delta={delta} direction={k.direction ?? drv?.kpi_direction} suffix="" />{!k.direction && !drv?.kpi_direction && <span className="mp-chip">direction not set</span>}</td></tr>
        );
      })}</tbody></table>
  ) : <SlideEmpty title="No scored KPIs for this period" body={`The insights workspace returned no KPI diagnosis for ${region} · ${period.label}.`}>{R(4)}</SlideEmpty>, 'Arrow shows raw movement; color follows the KPI direction. Unknown direction stays grey.'));

  slides.push(
    <section key={5} id="s05" className="mp-slide mp-break" aria-label={`Slide 5 of ${SLIDE_COUNT}: Section break`} data-slide={5}>
      <header className="mp-slide-head"><span className="mp-pill mp-pill-n">05 / {SLIDE_COUNT}</span><div className="mp-row"><span className="mp-pill">{region}</span><span className="mp-pill mp-pill-lock" data-testid="period-lock">Period locked · {period.label}</span>{data.status === 'Final' && <span className="mp-pill mp-pill-frozen">Frozen</span>}</div></header>
      <h2 className="mp-break-title">Where the gap sits</h2><p>Functions, people and the actions in flight · {region} · {period.label}</p>
    </section>,
  );

  const fnCards = REGION_FUNCTIONS[code].map((fn) => {
    const rows = data.teams.filter((t) => t.fn === fn.name);
    const summaries = ws?.team_summaries ?? [];
    const gapShare = fn.teams.reduce((acc, t) => acc + (summaries.find((x) => x.team === t)?.gap_contribution_percent ?? 0), 0);
    const hasShare = fn.teams.some((t) => summaries.find((x) => x.team === t)?.gap_contribution_percent != null);
    return { fn, rows, gapShare: hasShare ? gapShare : null };
  }).sort((a, b) => (b.gapShare ?? -1) - (a.gapShare ?? -1));
  slides.push(F(6, 'Underperforming functions', fnCards[0]?.gapShare != null ? `${fnCards[0].fn.name} explains ${fmtNum(fnCards[0].gapShare, 0)}% of ${region}'s gap to target` : `Functions in ${region}`, (
    <div className="mp-grid2">{fnCards.map(({ fn, rows, gapShare }) => (
      <div key={fn.name} className="mp-card">
        <div className="mp-row mp-gap"><span className="mp-label">Function</span>{gapShare != null ? <span className="mp-muted">{fmtNum(gapShare, 0)}% of region gap</span> : <NoDataBadge label="Gap share not available" />}</div>
        <h3 className="mp-h3">{fn.name}</h3>
        <div className="mp-label">Teams in this function · responsible KPI</div>
        <table className="mp-table mp-table-compact"><tbody>{rows.map((t) => (
          <tr key={t.team}><td>↳ <b>{t.team}</b></td><td>{fmtPct(t.score)}</td><td><GradeBadge score={t.score} /></td>
            <td>{t.worstKpi ? <StatusBadge badge={kpiBadge(t.worstKpi.achievement_percent, t.worstKpi.actual)} /> : <NoDataBadge />}</td>
            <td className="mp-small">{t.worstKpi ? `${t.worstKpi.label} ${fmtNum(t.worstKpi.actual)} vs ${fmtNum(t.worstKpi.target)}` : '—'} <Movement delta={t.scoreChange} direction="higher_better" /></td></tr>
        ))}</tbody></table>
      </div>
    ))}</div>
  ), 'Functions are parent domains with teams nested. Severity: <70% achievement = Critical, 70–99.9% = At risk.'));

  slides.push(F(7, 'Affected people', ws?.people_contribution_analysis ? `People behind ${ws.people_contribution_analysis.kpi_label}` : 'Affected people', people.length ? (
    <table className="mp-table"><thead><tr><th>Person</th><th>Team</th><th>Level</th><th>Current vs target</th><th>Weighted impact</th><th>Status</th></tr></thead>
      <tbody>{people.map((p, i) => (
        <tr key={`${p.employee_id}-${i}`}><td><b>{data.mask(p.employee_name)}</b></td><td>{p.team}</td><td>{p.performance_level}</td>
          <td>{fmtNum(p.current_value)} vs {fmtNum(p.target_value)}</td><td>{fmtNum(p.weighted_impact, 2)}</td>
          <td>{p.classification === 'data_issue' ? <NoDataBadge /> : <span className={`mp-badge mp-badge-${p.classification === 'positive' ? 'on_track' : 'critical'}`}>{p.classification}</span>}</td></tr>
      ))}</tbody></table>
  ) : <SlideEmpty title="No people analysis for this period" body={`No people contribution analysis was returned for ${region} · ${period.label}.`}>{R(7)}</SlideEmpty>));

  const rows = [...data.actions].slice(0, 8);
  slides.push(F(8, 'Corrective actions', `${mix.open + mix.in_progress} actions in flight; ${mix.overdue} overdue for ${period.short}`, rows.length ? (
    <>
      <table className="mp-table"><thead><tr><th>Action</th><th>Owner</th><th>Status</th><th>Due</th><th>Linked KPI</th><th>Expected impact (owner note)</th></tr></thead>
        <tbody>{rows.map((a) => {
          const st = displayActionState(a, period.endDate); const rawNote = expectedImpact(a);
          const hidden = <NoDataBadge label={MASKED_DETAILS_LABEL} />;
          return (<tr key={a.id}><td>{data.masked ? hidden : <b>{a.title}</b>}{a.priority === 'High' && <span className="mp-chip">High</span>}</td><td>{data.mask(a.owner)}</td>
            <td><span className={`mp-badge mp-act-${st.replace(' ', '-').toLowerCase()}`}>{st}</span></td><td>{fmtDue(a.due_date)}</td><td>{a.linked_kpi_key ?? '—'}</td>
            <td>{data.masked ? hidden : rawNote ? <q>{rawNote}</q> : <NoDataBadge label="No note" />}</td></tr>);
        })}</tbody></table>
      <p className="mp-muted mp-small">Showing {rows.length} of {data.actions.length}. Overdue is measured against {period.endDate} (end of the locked month), not today.</p>
    </>
  ) : <SlideEmpty title={`No corrective actions recorded for ${region} · ${period.label}`}>{R(8)}<a className="mp-btn" href="/corrective-actions">Open Corrective Actions</a></SlideEmpty>,
  'Region-scoped follow-up. Expected impact is the owner\'s free-text note, quoted as written; it is not scored or summed.'));

  slides.push(F(9, 'Outlook', 'Outlook from the actions in flight', (
    <>
      <div className="mp-kpis">{([['Open', mix.open], ['In progress', mix.in_progress], ['Overdue', mix.overdue], ['Completed', mix.completed]] as const).map(([k, v]) => (
        <div key={k} className="mp-card"><div className="mp-label">{k}</div><div className="mp-big">{v}</div></div>))}</div>
      <div className={`mp-card ${mix.total ? 'mp-card-soft' : 'mp-card-not_ready'}`}><p className="mp-lead">{outlookLine(mix)}</p></div>
      <p className="mp-muted mp-small">Qualitative only: written from the status mix and due dates. No projected score.</p>
    </>
  )));

  slides.push(F(10, 'Decisions', 'Decisions and asks', (
    <>
      <div className="mp-row mp-gap"><span className="mp-label">Author</span> Regional Head · {region} (name not available from the API)</div>
      <SlideEmpty title="No decisions recorded" body="The repo has no decisions/asks entity yet; the regional head adds asks in the meeting. No numeric forecasts." />
      <div className="mp-card"><div className="mp-label">Owners available for asks</div><p>{data.owners.length ? data.owners.slice(0, 12).map((o) => data.mask(o.name)).join(' · ') : 'Not available'}</p></div>
    </>
  )));

  if (opts.appendix) slides.push(F(11, 'Appendix', 'How to read this deck', (
    <div className="mp-grid2">
      <div className="mp-card"><div className="mp-label">Direction legend</div>
        <p><span className="mp-tone-good">▲ green</span> = better for the KPI direction · <span className="mp-tone-bad">▼ red</span> = worse · <span className="mp-tone-neutral">→ grey</span> = flat or direction unknown.</p>
        <div className="mp-label">No data vs miss</div><p><NoDataBadge /> means no value for the period; it is never counted as a miss. <StatusBadge badge="critical" /> is a true miss.</p></div>
      <div className="mp-card"><div className="mp-label">Grade bands</div>
        <p>{(['A', 'B', 'C', 'D', 'E'] as GradeClass[]).map((k) => <span key={k} className="mp-badge" style={{ color: GRADE_PALETTE[k].text, background: GRADE_PALETTE[k].background, borderColor: GRADE_PALETTE[k].border }}>{k} · {GRADE_PALETTE[k].label}</span>)}</p>
        <div className="mp-label">Period lock</div><p>Every number is for {period.label} in {region} only. Reloads, present mode and print show the same values.</p></div>
    </div>
  )));
  return slides;
}

