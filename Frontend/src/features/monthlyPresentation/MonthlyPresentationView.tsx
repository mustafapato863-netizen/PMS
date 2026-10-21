import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import {
  REGION_FUNCTIONS, REGION_LABEL, SLIDE_COUNT, accessibleRegions, buildDeckSearch, gradeMix, isMonthAvailable, lastCompleteMonth,
  nameMasker, opensOn, parseDeckParams, pdfFileName, periodFromKey, periodRegionActions, openHighCount, regionCode, regionSlug,
  shiftMonth, teamReadiness, kpiBadge, isCriticalKpi, canReopenDraft, filterRegionRows, type DeckStatus, type RegionCode, type RegionSlug,
} from './model';
import { MP_QUERY_ROOT, useMonthlyPresentationData } from './useMonthlyPresentationData';
import { buildSlides } from './buildSlides';
import { NoDataBadge } from './SlideParts';
import type { DeckData, TeamReady } from './deckTypes';
import './monthlyPresentation.css';

export default function MonthlyPresentationView({ today = new Date() }: { today?: Date }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const { role } = useUserRole();
  const params = parseDeckParams(location.search, location.hash);
  const allowed = useMemo(() => accessibleRegions({ role, accessible_regions: currentUser?.accessible_regions }), [role, currentUser?.accessible_regions]);
  const defaultMonth = lastCompleteMonth(today);
  const search = new URLSearchParams(location.search);
  const mask = search.get('mask') === '1';
  const appendix = search.get('appendix') !== '0';
  const footer = search.get('footer') !== '0';
  const bands = search.get('bands') !== '0';

  // Month lock: region + month always live in the URL (written on first load).
  useEffect(() => {
    if (params.region && params.month) return;
    const region = params.region ?? (allowed[0] ? regionSlug(allowed[0]) : 'egy');
    navigate({ search: buildDeckSearch(location.search, { region, month: params.month ?? defaultMonth }), hash: location.hash }, { replace: true });
  }, [params.region, params.month, allowed, defaultMonth, location.search, location.hash, navigate]);

  const code: RegionCode | null = params.region ? regionCode(params.region) : null;
  const period = periodFromKey(params.month);
  const canSee = Boolean(code && allowed.includes(code));
  const available = Boolean(period && isMonthAvailable(period.key, today));
  const q = useMonthlyPresentationData(code, period, canSee && available);

  // Draft/Final: there is no endpoint to persist Final, so the deck stays Draft (see PR notes).
  const status: DeckStatus = 'Draft';

  const switchRegion = useCallback((slug: RegionSlug) => {
    if (slug === params.region) return;
    queryClient.removeQueries({ queryKey: [MP_QUERY_ROOT] }); // regions are never mixed: drop every cached slide.
    navigate({ search: buildDeckSearch(location.search, { region: slug }) });
  }, [params.region, queryClient, navigate, location.search]);
  const setMonth = useCallback((key: string) => {
    navigate({ search: buildDeckSearch(location.search, { month: key }) });
  }, [navigate, location.search]);
  const setMode = useCallback((next: { present?: boolean; print?: boolean }, extra?: Record<string, string>) => {
    let s = buildDeckSearch(location.search, next);
    if (extra) { const p = new URLSearchParams(s); Object.entries(extra).forEach(([k, v]) => p.set(k, v)); s = `?${p}`; }
    navigate({ search: s, hash: location.hash });
  }, [navigate, location.search, location.hash]);

  const deck: DeckData | null = useMemo(() => {
    if (!code || !period) return null;
    const ws = q.workspace.data;
    const actions = periodRegionActions(q.followUp.data ?? [], code, period);
    const fnOf = (team: string) => REGION_FUNCTIONS[code].find((f) => f.teams.includes(team))?.name ?? '';
    const teams: TeamReady[] = q.teamDiagnosis.map(({ team, query }) => {
      const diag = query.data?.kpi_diagnosis ?? [];
      const high = openHighCount(actions, team);
      const r = teamReadiness(diag.map((k) => ({ key: k.key, label: k.label, weight: k.weight, actual: k.actual, achievement_percent: k.achievement_percent })), high);
      const summary = (ws?.team_summaries ?? []).find((t) => t.team === team) ?? query.data?.team_summaries?.find((t) => t.team === team);
      const crit = diag.filter(isCriticalKpi);
      const worst = [...diag].filter((k) => k.achievement_percent != null).sort((a, b) => a.achievement_percent! - b.achievement_percent!)[0] ?? null;
      const green = crit.filter((k) => kpiBadge(k.achievement_percent, k.actual) === 'on_track').length;
      const detail = query.isError ? 'KPI data could not be loaded' : !crit.length ? 'No critical KPI scored for the period'
        : r.status === 'no_data' ? `A critical KPI has no value for ${period.short}` : `Critical KPIs ${green}/${crit.length} green · ${high} open High action${high === 1 ? '' : 's'}`;
      return { team, fn: fnOf(team), status: query.isError ? 'no_data' : r.status, detail, score: summary?.current_score ?? null, scoreChange: summary?.score_change ?? null, worstKpi: worst };
    });
    const partial = teams.filter((t) => t.status === 'partial').map((t) => t.team);
    const recs = q.records.data
      ? filterRegionRows(code, q.records.data).filter((r) => r.month.toLowerCase() === period.monthName.toLowerCase() && (r.year == null || r.year === period.year))
      : null;
    const prev = ws?.comparison?.previous ? periodFromKey(ws.comparison.previous.key) ?? null : null;
    return {
      code, period, status, ws, teams, actions,
      previousLabel: prev ? `${prev.short} ${prev.year}` : (ws?.comparison?.previous?.month ?? null),
      gradeMix: recs ? gradeMix(recs, partial) : null, gradeMixExcluded: partial,
      owners: q.owners.data ?? [], mask: mask ? nameMasker() : (n) => String(n ?? '').trim() || '—',
    };
  }, [code, period, q.workspace.data, q.followUp.data, q.teamDiagnosis, q.records.data, q.owners.data, mask, status]);

  const insightsHref = code && period ? `/insights?region=${code}&month=${period.short}&year=${period.year}` : '/insights';
  const noMonthData = q.workspace.data && (q.workspace.data.summary?.analyzed_kpis ?? 0) === 0;
  const slides = deck && q.workspace.data && !noMonthData ? buildSlides(deck, insightsHref, { appendix: params.print ? appendix : true }) : [];

  // Print: title = PDF file name, then open the print dialog once data is in.
  useEffect(() => {
    if (!params.print || !code || !period) return;
    const previous = document.title;
    document.title = pdfFileName(code, period.key).replace(/\.pdf$/, '');
    document.documentElement.classList.add('mp-printing');
    return () => { document.title = previous; document.documentElement.classList.remove('mp-printing'); };
  }, [params.print, code, period]);
  const printedRef = useRef(false);
  useEffect(() => {
    if (params.print && slides.length && !printedRef.current && search.get('autoprint') === '1') {
      printedRef.current = true;
      window.setTimeout(() => window.print(), 400);
    }
  });

  // Anchor deep link (#s01..#s11) on the normal page.
  useEffect(() => {
    if (!params.present && params.slide && slides.length) document.getElementById(`s${String(params.slide).padStart(2, '0')}`)?.scrollIntoView();
  }, [params.present, params.slide, slides.length]);

  let content: React.ReactNode;
  if (!code || !period) content = null;
  else if (!canSee) content = (
    <Empty title={`You don't have access to ${REGION_LABEL[code]}`} body={allowed.length ? `Your account can open ${allowed.map((r) => REGION_LABEL[r]).join(' and ')} only. Ask a PMS Admin for access to another region.` : 'Your account has no region assigned. Ask a PMS Admin for access.'} />
  );
  else if (!available) content = (
    <Empty title={`${period.label} is not yet available`} body={`Monthly data is complete on the 5th of the following month. ${period.label} opens on ${opensOn(period.key)}. The last complete month is ${periodFromKey(defaultMonth)!.label}.`}>
      <button type="button" className="mp-btn" onClick={() => setMonth(defaultMonth)}>Open {periodFromKey(defaultMonth)!.label}</button>
    </Empty>
  );
  else if (q.workspace.isLoading) content = <div className="mp-empty" role="status">Loading {REGION_LABEL[code]} · {period.label}…</div>;
  else if (q.workspace.isError) content = <Empty title="The deck could not be loaded" body="Insights workspace request failed. Nothing is shown rather than partial numbers." />;
  else if (noMonthData) content = (
    <Empty title={`No ${period.label} data for ${REGION_LABEL[code]} yet`} body="No scored records for the locked period. Ready cannot be computed, so every team shows No data.">
      <button type="button" className="mp-btn" onClick={() => setMonth(shiftMonth(period.key, -1))}>Switch period to {periodFromKey(shiftMonth(period.key, -1))!.label}</button>
      <div className="mp-row mp-gap"><NoDataBadge /> {REGION_FUNCTIONS[code].flatMap((f) => f.teams).join(' · ')}</div>
    </Empty>
  );
  else content = slides;

  if (params.present && slides.length && deck) {
    return createPortal(<div className="mp-portal"><PresentMode slides={slides} start={params.slide ?? 1} onExit={() => setMode({ present: false })} label={`${REGION_LABEL[deck.code]} · ${deck.period.label}`} /></div>, document.body);
  }

  const page = (
    <div className={`mp-root ${params.print ? 'mp-print' : ''} ${bands ? 'mp-bands' : ''}`} data-region={code ?? ''}>
      {!params.print && code && period && (
        <Toolbar code={code} period={period.key} allowed={allowed} today={today} status={status} role={role}
          onRegion={switchRegion} onMonth={setMonth} canPresent={slides.length > 0}
          onPresent={() => setMode({ present: true })}
          onExport={(o) => setMode({ print: true }, { mask: o.mask ? '1' : '0', bands: o.bands ? '1' : '0', appendix: o.appendix ? '1' : '0', footer: o.footer ? '1' : '0', autoprint: '1' })}
        />
      )}
      {params.print && (
        <div className="mp-print-bar mp-noprint"><button type="button" className="mp-btn" onClick={() => window.print()}>Print / Save PDF</button>
          <button type="button" className="mp-btn mp-btn-ghost" onClick={() => setMode({ print: false })}>Back to deck</button></div>
      )}
      <div className="mp-slides">{content}</div>
      {params.print && code && period && footer && (
        <div className="mp-print-footer">{REGION_LABEL[code]} · Period locked · {period.label} · {status}{mask ? ' · Names masked' : ''} · {`${window.location.origin}/monthly-presentation?region=${regionSlug(code)}&month=${period.key}`}</div>
      )}
    </div>
  );
  return params.print ? createPortal(<div className="mp-portal mp-portal-print">{page}</div>, document.body) : page;
}

function Empty({ title, body, children }: { title: string; body?: string; children?: React.ReactNode }) {
  return <div className="mp-empty" role="status"><div className="mp-hatch mp-hatch-icon" aria-hidden /><strong>{title}</strong>{body && <p>{body}</p>}{children}</div>;
}

function Toolbar({ code, period, allowed, today, status, role, onRegion, onMonth, onPresent, onExport, canPresent }: {
  code: RegionCode; period: string; allowed: RegionCode[]; today: Date; status: DeckStatus; role: string | null | undefined;
  onRegion: (s: RegionSlug) => void; onMonth: (k: string) => void; onPresent: () => void; onExport: (o: ExportOptions) => void; canPresent: boolean;
}) {
  const [exportOpen, setExportOpen] = useState(false);
  const last = lastCompleteMonth(today);
  const next = shiftMonth(last, 1);
  const months = Array.from({ length: 12 }, (_, i) => shiftMonth(last, -i));
  if (!months.includes(period) && period <= last) months.push(period);
  return (
    <div className="mp-toolbar" role="toolbar" aria-label="Monthly presentation controls">
      <div><div className="mp-tb-title">SGH Hub · Monthly Presentation</div><div className="mp-tb-url">/monthly-presentation?region={regionSlug(code)}&month={period}</div></div>
      {allowed.length > 1 ? (
        <div className="mp-seg" role="radiogroup" aria-label="Region">
          {(['EGY', 'UAE'] as RegionCode[]).map((r) => (
            <button key={r} type="button" role="radio" aria-checked={r === code} className={r === code ? 'is-on' : ''} onClick={() => onRegion(regionSlug(r))}>{REGION_LABEL[r]}</button>
          ))}
        </div>
      ) : <span className="mp-pill" data-testid="region-pill">{REGION_LABEL[allowed[0] ?? code]}</span>}
      <label className="mp-period"><span className="mp-label">Period · locked</span>
        <select aria-label="Locked period" value={period} onChange={(e) => onMonth(e.target.value)}>
          <option value={next} disabled>{periodFromKey(next)!.label} · opens {opensOn(next)} (not yet available)</option>
          {months.map((k) => <option key={k} value={k}>{periodFromKey(k)!.label}{k === last ? ' · last complete' : ''}</option>)}
        </select>
        <span className="mp-muted mp-small">Last complete · {periodFromKey(next)!.short} opens {opensOn(next)}</span>
      </label>
      <div className="mp-deck-status"><span className="mp-label">Deck</span> <b>{status}</b>
        <button type="button" className="mp-linkbtn" disabled aria-disabled title="Persisting Final needs a backend endpoint that does not exist yet. Reopen as Draft would be Admin-only.">· Mark Final</button>
        {status === 'Final' && canReopenDraft(role) && <button type="button" className="mp-linkbtn">Reopen as Draft</button>}
      </div>
      <div className="mp-tb-actions">
        <div className="mp-pop-wrap">
          <button type="button" className="mp-btn mp-btn-ghost" aria-haspopup="dialog" aria-expanded={exportOpen} disabled={!canPresent} onClick={() => setExportOpen((v) => !v)}>Export PDF ▾</button>
          {exportOpen && <ExportDialog code={code} period={period} status={status} onCancel={() => setExportOpen(false)} onExport={(o) => { setExportOpen(false); onExport(o); }} />}
        </div>
        <button type="button" className="mp-btn" onClick={onPresent} disabled={!canPresent}>Present ▸</button>
      </div>
    </div>
  );
}

export interface ExportOptions { mask: boolean; bands: boolean; appendix: boolean; footer: boolean }
export function ExportDialog({ code, period, status, onCancel, onExport }: { code: RegionCode; period: string; status: DeckStatus; onCancel: () => void; onExport: (o: ExportOptions) => void }) {
  const [o, setO] = useState<ExportOptions>({ mask: true, bands: true, appendix: false, footer: true });
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.querySelector('input')?.focus(); }, []);
  const opt = (k: keyof ExportOptions, label: string) => (
    <label className="mp-check"><input type="checkbox" checked={o[k]} onChange={(e) => setO({ ...o, [k]: e.target.checked })} /> {label}</label>
  );
  return (
    <div ref={ref} className="mp-pop" role="dialog" aria-modal="false" aria-label="Export PDF" onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); }}>
      <h3>Export PDF</h3>
      <p className="mp-muted">{REGION_LABEL[code]} · {periodFromKey(period)!.label} · {status}</p>
      {opt('mask', 'Mask names (Person A, B, …)')}
      {opt('bands', 'Section breaks as thin bands')}
      {opt('appendix', 'Include appendix (slide 11)')}
      {opt('footer', 'Footer: freshness + period lock')}
      <p className="mp-muted mp-small">A4 landscape · one PDF for the selected region only · {pdfFileName(code, period)}</p>
      <div className="mp-row mp-end"><button type="button" className="mp-btn mp-btn-ghost" onClick={onCancel}>Cancel</button><button type="button" className="mp-btn" onClick={() => onExport(o)}>Export PDF</button></div>
    </div>
  );
}

export function PresentMode({ slides, start, onExit, label }: { slides: React.ReactNode[]; start: number; onExit: () => void; label: string }) {
  const [i, setI] = useState(Math.min(Math.max(start, 1), slides.length) - 1);
  const [hint, setHint] = useState(true);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  const [activity, setActivity] = useState(0);
  useEffect(() => { const t = window.setTimeout(() => setHint(false), 3000); return () => window.clearTimeout(t); }, [i, activity]);
  const wake = () => { setHint(true); setActivity((n) => n + 1); };
  useEffect(() => { window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}#s${String(i + 1).padStart(2, '0')}`); }, [i]);
  const onKey = (e: React.KeyboardEvent) => {
    const last = slides.length - 1;
    const map: Record<string, () => number> = {
      ArrowRight: () => Math.min(i + 1, last), ArrowDown: () => Math.min(i + 1, last), PageDown: () => Math.min(i + 1, last), ' ': () => Math.min(i + 1, last),
      ArrowLeft: () => Math.max(i - 1, 0), ArrowUp: () => Math.max(i - 1, 0), PageUp: () => Math.max(i - 1, 0), Home: () => 0, End: () => last,
    };
    if (e.key === 'Escape') { e.preventDefault(); onExit(); return; }
    if (map[e.key]) { e.preventDefault(); setI(map[e.key]()); wake(); }
  };
  return (
    <div ref={ref} className="mp-present" tabIndex={0} role="region" aria-roledescription="presentation" aria-label={`Presentation · ${label}`} onKeyDown={onKey} onMouseMove={wake}>
      <div className="mp-present-stage" aria-live="polite">{slides[i]}</div>
      <div className={`mp-present-hint ${hint ? 'is-on' : ''}`}>
        <span>{String(i + 1).padStart(2, '0')} / {SLIDE_COUNT}</span>
        <div className="mp-progress" role="progressbar" aria-valuemin={1} aria-valuemax={slides.length} aria-valuenow={i + 1}><span style={{ width: `${((i + 1) / slides.length) * 100}%` }} /></div>
        <span className="mp-keys"><kbd>← →</kbd> prev / next <kbd>PgUp PgDn</kbd> prev / next <kbd>Space</kbd> next <kbd>Home End</kbd> first / last <kbd>Esc</kbd> exit</span>
        <button type="button" className="mp-linkbtn" onClick={onExit}>Exit</button>
      </div>
    </div>
  );
}
