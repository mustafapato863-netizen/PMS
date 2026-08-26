import './PageEnhancements.css';
import { useState, type CSSProperties, type ReactNode } from 'react';
import {
  Activity,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  Copy,
  Database,
  Filter,
  Gauge,
  Layers3,
  LayoutGrid,
  Search,
  ShieldCheck,
  Sparkles,
  Table2,
  Target,
  TrendingDown,
  TrendingUp,
  Users,
} from 'lucide-react';
import PerformanceKpiCard from '../components/common/PerformanceKpiCard';
import CustomDropdown from '../components/common/CustomDropdown';
import LineChart from '../components/balanced-scorecard/LineChart';
import './DesignSystemView.css';

type Token = {
  name: string;
  value: string;
  role: string;
  swatch: string;
  border?: string;
};

const tokens: Token[] = [
  { name: '--bg-base', value: '#F8FAFC', role: 'Application canvas', swatch: 'var(--bg-base)' },
  { name: '--bg-surface', value: '#FFFFFF', role: 'Cards and panels', swatch: 'var(--bg-surface)', border: 'var(--border-medium)' },
  { name: '--bg-sunken', value: '#F1F5F9', role: 'Inputs and table headers', swatch: 'var(--bg-sunken)' },
  { name: '--text-primary', value: '#0F172A', role: 'Headings and key values', swatch: 'var(--text-primary)' },
  { name: '--text-secondary', value: '#475569', role: 'Body and supporting labels', swatch: 'var(--text-secondary)' },
  { name: '--text-muted', value: '#64748B', role: 'Metadata and helper copy', swatch: 'var(--text-muted)' },
  { name: '--input-focus', value: '#3B82F6', role: 'Keyboard focus ring', swatch: 'var(--input-focus)' },
  { name: '--sidebar-active-text', value: '#1D4ED8', role: 'Selected navigation', swatch: 'var(--sidebar-active-text)' },
  { name: '--bsc-blue', value: '#2E6FE0', role: 'Financial / primary emphasis', swatch: 'var(--bsc-blue)' },
  { name: '--bsc-purple', value: '#7C5CE0', role: 'Customer / analysis emphasis', swatch: 'var(--bsc-purple)' },
  { name: '--bsc-green', value: '#1A9E72', role: 'Positive / measured state', swatch: 'var(--bsc-green)' },
  { name: '--bsc-orange', value: '#E0832E', role: 'Learning / attention state', swatch: 'var(--bsc-orange)' },
  { name: '--grade-a-text', value: '#0F8A4B', role: 'Exceeds target', swatch: 'var(--grade-a-text)' },
  { name: '--grade-c-text', value: '#B7791F', role: 'Average result', swatch: 'var(--grade-c-text)' },
  { name: '--grade-e-text', value: '#D92D20', role: 'Critical result', swatch: 'var(--grade-e-text)' },
];

const metricCards = [
  { label: 'Average score', value: '86.8%', note: 'Current period', accent: 'var(--bsc-blue)', icon: Gauge },
  { label: 'Employees at risk', value: '14', note: 'Needs manager review', accent: 'var(--bsc-orange)', icon: Users },
  { label: 'KPI coverage', value: '97.1%', note: '777 of 800 records', accent: 'var(--bsc-green)', icon: Activity },
];

const futureRecommendations = [
  { category: 'Analysis', name: 'KPI drilldown drawer', priority: 'High', icon: Gauge, why: 'Turn a score into a decision by showing the formula, target, source rows, six-month trend, and affected employees in one focused surface.', scope: 'KPI card → drawer → employee and trend details', building: 'PerformanceKpiCard + LineChart' },
  { category: 'Navigation', name: 'Role-aware filter bar', priority: 'High', icon: Filter, why: 'Keep the executive view compact while allowing region, team, level, position, and employee filters to reveal deeper analysis only when needed.', scope: 'Primary scope filters + More filters drawer + URL state', building: 'Filter row + dropdown menu + route state' },
  { category: 'Workflow', name: 'Corrective action quick drawer', priority: 'High', icon: ClipboardCheck, why: 'Let managers create, update, and review an action without leaving the roster or KPI analysis they are already using.', scope: 'Owner, due date, root cause, action text, status, and history', building: 'Glass panel + form fields + status badges' },
  { category: 'Data quality', name: 'Upload review panel', priority: 'High', icon: Database, why: 'Make imports safe by showing row errors, duplicate IDs, missing months, skipped records, and score calculation warnings before publishing data.', scope: 'Validation summary + row-level errors + downloadable report', building: 'Table + alert states + file status' },
  { category: 'Administration', name: 'Audit timeline', priority: 'Medium', icon: ShieldCheck, why: 'Give administrators a traceable history for uploads, recalculations, permission changes, and corrective-action edits.', scope: 'Actor, timestamp, event, scope, and before/after summary', building: 'Timeline + event badges + compact drawer' },
  { category: 'Reporting', name: 'Export job center', priority: 'Medium', icon: Table2, why: 'Make Excel, Word, and PDF exports predictable with progress, selected filters, retry, and a short download history.', scope: 'Format picker + progress + completed files + retry', building: 'Dropdown menu + progress state + action list' },
];

function Section({
  title,
  description,
  icon: Icon,
  children,
  className = '',
}: {
  title: string;
  description: string;
  icon: typeof Activity;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ds-section glass-panel ${className}`} aria-labelledby={`ds-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
      <header className="ds-section-head">
        <div className="ds-section-title">
          <span className="ds-section-icon" aria-hidden="true"><Icon size={17} /></span>
          <div>
            <h2 id={`ds-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>{title}</h2>
            <p>{description}</p>
          </div>
        </div>
        <span className="ds-source-tag">Used in product</span>
      </header>
      <div className="ds-section-body">{children}</div>
    </section>
  );
}

function DesignSystemView() {
  const [density, setDensity] = useState('Comfortable');
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [monthMenuOpen, setMonthMenuOpen] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState('All months');
  const [previewRegion, setPreviewRegion] = useState('All regions');
  const [previewMonth, setPreviewMonth] = useState('June 2026');

  const copyToken = async (token: Token) => {
    try {
      await navigator.clipboard?.writeText(`var(${token.name})`);
      setCopiedToken(token.name);
      window.setTimeout(() => setCopiedToken(null), 1200);
    } catch {
      setCopiedToken(null);
    }
  };

  return (
    <main className="ds-page" data-density={density.toLowerCase()}>
      <header className="ds-hero glass-panel">
        <div className="ds-hero-copy">
          <span className="text-label">Admin reference</span>
          <h1>SGH Hub design system</h1>
          <p>Production tokens and interaction patterns used across the performance workspace. This page documents the system we ship.</p>
          <div className="ds-hero-meta">
            <span><ShieldCheck size={14} /> Source: <code>Frontend/src/index.css</code></span>
            <span><Layers3 size={14} /> Light and dark tokens</span>
            <span><Sparkles size={14} /> Motion is state-led</span>
          </div>
        </div>
        <div className="ds-hero-art" aria-hidden="true">
          <div className="ds-hero-orb ds-hero-orb-blue animate-blob" />
          <div className="ds-hero-orb ds-hero-orb-indigo animate-blob animation-delay-2000" />
          <div className="ds-hero-orb ds-hero-orb-green animate-blob animation-delay-4000" />
          <div className="ds-hero-mark"><Activity size={30} /></div>
        </div>
      </header>

      <div className="ds-contract" role="note">
        <Check size={17} aria-hidden="true" />
        <div><strong>Current product contract.</strong> Use these shared tokens and existing classes before introducing a new visual treatment.</div>
      </div>

      <Section title="Color tokens" description="The actual semantic roles behind the SGH Hub light and dark themes." icon={LayoutGrid}>
        <div className="ds-token-layout">
          <div className="ds-token-grid">
            {tokens.map((token) => (
              <button type="button" className="ds-token" key={token.name} onClick={() => void copyToken(token)} title={`Copy ${token.name}`}>
                <span className="ds-token-swatch" style={{ background: token.swatch, borderColor: token.border || token.swatch }} aria-hidden="true" />
                <span className="ds-token-copy"><strong>{token.name}</strong><small>{token.role}</small><code>{copiedToken === token.name ? 'Copied' : token.value}</code></span>
                <Copy size={13} aria-hidden="true" />
              </button>
            ))}
          </div>
          <aside className="ds-token-note">
            <span className="text-label">Do</span>
            <h3>Reference the role, not a one-off hex.</h3>
            <p>Use <code>var(--text-primary)</code>, <code>var(--bg-surface)</code>, and the BSC perspective tokens so dark mode stays aligned automatically.</p>
            <div className="ds-surface-preview">
              <span className="ds-surface-dot" />
              <div><strong>Theme aware</strong><small>Switches with the app's <code>.dark</code> class</small></div>
            </div>
          </aside>
        </div>
      </Section>

      <div className="ds-two-column">
        <Section title="Typography and density" description="The hierarchy used by headers, dashboard cards, and data views." icon={Table2}>
          <div className="ds-type-stack">
            <div><span className="text-label">Heading 1</span><div className="heading-1">Team performance</div></div>
            <div><span className="text-label">Heading 2</span><div className="heading-2">Performance analysis</div></div>
            <div><span className="text-label">Body</span><p className="text-body">Use concise copy to explain what changed and what the user should do next.</p></div>
            <div><span className="text-label">Metadata</span><p className="text-small">June 2026 · Live measured data</p></div>
          </div>
          <div className="ds-density-control" aria-label="Density examples">
            <span>View density</span>
            {['Comfortable', 'Compact', 'Dense'].map((option) => (
              <button type="button" key={option} className={density === option ? 'is-active' : ''} aria-pressed={density === option} onClick={() => setDensity(option)}>{option}</button>
            ))}
          </div>
        </Section>

        <Section title="Surfaces and elevation" description="The real panel hierarchy used across the app." icon={Layers3}>
          <div className="ds-surface-stack">
            <div className="ds-surface-row glass-card"><span className="ds-surface-chip">glass-panel</span><div><strong>Page panel</strong><small>Blurred surface, subtle border, tinted shadow</small></div><ArrowUpRight size={15} /></div>
            <div className="ds-surface-row ds-raised-card"><span className="ds-surface-chip">glass-card</span><div><strong>Interactive card</strong><small>Hover lifts 2px and strengthens the border</small></div><ArrowUpRight size={15} /></div>
            <div className="ds-surface-row ds-sunken-card"><span className="ds-surface-chip">bg-sunken</span><div><strong>Input and table chrome</strong><small>Separates controls from the canvas</small></div><ArrowUpRight size={15} /></div>
          </div>
        </Section>
      </div>

      <Section title="Real component patterns" description="Small, reusable shapes taken from the live dashboards and settings screens." icon={ClipboardCheck}>
        <div className="ds-component-grid">
          <div className="ds-component-block ds-span-two">
            <div className="ds-block-head"><div><span className="text-label">Dashboard header</span><h3>Team performance</h3></div><button type="button" className="ds-icon-control" aria-label="More header options"><ChevronDown size={16} /></button></div>
            <div className="ds-filter-row">
              <label><span>Region</span><CustomDropdown value={previewRegion} options={['All regions', 'Offshore EGY', 'UAE Region']} onChange={setPreviewRegion} ariaLabel="Region filter preview" className="w-full" buttonClassName="w-full min-h-10 rounded-xl" size="lg" /></label>
              <label><span>Month</span><CustomDropdown value={previewMonth} options={['June 2026', 'May 2026']} onChange={setPreviewMonth} ariaLabel="Month filter preview" className="w-full" buttonClassName="w-full min-h-10 rounded-xl" size="lg" /></label>
              <button type="button" className="ds-filter-button"><Filter size={14} /> Filters <span>2</span></button>
            </div>
            <div className="ds-shell-search"><Search size={15} /><span>Search employees, teams, or actions</span><kbd>Ctrl K</kbd></div>
          </div>
          <div className="ds-component-block">
            <div className="ds-block-head"><div><span className="text-label">KPI card</span><h3>Metric hierarchy</h3></div><CircleHelp size={15} className="ds-muted-icon" /></div>
            <div className="ds-metric-list">
              {metricCards.map(({ label, value, note, accent, icon: Icon }) => <div className="ds-metric-card glass-card" key={label} style={{ '--metric-accent': accent } as CSSProperties}><span className="ds-metric-icon"><Icon size={16} /></span><span className="text-label">{label}</span><strong>{value}</strong><small>{note}</small></div>)}
            </div>
          </div>
          <div className="ds-component-block">
            <div className="ds-block-head"><div><span className="text-label">Sidebar selection</span><h3>Navigation states</h3></div><LayoutGrid size={15} className="ds-muted-icon" /></div>
            <nav className="ds-nav-preview" aria-label="Navigation state preview"><span><Activity size={15} /> Executive Summary</span><span className="is-selected"><Users size={15} /> All Teams <b>•</b></span><span><Table2 size={15} /> Reports</span><span><CircleHelp size={15} /> Insights</span></nav>
          </div>
          <div className="ds-component-block ds-dropdown-block">
            <div className="ds-block-head"><div><span className="text-label">Dropdown menu</span><h3>Month selection</h3></div><ChevronDown size={15} className="ds-muted-icon" /></div>
            <div className="ds-dropdown-preview">
              <button type="button" className={`ds-dropdown-trigger ${monthMenuOpen ? 'is-open' : ''}`} aria-haspopup="listbox" aria-expanded={monthMenuOpen} onClick={() => setMonthMenuOpen((open) => !open)}>
                <span><span className="ds-dropdown-leading"><CalendarDays size={15} /></span>{selectedMonth}</span><ChevronDown size={15} />
              </button>
              {monthMenuOpen && (
                <div className="ds-dropdown-menu" role="listbox" aria-label="Month options">
                  {['All months', 'January', 'February', 'March', 'April', 'May', 'June'].map((month) => (
                    <button type="button" role="option" aria-selected={selectedMonth === month} className={selectedMonth === month ? 'is-selected' : ''} key={month} onClick={() => { setSelectedMonth(month); setMonthMenuOpen(false); }}>
                      <span>{month}</span>{selectedMonth === month && <Check size={15} />}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <small className="ds-component-hint">Active option, checkmark, placement, and focus states are shared across filters.</small>
          </div>
        </div>
      </Section>

      <Section title="Score, KPI, neon and trend cards" description="The cards that carry performance decisions in Team Dashboard and Balanced Scorecard." icon={Gauge}>
        <div className="ds-card-showcase-grid">
          <div className="ds-score-card-wrap">
            <span className="text-label">Overall score card</span>
            <article className="ds-score-card glass-card">
              <div className="ds-score-card-top"><div><span className="text-label">Overall performance</span><strong>66.4%</strong></div><span className="pms-below">Needs attention</span></div>
              <div className="ds-score-card-meter"><span style={{ width: '66.4%' }} /></div>
              <div className="ds-score-card-foot"><span>Current<strong>66.4%</strong></span><span>Monthly change<strong className="ds-negative"><TrendingDown size={12} /> -1.6%</strong></span></div>
            </article>
          </div>
          <div className="ds-real-kpi-wrap">
            <span className="text-label">PerformanceKpiCard.tsx</span>
            <PerformanceKpiCard
              icon={Target}
              iconAccentColor="var(--bsc-blue)"
              label="Submission Within TAT %"
              value="91.7%"
              detailLabel="Higher is better"
              badgeText="On target"
              badgeType="success"
              trendDelta={1.7}
              progressPercent={91.7}
              contribution={30}
              weight={0.4}
              targetValue="70%"
            />
          </div>
          <div className="ds-trend-card-wrap ds-span-two">
            <div className="ds-trend-card glass-card">
              <div className="ds-block-head"><div><span className="text-label">TeamChartsSection.tsx</span><h3>Score Trend · Last 6 Months</h3></div><span className="ds-trend-chip"><TrendingUp size={13} /> +8.5% MoM</span></div>
              <LineChart history={[{ month: 'January', year: 2026, score: 61 }, { month: 'February', year: 2026, score: 68 }, { month: 'March', year: 2026, score: 74 }, { month: 'April', year: 2026, score: 71 }, { month: 'May', year: 2026, score: 78 }, { month: 'June', year: 2026, score: 83 }]} targetValue={80} color="#2E6FE0" height={170} />
            </div>
          </div>
          <div className="ds-neon-showcase ds-span-two">
            <div className="ds-neon-intro"><span className="text-label">BSC and workflow cards</span><h3>Neon is reserved for a decision focus</h3><p>Use the existing <code>--bsc-glow-*</code> shadows on hover or selection. Do not add glow to every card.</p></div>
            <div className="ds-neon-grid">
              <button type="button" className="ds-neon-card ds-neon-blue"><span className="ds-neon-icon"><Activity size={17} /></span><strong>Financial</strong><small>50.5% · Weighted score</small><ArrowUpRight size={15} /></button>
              <button type="button" className="ds-neon-card ds-neon-purple"><span className="ds-neon-icon"><Users size={17} /></span><strong>Customer</strong><small>42.9% · Weighted score</small><ArrowUpRight size={15} /></button>
              <button type="button" className="ds-neon-card ds-neon-green"><span className="ds-neon-icon"><ClipboardCheck size={17} /></span><strong>Internal process</strong><small>70.4% · Measured</small><ArrowUpRight size={15} /></button>
            </div>
          </div>
        </div>
      </Section>

      <div className="ds-two-column">
        <Section title="Status and grade vocabulary" description="Existing classes used for scorecards, risk, and account states." icon={ShieldCheck}>
          <div className="ds-badge-groups"><div><span className="text-label">Performance state</span><div className="ds-badge-row"><span className="status-badge status-exceeds">Exceeds</span><span className="status-badge status-meet">Meets</span><span className="status-badge status-average">Average</span><span className="status-badge status-pi">Below</span><span className="status-badge status-sip">Critical</span></div></div><div><span className="text-label">Grade</span><div className="ds-badge-row"><span className="grade-badge grade-A">A</span><span className="grade-badge grade-B">B</span><span className="grade-badge grade-C">C</span><span className="grade-badge grade-D">D</span><span className="grade-badge grade-E">E</span></div></div><div><span className="text-label">PMS decision</span><div className="ds-badge-row"><span className="pms-meet">On target</span><span className="pms-below">Below target</span><span className="pms-critical">Critical gap</span></div></div></div>
        </Section>
        <Section title="Data and feedback" description="Tables, filters, loading, and empty states share the same language." icon={Database}>
          <div className="ds-feedback-grid"><div className="ds-feedback-card"><span className="text-label">Loading</span><div className="ds-skeleton-stack"><span className="shimmer" /><span className="shimmer" /><span className="shimmer ds-skeleton-short" /></div><small>Use the existing <code>.shimmer</code> utility.</small></div><div className="ds-feedback-card ds-empty-feedback"><span className="text-label">Empty</span><Database size={22} /><strong>No performance data</strong><small>Explain the missing scope and next action.</small></div></div>
        </Section>
      </div>

      <Section title="Motion contract" description="Animation already used by SGH Hub. Each motion communicates hierarchy, feedback, or state." icon={Activity}>
        <div className="ds-motion-contract"><div className="ds-motion-item"><div className="ds-motion-orb animate-blob" /><div><strong>Ambient blob</strong><small><code>.animate-blob</code> · 12s ease-in-out. Adds depth to the app canvas.</small></div></div><div className="ds-motion-item"><div className="ds-motion-hover glass-card">Hover</div><div><strong>Card lift</strong><small><code>.glass-card:hover</code> · 180-300ms. Confirms an interactive surface.</small></div></div><div className="ds-motion-item"><div className="ds-motion-skeleton shimmer" /><div><strong>Skeleton shimmer</strong><small><code>.shimmer</code> · 1.6s. Signals data is loading.</small></div></div><div className="ds-motion-item"><div className="ds-motion-focus" tabIndex={0}>Focus me</div><div><strong>Focus-visible</strong><small>Uses <code>--input-focus</code> so keyboard navigation stays clear.</small></div></div></div><div className="ds-reduced-motion"><Check size={14} /> Reduced motion removes transforms, shimmer, and ambient movement while preserving state and focus.</div>
      </Section>

      <Section title="Recommended future components" description="Practical additions selected for SGH Hub's next analysis, workflow, data-quality, and reporting journeys." icon={Layers3}>
        <div className="ds-recommendation-intro">
          <div><span className="text-label">Recommended sequence</span><h3>Make analysis, action, and data quality easier to reach.</h3><p>These are not empty slots. Each recommendation has a clear user problem, a suggested scope, and a reuse path through the components already documented above.</p></div>
          <span className="ds-roadmap-count">{futureRecommendations.length} candidates</span>
        </div>
        <div className="ds-recommendation-grid">
          {futureRecommendations.map(({ category, name, priority, icon: Icon, why, scope, building }) => (
            <article className="ds-recommendation-card" key={name}>
              <div className="ds-recommendation-top"><span className="ds-recommendation-icon"><Icon size={16} /></span><span className={`ds-priority ds-priority-${priority.toLowerCase()}`}>{priority}</span></div>
              <span className="ds-recommendation-category">{category}</span>
              <h3>{name}</h3>
              <p>{why}</p>
              <div className="ds-recommendation-scope"><strong>Suggested scope</strong><span>{scope}</span></div>
              <small><Layers3 size={12} /> Reuses <code>{building}</code></small>
            </article>
          ))}
        </div>
      </Section>

      <footer className="ds-footer"><span><ShieldCheck size={15} /> Admin-only reference page</span><span><code>index.css</code> is the source of truth</span><span>New components must use these roles first.</span></footer>
    </main>
  );
}

export default DesignSystemView;
