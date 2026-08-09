import { Fragment, useState, type ButtonHTMLAttributes, type ReactNode } from 'react';
import {
  AlertCircle,
  ArrowDown,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Download,
  FileUp,
  Info,
  Lock,
  MoreHorizontal,
  Palette,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import './DesignSystemView.css';

type ButtonVariant = 'primary' | 'secondary' | 'success' | 'danger' | 'ghost';

interface LabCardProps {
  title: string;
  description: string;
  badge?: string;
  children: ReactNode;
  className?: string;
}

const tokenSwatches = [
  { label: 'Canvas', note: 'page background', color: '#F8FAFC' },
  { label: 'Ink 950', note: 'primary text', color: '#0F172A' },
  { label: 'Action', note: 'primary CTA', color: '#2563EB' },
  { label: 'Action hover', note: 'hover and focus', color: '#1D4ED8' },
  { label: 'Neon cyan', note: 'focus edge', color: '#22D3EE' },
  { label: 'Decision', note: 'risk and attention', color: '#C2410C' },
  { label: 'Ready', note: 'success outcome', color: '#15803D' },
  { label: 'Danger', note: 'destructive action', color: '#B91C1C' },
];

const tableRows = [
  { id: 'ahmed', name: 'Ahmed Mahmoud', team: 'Inbound', status: 'On track', score: '87%', owner: 'LM' },
  { id: 'lina', name: 'Lina Samir', team: 'Marketing', status: 'Review', score: '74%', owner: 'RK' },
  { id: 'omar', name: 'Omar Khaled', team: 'Sales', status: 'Needs action', score: '61%', owner: 'AM' },
];

const pipelineColumns = [
  {
    title: 'Data intake',
    count: '4 records',
    limit: 'WIP 6',
    tone: 'blue',
    cards: [
      { initials: 'DR', name: 'Diego Ruiz', detail: 'April scorecard import', status: 'New', statusTone: 'new' },
    ],
    footer: 'Drop a file to begin',
  },
  {
    title: 'Validation',
    count: '3 records',
    limit: 'WIP 4',
    tone: 'violet',
    cards: [
      { initials: 'LS', name: 'Lina Samir', detail: 'KPI evidence check', status: 'Review', statusTone: 'review' },
    ],
    footer: '',
  },
  {
    title: 'Manager review',
    count: '2 records',
    limit: 'WIP 3',
    tone: 'orange',
    cards: [
      { initials: 'SM', name: 'Sofia Marin', detail: 'Scorecard ready for review', status: 'Focus', statusTone: 'focus', priority: 'Needs decision' },
      { initials: 'PN', name: 'Priya Nair', detail: 'Monthly performance notes', status: 'Review', statusTone: 'review' },
    ],
    footer: '',
  },
  {
    title: 'Approved',
    count: '1 record',
    limit: 'WIP 2',
    tone: 'green',
    cards: [
      { initials: 'MI', name: 'Mona Ibrahim', detail: 'Development plan approved', status: 'Ready', statusTone: 'ready' },
    ],
    footer: '',
  },
  {
    title: 'Archived',
    count: '8 records',
    limit: 'WIP -',
    tone: 'slate',
    cards: [
      { initials: 'OK', name: 'Omar Khaled', detail: 'Closed action plan', status: 'Closed', statusTone: 'closed' },
    ],
    footer: '+3 more records',
  },
];

const interviewDays = [
  { day: 'MON', date: '10', count: '4 reviews' },
  { day: 'TUE', date: '11', count: '3 reviews', today: true },
  { day: 'WED', date: '12', count: '2 reviews' },
  { day: 'THU', date: '13', count: '4 reviews' },
  { day: 'FRI', date: '14', count: '1 review' },
];

const interviewEvents: Record<string, { tone: string; name: string; detail: string } | undefined> = {
  '09:00-0': { tone: 'blue', name: 'Sofia Marin', detail: 'Manager review' },
  '09:00-2': { tone: 'violet', name: 'Priya Nair', detail: 'KPI review' },
  '09:00-3': { tone: 'orange', name: 'Diego Ruiz', detail: 'Conflict' },
  '10:00-1': { tone: 'green', name: 'Mona Ibrahim', detail: 'Action review' },
  '10:00-4': { tone: 'violet', name: 'Sofia Marin', detail: 'Debrief' },
  '11:00-2': { tone: 'blue', name: 'Mona Ibrahim', detail: 'Planning session' },
  '12:00-4': { tone: 'green', name: 'Amina Youssef', detail: 'Data intake' },
};

function LabCard({ title, description, badge, children, className = '' }: LabCardProps) {
  const headingId = 'design-system-' + title.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  return (
    <section className={'ds-card ' + className} aria-labelledby={headingId}>
      <div className="ds-card-head">
        <div>
          <h2 id={headingId}>{title}</h2>
          <p>{description}</p>
        </div>
        {badge && <span className="ds-badge ds-badge-blue">{badge}</span>}
      </div>
      <div className="ds-card-body">{children}</div>
    </section>
  );
}

function DemoButton({
  variant = 'secondary',
  size = '',
  className = '',
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: 'small' | '';
}) {
  return (
    <button
      type="button"
      className={'ds-btn ds-btn-' + variant + (size ? ' ds-btn-small' : '') + (className ? ' ' + className : '')}
      {...props}
    >
      {children}
    </button>
  );
}

function IconButton({
  label,
  children,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      className={'ds-icon-btn' + (className ? ' ' + className : '')}
      aria-label={label}
      {...props}
    >
      {children}
    </button>
  );
}

function Avatar({ initials, size = 'medium' }: { initials: string; size?: 'small' | 'medium' | 'large' }) {
  return <span className={'ds-avatar ds-avatar-' + size}>{initials}</span>;
}

function DesignSystemView() {
  const [density, setDensity] = useState('Comfortable');
  const [selectedTab, setSelectedTab] = useState('Overview');
  const [selectedSegment, setSelectedSegment] = useState('Board');
  const [selectedRows, setSelectedRows] = useState<string[]>(['ahmed']);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [activeSavedView, setActiveSavedView] = useState('My workspace');
  const [filters, setFilters] = useState(['Team: All', 'Month: June']);
  const [modalOpen, setModalOpen] = useState(true);
  const [menuOpen, setMenuOpen] = useState(true);
  const [selectedDate, setSelectedDate] = useState('12');
  const [selectedTime, setSelectedTime] = useState('10:00');
  const [score, setScore] = useState(5);
  const [recommendation, setRecommendation] = useState('Strong result');
  const [calendarView, setCalendarView] = useState('Week');

  const allRowsSelected = selectedRows.length === tableRows.length;

  const toggleRow = (id: string) => {
    setSelectedRows((current) => current.includes(id)
      ? current.filter((rowId) => rowId !== id)
      : [...current, id]);
  };

  const toggleAllRows = () => {
    setSelectedRows(allRowsSelected ? [] : tableRows.map((row) => row.id));
  };

  return (
    <div className="ds-lab">
      <header className="ds-page-head">
        <div>
          <div className="ds-eyebrow">PMS Workspace</div>
          <h1>Design System Laboratory</h1>
          <p>Reusable surfaces for the performance workspace. Each example documents hierarchy, state, density, and responsive behavior.</p>
        </div>
        <div className="ds-page-actions">
          <DemoButton><Download size={14} /> Export tokens</DemoButton>
          <DemoButton variant="primary"><Palette size={14} /> View page recipes</DemoButton>
        </div>
      </header>

      <div className="ds-callout" role="note">
        <ShieldCheck size={18} aria-hidden="true" />
        <div><strong>Admin reference contract:</strong> use the same token, state, grid recipe, and access rule on every page. This laboratory is visible only to Admin users.</div>
      </div>

      <div className="ds-grid ds-grid-3 ds-lab-section">
        <LabCard title="Color roles" description="Semantic roles, not page-specific colors.">
          <div className="ds-token-grid">
            {tokenSwatches.map((token) => (
              <div className="ds-token-swatch" key={token.label}>
                <span style={{ backgroundColor: token.color }} aria-hidden="true" />
                <div><strong>{token.label}</strong><small>{token.note}</small></div>
              </div>
            ))}
          </div>
        </LabCard>

        <LabCard title="Typography and density" description="Readable enterprise hierarchy with predictable density.">
          <div className="ds-type-sample">
            <h3>Heading 1. Executive summary</h3>
            <h4>Heading 2. Section title</h4>
            <h5>Heading 3. Panel title</h5>
            <p>Body copy stays readable at 14px with a 1.5 line height. Metadata is quieter but never disappears.</p>
            <small>Caption. 12px. Labels use uppercase sparingly.</small>
          </div>
          <div className="ds-density-row" aria-label="Density examples">
            {['Comfortable', 'Compact', 'Dense'].map((option) => (
              <button type="button" key={option} className={density === option ? 'is-selected' : ''} aria-pressed={density === option} onClick={() => setDensity(option)}>{option}</button>
            ))}
          </div>
        </LabCard>

        <LabCard title="Gradient policy" description="A gradient signals hierarchy. It never replaces readable structure.">
          <div className="ds-gradient-samples">
            <div className="ds-gradient-sample ds-gradient-canvas">Canvas atmosphere</div>
            <div className="ds-gradient-sample ds-gradient-action">Primary action</div>
            <div className="ds-gradient-sample ds-gradient-selection">Selected navigation</div>
            <div className="ds-gradient-sample ds-gradient-neon">Focus accent</div>
          </div>
        </LabCard>
      </div>

      <LabCard title="12-column grid recipes" description="Every page declares a max width, gutter, columns, gap, and collapse rule." badge="Layout foundation" className="ds-lab-section">
        <div className="ds-grid-recipe">
          <div className="ds-grid-recipe-meta"><strong>Desktop</strong><span>1440px. max 1720px. 12 columns. 24px gap. 32px gutter.</span></div>
          <div className="ds-layout-grid ds-layout-desktop">{Array.from({ length: 12 }, (_, index) => <span key={index}>{index + 1}</span>)}</div>
          <div className="ds-grid-recipe-meta"><strong>Tablet</strong><span>768-1199px. 8 columns. 20px gap. 24px gutter.</span></div>
          <div className="ds-layout-grid ds-layout-tablet">{Array.from({ length: 8 }, (_, index) => <span key={index}>{index + 1}</span>)}</div>
          <div className="ds-grid-recipe-meta"><strong>Phone</strong><span>375-767px. 4 columns. 16px gap. 16px gutter. Stack main and aside.</span></div>
          <div className="ds-layout-grid ds-layout-phone">{Array.from({ length: 4 }, (_, index) => <span key={index}>{index + 1}</span>)}</div>
          <div className="ds-recipe-tiles">
            <div><strong>Dashboard</strong><small>6 metric cards, then 8/4 main-side, then supporting cards.</small></div>
            <div><strong>List and inbox</strong><small>Toolbar plus full-width table. No nested horizontal scroll.</small></div>
            <div><strong>Detail</strong><small>Evidence column with a decision rail.</small></div>
            <div><strong>Wizard</strong><small>Form column with a readiness rail.</small></div>
          </div>
        </div>
      </LabCard>

      <div className="ds-grid ds-grid-2 ds-lab-section">
        <LabCard title="Stat cards and focus treatment" description="Use the neon treatment for one decision-critical card per view.">
          <div className="ds-stat-showcase">
            <div className="ds-stat-sample"><small>Default metric</small><strong>28</strong><span>Open actions. Neutral surface.</span></div>
            <div className="ds-stat-sample ds-stat-accent"><small>Action metric</small><strong>74</strong><span>Required reviews. Blue edge.</span></div>
            <div className="ds-stat-sample ds-stat-neon"><small>Focus metric</small><strong>7</strong><span>Pending approvals. Cyan and violet focus.</span></div>
          </div>
          <div className="ds-interaction-note"><strong>Hover:</strong> border brightens and card lifts 2px. <strong>Focus:</strong> accessible ring. <strong>Reduced motion:</strong> no lift or pulse.</div>
        </LabCard>

        <LabCard title="Button matrix" description="Every button exposes action hierarchy and a complete state contract.">
          <div className="ds-button-matrix">
            <div><small>Primary. Default and loading</small><div className="ds-button-row"><DemoButton variant="primary">Save configuration</DemoButton><DemoButton variant="primary" disabled><span className="ds-spinner" /> Saving</DemoButton></div></div>
            <div><small>Secondary. Neutral border</small><div className="ds-button-row"><DemoButton>Save draft</DemoButton><DemoButton className="is-selected">Selected</DemoButton></div></div>
            <div><small>Decision. Confirm and reject</small><div className="ds-button-row"><DemoButton variant="success">Approve</DemoButton><DemoButton variant="danger">Reject</DemoButton></div></div>
            <div><small>Quiet and icon-safe</small><div className="ds-button-row"><DemoButton variant="ghost">More options <MoreHorizontal size={14} /></DemoButton><IconButton label="More options"><MoreHorizontal size={17} /></IconButton></div></div>
          </div>
          <div className="ds-state-strip" aria-label="Button states"><span>Default</span><span className="is-hover">Hover</span><span className="is-focus">Focus-visible</span><span className="is-pressed">Pressed</span><span className="is-disabled">Disabled</span></div>
        </LabCard>
      </div>

      <div className="ds-grid ds-grid-2 ds-lab-section">
        <LabCard title="Sidebar selection and command search" description="Selected navigation gets a smooth gradient fill. Search stays global and keyboard-visible.">
          <div className="ds-demo-sidebar">
            <div className="ds-demo-sidebar-item"><span>◆</span>Executive summary</div>
            <div className="ds-demo-sidebar-item is-selected"><span>✓</span>My teams<i>14</i></div>
            <div className="ds-demo-sidebar-item"><span>◉</span>Insights<i>7</i></div>
            <div className="ds-demo-sidebar-item ds-demo-restricted"><Lock size={13} /><span>Design System</span><b>Admin only</b></div>
          </div>
          <div className="ds-search-demo"><Search size={14} /><span>Search people, teams, and actions...</span><kbd>Ctrl K</kbd></div>
          <div className="ds-interaction-note"><strong>Hover:</strong> surface tint only. <strong>Selected:</strong> gradient fill and action rail. <strong>Keyboard:</strong> visible focus ring and shortcut hint.</div>
        </LabCard>

        <LabCard title="Data states and feedback" description="State is paired with text and an action. Color is never the only signal.">
          <div className="ds-state-cards">
            <div className="ds-state-card ds-loading-state"><div className="ds-loader" role="status" aria-label="Loading"><span className="ds-sr-only">Loading</span></div><small>Dotted dual-ring loader. Reduced-motion safe.</small></div>
            <div className="ds-state-card ds-empty-state"><strong>Empty</strong><span className="ds-state-icon">◯</span><small>Explain what is missing and give one next action.</small></div>
            <div className="ds-state-card ds-error-state"><strong>Error</strong><span className="ds-state-icon">!</span><small>Explain impact, recovery, and support context.</small></div>
          </div>
        </LabCard>
      </div>

      <LabCard title="Motion and interaction contract" description="Motion clarifies state changes. It must never delay work." badge="150-300ms" className="ds-lab-section">
        <div className="ds-motion-grid">
          <div><div className="ds-motion-demo ds-slide-demo">Enter</div><small>Page or drawer enter. 180ms ease-out.</small></div>
          <div><div className="ds-motion-demo ds-hover-demo">Hover</div><small>Color, border, glow. 180ms ease.</small></div>
          <div><div className="ds-motion-demo ds-pulse-demo">Attention</div><small>Focus pulse for urgent review only.</small></div>
          <div><div className="ds-motion-demo ds-shimmer-demo">Loading</div><small>Skeleton shimmer. Reduced-motion safe.</small></div>
        </div>
        <div className="ds-reduced-motion"><strong>Reduced motion:</strong> set durations to 1ms, remove transforms and shimmer, and preserve contrast and focus.</div>
      </LabCard>

      <LabCard title="Page-level handoff checklist" description="Use this before implementing any new frontend page." badge="No outliers" className="ds-lab-section">
        <div className="ds-handoff-grid">
          {[
            ['Purpose', 'Name the user, job to be done, and next action.'],
            ['Grid', 'Declare columns, gutters, gap, max width, and mobile collapse.'],
            ['Hierarchy', 'One primary CTA, one decision focus, supporting actions secondary.'],
            ['States', 'Default, hover, focus, pressed, disabled, loading, empty, error, success.'],
            ['Motion', 'Specify timing, easing, trigger, and reduced-motion fallback.'],
            ['Handoff', 'Name what creates the page, what it produces, and where the user goes next.'],
          ].map(([label, note]) => <div key={label}><span className="ds-check-dot"><Check size={12} /></span><strong>{label}</strong><small>{note}</small></div>)}
        </div>
      </LabCard>

      <div className="ds-grid ds-grid-3 ds-lab-section">
        <LabCard title="Form fields and validation" description="Shared default, focus, error, and disabled contracts.">
          <div className="ds-field-grid">
            <label className="ds-field"><span>Employee email</span><input type="email" value="ahmed@company.com" readOnly /></label>
            <label className="ds-field"><span>Role title</span><input className="is-focus" type="text" value="Team lead" readOnly /></label>
            <label className="ds-field"><span>Target score</span><input className="is-error" type="text" value="120" aria-invalid="true" readOnly /><small className="ds-field-error"><AlertCircle size={14} />Enter a value within the approved band.</small></label>
            <label className="ds-field"><span>Source</span><select disabled defaultValue="locked"><option value="locked">Imported catalog</option></select></label>
          </div>
          <div className="ds-field-grid ds-field-grid-secondary">
            <label className="ds-field"><span>Notes</span><textarea defaultValue="Strong review with clear evidence..." /></label>
            <div className="ds-field"><label htmlFor="ds-stage">Stage</label><select id="ds-stage" defaultValue="Review"><option>Review</option><option>Approved</option></select><label className="ds-checkbox"><input type="checkbox" defaultChecked />Notify team lead</label><button type="button" className={'ds-toggle ' + (autoAdvance ? 'is-on' : '')} role="switch" aria-checked={autoAdvance} onClick={() => setAutoAdvance((value) => !value)}><span /></button><span className="ds-toggle-label">Auto-advance on approval</span></div>
          </div>
        </LabCard>

        <LabCard title="Status and stage pills" description="One vocabulary for scorecards, plans, actions, and approvals.">
          <div className="ds-pill-row"><span className="ds-pill ds-pill-new">New</span><span className="ds-pill ds-pill-review">Review</span><span className="ds-pill ds-pill-focus">Focus</span><span className="ds-pill ds-pill-ready">Ready</span><span className="ds-pill ds-pill-closed">Closed</span><span className="ds-pill ds-pill-danger">Blocked</span></div>
          <div className="ds-priority-row"><span className="ds-priority ds-priority-high">High priority</span><span className="ds-priority ds-priority-medium">Medium</span><span className="ds-priority ds-priority-low">Low</span></div>
          <div className="ds-interaction-note"><strong>Rule:</strong> each color maps to one meaning everywhere. Never use color alone for a decision.</div>
        </LabCard>

        <LabCard title="Avatar, presence and assignee stack" description="Identity sizes scale from dense tables to profile headers.">
          <div className="ds-avatar-row"><Avatar initials="AM" size="small" /><Avatar initials="AM" /><Avatar initials="AM" size="large" /><span className="ds-avatar-presence"><Avatar initials="JS" /><i className="ds-presence-dot ds-online" /></span><span className="ds-avatar-presence"><Avatar initials="RK" /><i className="ds-presence-dot ds-away" /></span></div>
          <div className="ds-avatar-stack"><Avatar initials="AM" /><Avatar initials="JS" /><Avatar initials="RK" /><span className="ds-avatar-more">+4</span></div>
        </LabCard>
      </div>

      <LabCard title="Data table pattern" description="Every list view sorts, selects, and paginates the same way." badge="List and inbox recipe" className="ds-lab-section">
        <div className="ds-table-toolbar"><strong>Open scorecards</strong><span className="ds-interaction-note">{selectedRows.length} selected</span></div>
        <div className="ds-table-wrap">
          <table className="ds-table">
            <thead><tr><th className="ds-selection-col"><span className="ds-sr-only">Select</span><input type="checkbox" aria-label="Select all scorecards" checked={allRowsSelected} onChange={toggleAllRows} /></th><th>Employee</th><th>Score <ArrowDown size={12} aria-hidden="true" /></th><th>Status</th><th>Owner</th><th className="ds-action-col">Actions</th></tr></thead>
            <tbody>
              {tableRows.map((row) => {
                const selected = selectedRows.includes(row.id);
                return <tr key={row.id} className={selected ? 'is-selected' : ''} aria-selected={selected}><td className="ds-selection-col"><input type="checkbox" aria-label={'Select ' + row.name} checked={selected} onChange={() => toggleRow(row.id)} /></td><td><strong>{row.name}</strong><small>{row.team}</small></td><td><strong>{row.score}</strong></td><td><span className={'ds-pill ds-pill-' + (row.status === 'On track' ? 'ready' : row.status === 'Review' ? 'review' : 'danger')}>{row.status}</span></td><td>{row.owner}</td><td className="ds-action-col"><IconButton label={'More actions for ' + row.name}><MoreHorizontal size={17} /></IconButton></td></tr>;
              })}
            </tbody>
          </table>
        </div>
        <nav className="ds-pagination" aria-label="Scorecard pages"><IconButton label="Previous page"><ChevronLeft size={15} /></IconButton><button type="button" className="is-active" aria-current="page">1</button><button type="button">2</button><button type="button">3</button><IconButton label="Next page"><ChevronRight size={15} /></IconButton></nav>
      </LabCard>

      <div className="ds-grid ds-grid-2 ds-lab-section">
        <LabCard title="Tabs and segmented control" description="Tabs switch views. Segmented controls switch one setting.">
          <div className="ds-tabs" role="tablist" aria-label="Scorecard views">
            {['Overview', 'Reviews', 'Evidence', 'Activity'].map((tab) => <button type="button" key={tab} className={selectedTab === tab ? 'is-active' : ''} role="tab" aria-selected={selectedTab === tab} onClick={() => setSelectedTab(tab)}>{tab}{tab === 'Overview' && <span>12</span>}{tab === 'Reviews' && <span>4</span>}</button>)}
          </div>
          <div className="ds-segmented" role="group" aria-label="Scorecard layout">
            {['Board', 'List', 'Calendar'].map((option) => <button type="button" key={option} className={selectedSegment === option ? 'is-active' : ''} aria-pressed={selectedSegment === option} onClick={() => setSelectedSegment(option)}>{option}</button>)}
          </div>
          <p className="ds-demo-caption">Active view: <strong>{selectedTab}</strong>. Layout: <strong>{selectedSegment}</strong>.</p>
        </LabCard>

        <LabCard title="Modal and dialog anatomy" description="Title, scannable body, focus-safe close, and a clear decision pair.">
          {!modalOpen && <DemoButton variant="primary" onClick={() => setModalOpen(true)}>Open example dialog</DemoButton>}
          {modalOpen && <div className="ds-modal-demo" role="dialog" aria-modal="true" aria-labelledby="ds-dialog-title" aria-describedby="ds-dialog-body"><div className="ds-modal-head"><strong id="ds-dialog-title">Archive scorecard?</strong><IconButton label="Close dialog" onClick={() => setModalOpen(false)}><X size={16} /></IconButton></div><p id="ds-dialog-body">This record will leave the active review queue. The audit history remains available.</p><div className="ds-modal-footer"><DemoButton onClick={() => setModalOpen(false)}>Cancel</DemoButton><DemoButton variant="danger" onClick={() => setModalOpen(false)}>Archive</DemoButton></div></div>}
        </LabCard>
      </div>

      <div className="ds-grid ds-grid-2 ds-lab-section">
        <LabCard title="Toast and inline alerts" description="Toasts confirm an action. Banners flag an ongoing condition.">
          <div className="ds-toast-stack">
            <div className="ds-toast ds-toast-success" role="status"><CheckCircle2 size={16} /><div><strong>Scorecard saved</strong><span>Ahmed Mahmoud can see the updated review.</span></div></div>
            <div className="ds-toast ds-toast-danger" role="alert"><AlertCircle size={16} /><div><strong>Approval failed</strong><span>Target threshold needs an owner before submission.</span></div></div>
            <div className="ds-toast ds-toast-info" role="status"><Info size={16} /><div><strong>Workspace refreshed</strong><span>New management data is ready to review.</span></div></div>
            <div className="ds-alert-banner" role="status"><AlertCircle size={16} />3 scorecards are waiting for admin approval.</div>
          </div>
        </LabCard>

        <LabCard title="Tooltip and file upload" description="Tooltips explain icons. Uploads keep progress and recovery visible.">
          <div className="ds-tooltip-demo"><span className="ds-tooltip-trigger"><span className="ds-tooltip-bubble" role="tooltip">Assign an owner</span><IconButton label="Assign an owner"><Info size={16} /></IconButton></span></div>
          <label className="ds-dropzone" htmlFor="ds-file-upload"><FileUp size={22} /><span>Drop CSV files here or <strong>browse files</strong></span><input id="ds-file-upload" className="ds-sr-only" type="file" accept=".csv,.xlsx" aria-label="Upload scorecard files" /><span className="ds-upload-row"><span>june_scorecards.xlsx</span><span className="ds-upload-progress"><span /></span><span>70%</span></span></label>
        </LabCard>
      </div>

      <LabCard title="Filter chips, saved views and pagination" description="List toolbars filter, save, and page the same way everywhere." className="ds-lab-section">
        <div className="ds-filter-toolbar">
          {filters.map((filter) => <span className="ds-filter-chip" key={filter}>{filter}<button type="button" aria-label={'Remove ' + filter + ' filter'} onClick={() => setFilters((current) => current.filter((item) => item !== filter))}><X size={12} /></button></span>)}
          <button type="button" className="ds-filter-add" onClick={() => setFilters((current) => current.includes('Status: Review') ? current : [...current, 'Status: Review'])}>+ Add filter</button>
        </div>
        <div className="ds-saved-views" role="tablist" aria-label="Saved views">
          {['My workspace', 'Needs review', 'All records'].map((view) => <button type="button" key={view} className={activeSavedView === view ? 'is-active' : ''} role="tab" aria-selected={activeSavedView === view} onClick={() => setActiveSavedView(view)}>{view}</button>)}
        </div>
      </LabCard>

      <div className="ds-grid ds-grid-2 ds-lab-section">
        <LabCard title="Activity timeline" description="Actor, action, timestamp, and evidence stay together.">
          <ol className="ds-timeline">
            <li className="is-ready"><span className="ds-timeline-dot" /><strong>Scorecard approved</strong><small>Ahmed Mahmoud. 2h ago</small><p>Approved the June review for Inbound.</p></li>
            <li><span className="ds-timeline-dot" /><strong>Evidence added</strong><small>Lina Samir. Yesterday</small><p>Added a note to the conversion KPI.</p></li>
            <li className="is-danger"><span className="ds-timeline-dot" /><strong>Target missed</strong><small>System. Aug 4</small><p>The action owner was notified for follow-up.</p></li>
          </ol>
        </LabCard>

        <LabCard title="Stepper and wizard progress" description="Every wizard recipe uses this step contract.">
          <ol className="ds-stepper" aria-label="Scorecard workflow progress"><li className="is-done"><span>✓</span><strong>Scope</strong></li><li className="is-done" aria-hidden="true" /><li className="is-done"><span>✓</span><strong>Evidence</strong></li><li className="is-done" aria-hidden="true" /><li className="is-current" aria-current="step"><span>3</span><strong>Review</strong></li><li aria-hidden="true" /><li><span>4</span><strong>Publish</strong></li></ol>
          <div className="ds-stepper-summary"><strong>Step 3 of 4</strong><span>Review</span></div>
          <ol className="ds-mobile-stepper" aria-label="Mobile scorecard workflow progress"><li className="is-done"><span>✓</span><div><strong>Scope</strong><small>Complete</small></div></li><li className="is-done"><span>✓</span><div><strong>Evidence</strong><small>Complete</small></div></li><li className="is-current" aria-current="step"><span>3</span><div><strong>Review</strong><small>Current step. 2 checks remaining.</small></div></li><li><span>4</span><div><strong>Publish</strong><small>Pending</small></div></li></ol>
        </LabCard>
      </div>

      <LabCard title="Critical workspace components" description="These recipes cover the most important PMS workflows without inventing live API behavior." badge="P0 and P1 foundation" className="ds-lab-section ds-critical-card">
        <div className="ds-grid ds-grid-2">
          <LabCard title="Drawer and slide-out panel" description="Preserve list context with a scrollable body and sticky decision footer.">
            <div className="ds-chip-row"><span className="ds-chip is-active">480px. Narrow</span><span className="ds-chip">640px. Standard</span><span className="ds-chip">800px. Evidence</span></div>
            <div className="ds-drawer-demo" role="dialog" aria-labelledby="ds-drawer-title"><div className="ds-drawer-head"><div><strong id="ds-drawer-title">Scorecard decision</strong><small>EMP-28104. Inbound team</small></div><IconButton label="Close scorecard drawer"><X size={16} /></IconButton></div><div className="ds-drawer-body"><div className="ds-drawer-person"><Avatar initials="SM" /><div><strong>Sofia Marin</strong><small>Review complete. Owner Ahmed Mahmoud.</small></div></div><div className="ds-drawer-readiness"><strong>Decision readiness</strong><span><CheckCircle2 size={14} />Evidence complete</span><span><CircleHelp size={14} />Owner confirmation pending</span></div><p className="ds-interaction-note">Body scrolls independently. The footer stays available for the next decision.</p></div><div className="ds-drawer-footer"><DemoButton>Keep open</DemoButton><DemoButton variant="primary">Open profile</DemoButton></div></div>
          </LabCard>

          <LabCard title="Date and time picker" description="Scheduling needs date, range, time slots, timezone, and conflict-aware validation.">
            <div className="ds-picker-fields"><label className="ds-field"><span>Review date</span><input type="date" value="2026-08-12" readOnly /></label><label className="ds-field"><span>Review window</span><input type="text" value="12 Aug - 28 Aug 2026" readOnly /></label></div>
            <div className="ds-calendar-head"><IconButton label="Previous month"><ChevronLeft size={15} /></IconButton><strong>August 2026</strong><IconButton label="Next month"><ChevronRight size={15} /></IconButton></div>
            <div className="ds-mini-calendar" role="grid" aria-label="August 2026 calendar">{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => <span key={day}>{day}</span>)}{['12', '13', '14', '15', '16', '17', '18'].map((date) => <button type="button" key={date} className={date === selectedDate ? 'is-selected' : ''} aria-selected={date === selectedDate} onClick={() => setSelectedDate(date)}>{date}</button>)}</div>
            <div className="ds-time-head"><strong>Available time slots</strong><span>UTC+02:00. Cairo</span></div>
            <div className="ds-time-slots" role="group" aria-label="Available review time slots">{['09:30', '10:00', '11:30', '13:00. Conflict'].map((time) => <button type="button" key={time} className={(time === selectedTime ? 'is-selected ' : '') + (time.includes('Conflict') ? 'is-conflict' : '')} disabled={time.includes('Conflict')} onClick={() => setSelectedTime(time)}>{time}</button>)}</div>
            <div className="ds-field-error"><AlertCircle size={14} />Past dates and conflicts explain the reason before submission.</div>
          </LabCard>

          <LabCard title="Bulk actions toolbar" description="A selection exposes a clear hierarchy and a safe way to dismiss it.">
            <div className="ds-bulk-toolbar"><div><strong>3 employees selected</strong><small>Selection persists while filters remain unchanged.</small></div><div className="ds-button-row"><DemoButton variant="primary" size="small">Move to team</DemoButton><DemoButton size="small">Export</DemoButton><DemoButton variant="danger" size="small">Reject</DemoButton><IconButton label="Clear selected employees"><X size={15} /></IconButton></div></div>
            <div className="ds-bulk-secondary"><DemoButton variant="ghost" size="small">Assign owner</DemoButton><DemoButton variant="ghost" size="small">Add tag</DemoButton><span>Primary action first. Destructive action requires confirmation.</span></div>
          </LabCard>

          <LabCard title="Dropdown menu" description="Overflow actions and sort options use one keyboard-oriented menu contract.">
            <div className="ds-dropdown-demo"><DemoButton variant="primary" onClick={() => setMenuOpen((value) => !value)}>More actions <ChevronDown size={14} /></DemoButton>{menuOpen && <div className="ds-dropdown-menu" role="menu" aria-label="Scorecard actions"><button type="button" role="menuitem">Open scorecard</button><button type="button" role="menuitem">Assign owner</button><div /><button type="button" role="menuitem" disabled>Delete record</button></div>}<small>Arrow keys move between items. Enter selects. Escape closes.</small></div>
          </LabCard>

          <div className="ds-span-2">
            <LabCard title="Team performance board" description="Show stage cards, WIP limits, drop-zone feedback, and one decision-critical focus card.">
              <div className="ds-pipeline-board" role="region" aria-label="Team performance board">
                {pipelineColumns.map((column) => <section className={'ds-pipeline-column ds-pipeline-' + column.tone} key={column.title}><header><div><strong>{column.title}</strong><small>{column.count}. {column.limit}</small></div><IconButton label={column.title + ' column actions'}><MoreHorizontal size={15} /></IconButton></header>{column.cards.map((card) => <article className={'ds-pipeline-card' + (card.statusTone === 'focus' ? ' is-focus' : '')} key={card.name} tabIndex={0} aria-label={card.name + ', ' + column.title}><div className="ds-pipeline-card-top"><Avatar initials={card.initials} size="small" />{card.priority && <span className="ds-priority ds-priority-high">{card.priority}</span>}</div><strong>{card.name}</strong><small>{card.detail}</small><span className={'ds-pill ds-pill-' + card.statusTone}>{card.status}</span></article>)}{column.footer && <div className="ds-pipeline-footer">{column.footer}</div>}</section>)}
              </div>
            </LabCard>
          </div>

          <LabCard title="Interview scorecard" description="Structured feedback keeps decisions evidence-based and validates required categories.">
            <form className="ds-scorecard-demo" onSubmit={(event) => event.preventDefault()}><div className="ds-scorecard-head"><div><strong>Senior team lead. Final review</strong><small>Reviewer: Ahmed Mahmoud. Due today.</small></div><span className="ds-badge ds-badge-orange">2 / 3 complete</span></div><div className="ds-score-category"><button type="button" className="ds-accordion-trigger" aria-expanded="true"><span>Delivery quality</span><span className="ds-badge ds-badge-green">Complete</span></button><div className="ds-score-category-body"><div className="ds-score-row"><span>Systems thinking</span><div className="ds-rating" role="radiogroup" aria-label="Systems thinking rating">{[1, 2, 3, 4, 5].map((value) => <button type="button" key={value} role="radio" aria-checked={score === value} className={score === value ? 'is-selected' : ''} onClick={() => setScore(value)}>{value}</button>)}</div></div><div className="ds-score-row"><span>Evidence quality</span><div className="ds-rating"><button type="button" className="is-selected">3</button><span className="ds-rating-muted">/ 5</span></div></div></div></div><div className="ds-score-category"><button type="button" className="ds-accordion-trigger"><span>Growth and communication</span><span className="ds-badge ds-badge-red">Required</span></button><div className="ds-field-error"><AlertCircle size={14} />Add one evidence-based comment before submitting this category.</div></div><div className="ds-recommendation"><strong>Overall recommendation</strong><div>{['Needs support', 'Strong result', 'Exceeds'].map((option) => <button type="button" key={option} className={recommendation === option ? 'is-selected' : ''} aria-pressed={recommendation === option} onClick={() => setRecommendation(option)}>{option}</button>)}</div></div><DemoButton variant="primary">Save feedback</DemoButton></form>
          </LabCard>

          <LabCard title="Comments and mentions thread" description="Turn the timeline into accountable discussion with replies, mentions, and attachments.">
            <div className="ds-comments-thread"><div className="ds-comment-item"><Avatar initials="AM" size="small" /><div><div className="ds-comment-meta"><strong>Ahmed Mahmoud</strong><span>2h ago. Team lead</span></div><p>Scorecard is strong. <span className="ds-mention">@Lina Samir</span> can you confirm the follow-up?</p><button type="button" className="ds-comment-reply">Reply</button><div className="ds-comment-reply-row"><Avatar initials="LS" size="small" /><div><div className="ds-comment-meta"><strong>Lina Samir</strong><span>1h ago</span></div><p>Follow-up is booked for 15:00.</p></div></div></div></div><div className="ds-comment-composer"><div className="ds-comment-tools"><button type="button" aria-label="Bold">B</button><button type="button" aria-label="Bulleted list">•</button><button type="button" aria-label="Add link">↗</button></div><div className="ds-comment-editor" contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Write a comment">Write a note and mention @someone...</div><div className="ds-comment-footer"><label className="ds-attach-file"><span>Attach file</span><input className="ds-sr-only" type="file" aria-label="Attach a comment file" /></label><DemoButton variant="primary" size="small">Post comment</DemoButton></div></div></div>
          </LabCard>

          <div className="ds-span-2">
            <LabCard title="Interview calendar" description="A weekly operations view for review capacity, timing, and conflict-aware scheduling.">
              <div className="ds-interview-toolbar"><div className="ds-interview-period"><div className="ds-button-row"><IconButton label="Previous week"><ChevronLeft size={15} /></IconButton><IconButton label="Next week"><ChevronRight size={15} /></IconButton><DemoButton size="small">Today</DemoButton></div><div><strong>Aug 10-14, 2026</strong><small>Week 33. UTC+02:00 Cairo.</small></div></div><div className="ds-calendar-switch" role="group" aria-label="Calendar view">{['Week', 'Agenda'].map((view) => <button type="button" key={view} className={calendarView === view ? 'is-selected' : ''} aria-pressed={calendarView === view} onClick={() => setCalendarView(view)}>{view}</button>)}</div></div>
              <div className="ds-interview-scroll"><div className="ds-interview-grid" role="grid" aria-label="Review calendar for August 10 to August 14, 2026"><div className="ds-interview-corner">GMT+2</div>{interviewDays.map((day) => <div key={day.date} className={'ds-interview-day ' + (day.today ? 'is-today' : '')}><strong>{day.day}</strong><b>{day.date}</b><small>{day.count}</small></div>)}{['09:00', '10:00', '11:00', '12:00'].map((time) => <Fragment key={time}><div className="ds-interview-time">{time}</div>{interviewDays.map((day, index) => { const event = interviewEvents[time + '-' + index]; return <div className="ds-interview-slot" key={day.date + '-' + time}>{event ? <button type="button" className={'ds-interview-event ds-event-' + event.tone} aria-label={event.name + ', ' + event.detail + ', ' + time}><small>{time}</small><strong>{event.name}</strong><span>{event.detail}</span></button> : <span className="ds-open-slot">Open</span>}</div>; })}</Fragment>)}</div></div>
              <div className="ds-interview-footer"><span><i className="ds-legend-dot ds-legend-scheduled" />Scheduled <i className="ds-legend-dot ds-legend-open" />Open capacity <i className="ds-legend-dot ds-legend-conflict" />Conflict</span><span>Conflicts require resolution before booking.</span></div>
            </LabCard>
          </div>
        </div>
      </LabCard>

      <footer className="ds-lab-footer"><Sparkles size={15} /> Admin reference surface. Keep tokens, states, permissions, and responsive rules aligned before shipping a new page.</footer>
    </div>
  );
}

export default DesignSystemView;
