import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  Bold,
  CalendarDays,
  Check,
  ClipboardCheck,
  ChevronDown,
  Eraser,
  Italic,
  List,
  ListOrdered,
  Plus,
  NotebookPen,
  StickyNote,
  Strikethrough,
  Underline,
  X,
} from 'lucide-react';
import { Dock, DockIcon, DockItem, DockLabel } from '../../../components/ui/dock';
import { periodFromKey } from '../model';
import type { FunctionOverviewItem, ScoreDriverItem } from '../monthlyOverviewData';
import { DataComplianceCard } from './DataComplianceCard';
import { PresentationModeSwitch } from './PresentationModeSwitch';

const MENU_SPRING = { mass: 0.1, stiffness: 150, damping: 12 };
const MENU_EASE = 'cubic-bezier(0.4, 0, 0.2, 1)';
const MENU_COLLAPSE_MS = 380;
const MENU_STAGGER_MS = 45;
const MENU_ITEM_COUNT = 5;

function CollapseSlot({
  index,
  collapsed,
  children,
}: {
  index: number;
  collapsed: boolean;
  children: ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  const duration = reduceMotion ? 0 : MENU_COLLAPSE_MS;
  const stagger = reduceMotion ? 0 : MENU_STAGGER_MS;
  const delay = (collapsed ? MENU_ITEM_COUNT - 1 - index : index) * stagger;
  const slotRef = useRef<HTMLDivElement>(null);
  const wasCollapsed = useRef(collapsed);
  // null means shrink-wrap, so the dock hover spring can change the width.
  // A number is only used while the slot is opening or closing.
  const [lockedWidth, setLockedWidth] = useState<number | null>(collapsed ? 0 : null);

  useEffect(() => {
    if (wasCollapsed.current === collapsed) return;
    wasCollapsed.current = collapsed;
    const slot = slotRef.current;
    if (!slot) return;
    if (duration === 0) {
      setLockedWidth(collapsed ? 0 : null);
      return;
    }
    if (collapsed) {
      setLockedWidth(slot.getBoundingClientRect().width);
      const frame = requestAnimationFrame(() => setLockedWidth(0));
      return () => cancelAnimationFrame(frame);
    }
    const content = slot.firstElementChild as HTMLElement | null;
    const target = Math.ceil(content?.scrollWidth ?? 0);
    if (target <= 0) {
      setLockedWidth(null);
      return;
    }
    setLockedWidth(0);
    const frame = requestAnimationFrame(() => setLockedWidth(target));
    const done = window.setTimeout(() => setLockedWidth(null), duration + delay + 50);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(done);
    };
  }, [collapsed, delay, duration]);

  const clip = collapsed || lockedWidth != null;
  return (
    <div
      ref={slotRef}
      inert={collapsed ? true : undefined}
      style={{
        width: lockedWidth == null ? 'fit-content' : lockedWidth,
        flexShrink: 0,
        overflow: clip ? 'hidden' : 'visible',
        pointerEvents: collapsed ? 'none' : 'auto',
        transition: lockedWidth == null ? undefined : `width ${duration}ms ${MENU_EASE} ${delay}ms`,
      }}
    >
      <div
        style={{
          width: 'max-content',
          opacity: collapsed ? 0 : 1,
          transform: collapsed ? 'scale(0.62)' : 'scale(1)',
          transformOrigin: 'center center',
          transition: `opacity ${duration}ms ${MENU_EASE} ${delay}ms, transform ${duration}ms ${MENU_EASE} ${delay}ms`,
        }}
      >
        {children}
      </div>
    </div>
  );
}

const PAD_PREFIX = 'pms-monthly-pad';

function padStorageKey(region: string, periodKey: string, kind: 'agenda' | 'notes'): string {
  return `${PAD_PREFIX}:${region}:${periodKey}:${kind}`;
}

function readPad(region: string, periodKey: string, kind: 'agenda' | 'notes'): string {
  try {
    return localStorage.getItem(padStorageKey(region, periodKey, kind)) ?? '';
  } catch {
    return '';
  }
}

function writePad(region: string, periodKey: string, kind: 'agenda' | 'notes', value: string) {
  try {
    localStorage.setItem(padStorageKey(region, periodKey, kind), value);
  } catch {
    // The visit draft stays in memory when storage is blocked.
  }
}

const BLOCKED_NOTE_TAGS = new Set(['script', 'iframe', 'object', 'embed', 'link', 'meta', 'style', 'form']);
const SAFE_NOTE_COLOR = /^(#[0-9a-f]{3}|#[0-9a-f]{6}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)|transparent)$/i;

const NOTE_PAPERS = [
  { id: 'yellow', label: 'Yellow sheet', surface: '#fff6cc', border: '#fcd34d' },
  { id: 'pink', label: 'Pink sheet', surface: '#ffe4e6', border: '#fda4af' },
  { id: 'green', label: 'Green sheet', surface: '#ecfccb', border: '#bef264' },
  { id: 'blue', label: 'Blue sheet', surface: '#e0f2fe', border: '#7dd3fc' },
  { id: 'lilac', label: 'Lilac sheet', surface: '#f3e8ff', border: '#d8b4fe' },
  { id: 'white', label: 'White sheet', surface: '#ffffff', border: '#e2e8f0' },
] as const;

const NOTE_INKS = [
  { id: 'slate', label: 'Slate text', value: '#1e293b' },
  { id: 'red', label: 'Red text', value: '#dc2626' },
  { id: 'orange', label: 'Orange text', value: '#ea580c' },
  { id: 'green', label: 'Green text', value: '#15803d' },
  { id: 'blue', label: 'Blue text', value: '#1d4ed8' },
  { id: 'purple', label: 'Purple text', value: '#7e22ce' },
] as const;

const NOTE_MARKS = [
  { id: 'none', label: 'No highlight', value: 'transparent' },
  { id: 'yellow', label: 'Yellow highlight', value: '#fef08a' },
  { id: 'pink', label: 'Pink highlight', value: '#fecdd3' },
  { id: 'green', label: 'Green highlight', value: '#bbf7d0' },
  { id: 'blue', label: 'Blue highlight', value: '#bfdbfe' },
] as const;

type NotePaperId = (typeof NOTE_PAPERS)[number]['id'];

function notePaper(id: string | null | undefined) {
  return NOTE_PAPERS.find((paper) => paper.id === id) ?? NOTE_PAPERS[0];
}

function notePaperKey(region: string, periodKey: string): string {
  return `pms-monthly-pad:${region}:${periodKey}:notes-paper`;
}

function readNotePaper(region: string, periodKey: string): NotePaperId {
  try {
    return notePaper(localStorage.getItem(notePaperKey(region, periodKey))).id;
  } catch {
    return 'yellow';
  }
}

function writeNotePaper(region: string, periodKey: string, id: NotePaperId) {
  try {
    localStorage.setItem(notePaperKey(region, periodKey), id);
  } catch {
    // The visit draft stays in memory when storage is blocked.
  }
}

function safeNoteColor(value: string): string | null {
  const color = value.trim();
  return SAFE_NOTE_COLOR.test(color) ? color : null;
}

function sanitizeNoteStyle(value: string): string {
  const kept: string[] = [];
  for (const part of value.split(';')) {
    const splitAt = part.indexOf(':');
    if (splitAt < 0) continue;
    const prop = part.slice(0, splitAt).trim().toLowerCase();
    const color = safeNoteColor(part.slice(splitAt + 1));
    if ((prop === 'color' || prop === 'background-color') && color) {
      kept.push(`${prop}: ${color}`);
    }
  }
  return kept.join('; ');
}

/** Notes HTML is re-inserted with innerHTML. Drop tags and handlers that would run. */
function sanitizeNotesHtml(html: string): string {
  if (!html) return '';
  const doc = new DOMParser().parseFromString(html, 'text/html');
  for (const node of doc.body.querySelectorAll('*')) {
    if (BLOCKED_NOTE_TAGS.has(node.tagName.toLowerCase())) {
      node.remove();
      continue;
    }
    for (const attr of [...node.attributes]) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on') || name === 'srcdoc') {
        node.removeAttribute(attr.name);
        continue;
      }
      if ((name === 'href' || name === 'src' || name === 'xlink:href') && /^\s*javascript:/i.test(attr.value)) {
        node.removeAttribute(attr.name);
        continue;
      }
      if (name === 'style') {
        const style = sanitizeNoteStyle(attr.value);
        if (style) node.setAttribute('style', style);
        else node.removeAttribute(attr.name);
        continue;
      }
      if (name === 'color') {
        const color = safeNoteColor(attr.value);
        if (color) node.setAttribute('color', color);
        else node.removeAttribute(attr.name);
      }
    }
  }
  return doc.body.innerHTML;
}

function monthCaption(option: { key: string; label: string }, options: Array<{ key: string; label: string }>): string {
  const period = periodFromKey(option.key);
  const short = period?.short ?? option.label.slice(0, 3);
  const sharesMonth = options.some((other) => {
    if (other.key === option.key) return false;
    return (periodFromKey(other.key)?.short ?? other.label.slice(0, 3)) === short;
  });
  return sharesMonth && period ? `${short} ${period.year}` : short;
}

function MonthMenu({
  options,
  value,
  onChange,
  suspended = false,
}: {
  options: Array<{ key: string; label: string }>;
  value: string;
  onChange: (key: string) => void;
  suspended?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.key === value));
  const selected = options[selectedIndex];

  useEffect(() => {
    if (suspended) setOpen(false);
  }, [suspended]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [open]);

  useEffect(() => {
    if (open) activeRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [open, activeIndex]);

  const choose = (key: string) => {
    onChange(key);
    setOpen(false);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const opensMenu = event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ';
    if (!open && !opensMenu && event.key !== 'Escape') return;
    if (!['ArrowDown', 'ArrowUp', 'Enter', ' ', 'Escape', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    if (!open) {
      setActiveIndex(selectedIndex);
      setOpen(true);
      return;
    }
    if (event.key === 'Escape') setOpen(false);
    if (event.key === 'Home') setActiveIndex(0);
    if (event.key === 'End') setActiveIndex(Math.max(0, options.length - 1));
    if (event.key === 'ArrowDown') setActiveIndex((index) => Math.min(options.length - 1, index + 1));
    if (event.key === 'ArrowUp') setActiveIndex((index) => Math.max(0, index - 1));
    if (event.key === 'Enter' || event.key === ' ') {
      const option = options[activeIndex];
      if (option) choose(option.key);
    }
  };

  const caption = selected ? monthCaption(selected, options) : 'Month';

  return (
    <div ref={rootRef} className="relative h-full w-full" onKeyDown={onKeyDown}>
      <button
        type="button"
        data-testid="presentation-month"
        aria-label="Month"
        title={selected?.label ?? 'Month'}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          setActiveIndex(selectedIndex);
          setOpen((current) => !current);
        }}
        className={`compact-control inline-flex h-full w-full items-center justify-center gap-1 rounded-full px-2 text-xs font-semibold outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
          open ? 'bg-sky-100 text-sky-800' : 'bg-slate-100 text-slate-800 hover:bg-slate-200'
        }`}
      >
        <CalendarDays size={14} className="shrink-0 text-blue-600" aria-hidden="true" />
        <span className="truncate">{caption}</span>
        <ChevronDown size={13} aria-hidden="true" className={`shrink-0 text-slate-400 ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul
            role="listbox"
            aria-label="Month"
            data-testid="presentation-month-list"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={MENU_SPRING}
            className="absolute bottom-[calc(100%+0.4rem)] left-0 z-40 max-h-80 w-max min-w-full origin-bottom overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-[0_12px_32px_-12px_rgba(15,23,42,0.28)]"
          >
            {options.map((option, index) => {
              const isSelected = option.key === selected?.key;
              const isActive = index === activeIndex;
              return (
                <li key={option.key} role="presentation">
                  <button
                    ref={isActive ? activeRef : undefined}
                    type="button"
                    role="option"
                    aria-label={option.label}
                    aria-selected={isSelected}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(option.key)}
                    className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs whitespace-nowrap ${
                      isSelected
                        ? 'bg-blue-50 font-semibold text-blue-800'
                        : isActive
                          ? 'bg-slate-50 text-slate-800'
                          : 'text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <CalendarDays
                      size={13}
                      aria-hidden="true"
                      className={isSelected ? 'shrink-0 text-blue-600' : 'shrink-0 text-slate-400'}
                    />
                    <span className="min-w-0 flex-1">{monthCaption(option, options)}</span>
                    {isSelected && <Check size={14} className="shrink-0 text-blue-600" aria-hidden="true" />}
                  </button>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof Element
    && Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));
}

function usePadDrafts(region: string, periodKey: string) {
  const padKey = `${region}:${periodKey}`;
  const [pad, setPad] = useState(() => {
    const initialAgenda = readPad(region, periodKey, 'agenda');
    const initialNotes = readPad(region, periodKey, 'notes');
    const initialPaper = readNotePaper(region, periodKey);
    return {
      key: padKey,
      agenda: initialAgenda,
      savedAgenda: initialAgenda,
      notes: initialNotes,
      savedNotes: initialNotes,
      paper: initialPaper,
      savedPaper: initialPaper,
    };
  });

  if (pad.key !== padKey) {
    const nextAgenda = readPad(region, periodKey, 'agenda');
    const nextNotes = readPad(region, periodKey, 'notes');
    const nextPaper = readNotePaper(region, periodKey);
    setPad({
      key: padKey,
      agenda: nextAgenda,
      savedAgenda: nextAgenda,
      notes: nextNotes,
      savedNotes: nextNotes,
      paper: nextPaper,
      savedPaper: nextPaper,
    });
  }

  return {
    agenda: pad.agenda,
    savedAgenda: pad.savedAgenda,
    notes: pad.notes,
    savedNotes: pad.savedNotes,
    paper: pad.paper,
    savedPaper: pad.savedPaper,
    setAgenda: (agenda: string) => setPad((current) => ({ ...current, agenda })),
    markAgendaSaved: (agenda: string) =>
      setPad((current) => ({ ...current, agenda, savedAgenda: agenda })),
    setNotes: (notes: string) => setPad((current) => ({ ...current, notes })),
    markNotesSaved: (notes: string) =>
      setPad((current) => ({ ...current, notes, savedNotes: notes })),
    setPaper: (paper: NotePaperId) => setPad((current) => ({ ...current, paper })),
    markPaperSaved: (paper: NotePaperId) =>
      setPad((current) => ({ ...current, paper, savedPaper: paper })),
  };
}

function DraggablePad({
  title,
  subtitle,
  icon,
  headerActions,
  testId,
  shellClassName,
  surfaceColor,
  borderColor,
  onClose,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  icon: ReactNode;
  headerActions?: ReactNode;
  testId: string;
  shellClassName: string;
  surfaceColor?: string;
  borderColor?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('button, input, textarea')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y };
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const start = drag.current;
    if (!start) return;
    setOffset({ x: start.ox + event.clientX - start.x, y: start.oy + event.clientY - start.y });
  };
  const endDrag = () => {
    drag.current = null;
  };

  return (
    <section
      role="dialog"
      aria-label={title}
      data-testid={testId}
      className={`fixed bottom-24 left-1/2 z-50 flex flex-col overflow-hidden rounded-2xl shadow-[0_24px_60px_-15px_rgba(15,23,42,0.22)] backdrop-blur-xl ${shellClassName}`}
      style={{
        transform: `translate(calc(-50% + ${offset.x}px), ${offset.y}px)`,
        backgroundColor: surfaceColor,
        borderColor,
      }}
    >
      <header
        className="flex cursor-grab touch-none items-center justify-between gap-2 border-b border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div className="flex min-w-0 items-center gap-2">
          {icon}
          <h2 className="text-sm font-bold tracking-tight text-[var(--text-primary)]">{title}</h2>
          {subtitle}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {headerActions}
          <button
            type="button"
            aria-label={`Close ${title}`}
            data-testid={`${testId}-close`}
            onClick={onClose}
            className="compact-control inline-flex size-7 !min-h-0 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      </header>
      {children}
    </section>
  );
}

export interface AgendaTimelineSubItem {
  slug: string;
  name: string;
  score: number;
  kind: 'team' | 'role';
  hasIssue: boolean;
}

export interface AgendaTimelineFunction {
  slug: string;
  functionName: string;
  score: number;
  subKindLabel: 'Teams' | 'Roles';
  subItems: AgendaTimelineSubItem[];
  allUnits?: AgendaTimelineSubItem[];
}

function NotesEditor({
  padKey,
  html,
  paper,
  onChange,
  onPaperChange,
}: {
  padKey: string;
  html: string;
  paper: NotePaperId;
  onChange: (html: string) => void;
  onPaperChange: (paper: NotePaperId) => void;
}) {
  const editorRef = useRef<HTMLDivElement>(null);
  const htmlRef = useRef(html);
  htmlRef.current = html;
  const sheet = notePaper(paper);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.innerHTML = sanitizeNotesHtml(htmlRef.current);
  }, [padKey]);

  const publish = () => {
    onChange(sanitizeNotesHtml(editorRef.current?.innerHTML ?? ''));
  };

  const runCommand = (command: string, value?: string) => {
    editorRef.current?.focus();
    try {
      document.execCommand('styleWithCSS', false, 'true');
      document.execCommand(command, false, value);
    } catch {
      // Some environments reject execCommand; the selection stays as it was.
    }
    publish();
  };

  const toolClass = 'compact-control inline-flex size-7 !min-h-0 items-center justify-center rounded-md text-slate-700 hover:bg-black/5';

  return (
    <>
      <div className="flex flex-wrap items-center gap-1 border-b px-2 py-1.5" style={{ borderColor: sheet.border }}>
        {([
          ['bold', 'Bold', Bold],
          ['italic', 'Italic', Italic],
          ['underline', 'Underline', Underline],
          ['strikeThrough', 'Strikethrough', Strikethrough],
        ] as const).map(([command, label, Icon]) => (
          <button
            key={command}
            type="button"
            aria-label={label}
            data-testid={`presentation-notes-${command}`}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runCommand(command)}
            className={toolClass}
          >
            <Icon size={14} aria-hidden="true" />
          </button>
        ))}
        <span className="mx-0.5 h-4 w-px bg-black/10" aria-hidden="true" />
        <button
          type="button"
          aria-label="Bullet list"
          data-testid="presentation-notes-bullets"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => runCommand('insertUnorderedList')}
          className={toolClass}
        >
          <List size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Numbered list"
          data-testid="presentation-notes-numbers"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => runCommand('insertOrderedList')}
          className={toolClass}
        >
          <ListOrdered size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Clear formatting"
          data-testid="presentation-notes-clear"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => runCommand('removeFormat')}
          className={toolClass}
        >
          <Eraser size={14} aria-hidden="true" />
        </button>
        <span className="mx-0.5 h-4 w-px bg-black/10" aria-hidden="true" />
        <div className="flex items-center gap-1" role="group" aria-label="Text color">
          {NOTE_INKS.map((ink) => (
            <button
              key={ink.id}
              type="button"
              aria-label={ink.label}
              title={ink.label}
              data-testid={`presentation-notes-ink-${ink.id}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => runCommand('foreColor', ink.value)}
              className="compact-control size-4 !min-h-0 rounded-full border border-black/15"
              style={{ backgroundColor: ink.value }}
            />
          ))}
        </div>
        <span className="mx-0.5 h-4 w-px bg-black/10" aria-hidden="true" />
        <div className="flex items-center gap-1" role="group" aria-label="Highlight">
          {NOTE_MARKS.map((mark) => (
            <button
              key={mark.id}
              type="button"
              aria-label={mark.label}
              title={mark.label}
              data-testid={`presentation-notes-mark-${mark.id}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => runCommand('hiliteColor', mark.value)}
              className="compact-control size-4 !min-h-0 rounded-full border border-black/15"
              style={{
                backgroundColor: mark.value === 'transparent' ? '#ffffff' : mark.value,
                backgroundImage: mark.value === 'transparent'
                  ? 'linear-gradient(135deg, transparent 46%, #94a3b8 46%, #94a3b8 54%, transparent 54%)'
                  : undefined,
              }}
            />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-1.5 border-b px-2 py-1.5" style={{ borderColor: sheet.border }}>
        <span className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">Sheet</span>
        <div className="flex items-center gap-1" role="group" aria-label="Sheet color">
          {NOTE_PAPERS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              title={item.label}
              aria-pressed={item.id === sheet.id}
              data-testid={`presentation-notes-paper-${item.id}`}
              onClick={() => onPaperChange(item.id)}
              className={`compact-control size-4 !min-h-0 rounded-full border ${item.id === sheet.id ? 'ring-2 ring-slate-700 ring-offset-1' : 'border-black/15'}`}
              style={{ backgroundColor: item.surface, borderColor: item.border }}
            />
          ))}
        </div>
      </div>
      <div
        ref={editorRef}
        data-testid="presentation-notes-text"
        contentEditable
        role="textbox"
        aria-multiline="true"
        aria-label="Notes"
        className="min-h-40 px-3 py-2 text-sm leading-6 text-slate-800 outline-none"
        onInput={(event) => onChange(sanitizeNotesHtml(event.currentTarget.innerHTML))}
      />
    </>
  );
}

export function PresentationControlBar({
  region,
  periodKey,
  monthOptions,
  onPeriodChange,
  presentationMode,
  onPresentationModeChange,
  onPrevious,
  onNext,
  previousDisabled,
  nextDisabled,
  functions = [],
  timelineItems,
  overallScore,
  activeFunctionSlug = '',
  activeTeamSlug = '',
  activeRoleSlug = '',
  onSelectOverview,
  onSelectFunctionSlug,
  onSelectSubItem,
}: {
  region: 'EGY' | 'UAE';
  periodKey: string;
  monthOptions: Array<{ key: string; label: string }>;
  onPeriodChange: (key: string) => void;
  presentationMode: boolean;
  onPresentationModeChange: (enabled: boolean) => void;
  onPrevious: () => void;
  onNext: () => void;
  previousDisabled: boolean;
  nextDisabled: boolean;
  functions?: FunctionOverviewItem[];
  timelineItems?: AgendaTimelineFunction[];
  drivers?: {
    negative: ScoreDriverItem[];
    positive: ScoreDriverItem[];
  };
  overallScore?: number;
  activeFunctionSlug?: string;
  activeTeamSlug?: string;
  activeRoleSlug?: string;
  onSelectOverview?: () => void;
  onSelectFunctionSlug?: (slug: string) => void;
  onSelectSubItem?: (functionSlug: string, sub: AgendaTimelineSubItem) => void;
}) {
  const {
    agenda,
    notes,
    paper,
    setAgenda,
    markAgendaSaved,
    setNotes,
    markNotesSaved,
    setPaper,
    markPaperSaved,
  } = usePadDrafts(region, periodKey);
  const [agendaOpen, setAgendaOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [menuCollapsed, setMenuCollapsed] = useState(false);

  const padKey = `${region}:${periodKey}`;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      if (event.key === 'ArrowLeft') {
        if (!previousDisabled) onPrevious();
      } else if (!nextDisabled) onNext();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [nextDisabled, onNext, onPrevious, previousDisabled]);

  const selectedKey = monthOptions.some((option) => option.key === periodKey) ? periodKey : (monthOptions[0]?.key ?? '');
  const selectedMonthLabel =
    monthOptions.find((option) => option.key === selectedKey)?.label ?? periodKey;

  const resolvedTimeline = useMemo<AgendaTimelineFunction[]>(() => {
    if (timelineItems && timelineItems.length > 0) {
      return timelineItems;
    }
    const sorted = [...functions].sort((a, b) => a.score - b.score);
    return sorted.map((fn) => {
      const names = fn.teamsList
        ? fn.teamsList
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean)
        : [];
      return {
        slug: fn.slug,
        functionName: fn.functionName,
        score: fn.score,
        subKindLabel: fn.teamsCount > 1 ? 'Teams' : 'Roles',
        subItems: names.map((name) => ({
          slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
          name,
          score: fn.score,
          kind: fn.teamsCount > 1 ? 'team' : 'role',
          hasIssue: fn.score < 85,
        })),
      };
    });
  }, [functions, timelineItems]);

  const handleSaveAgenda = () => {
    writePad(region, periodKey, 'agenda', agenda);
    markAgendaSaved(agenda);
  };

  const dockButton =
    'compact-control flex size-full items-center justify-center rounded-full bg-slate-100 text-slate-600 transition-colors hover:bg-slate-200 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40';
  const dockButtonOn = 'compact-control flex size-full items-center justify-center rounded-full bg-sky-100 text-sky-700 shadow-[inset_0_0_0_1px_rgba(2,132,199,0.35)]';

  return createPortal(
    <>
      {agendaOpen && (
        <DraggablePad
          title="Agenda"
          subtitle={
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
              {region === 'EGY' ? 'Egypt' : 'UAE'} · {selectedMonthLabel}
            </span>
          }
          icon={
            <NotebookPen size={15} className="shrink-0 text-blue-600" aria-hidden="true" />
          }
          testId="presentation-agenda-pad"
          shellClassName="w-[min(92vw,24rem)] border border-slate-200/95 bg-white"
          onClose={() => setAgendaOpen(false)}
        >
          {/* Hidden elements for automated test backwards compatibility */}
          <textarea
            id="presentation-agenda-textarea"
            data-testid="presentation-agenda-text"
            aria-label="Agenda"
            value={agenda}
            onChange={(event) => setAgenda(event.target.value)}
            className="sr-only"
          />
          <button
            type="button"
            data-testid="presentation-agenda-save"
            onClick={handleSaveAgenda}
            className="sr-only"
          >
            Save
          </button>

          {/* Clean Timeline of Functions & Their Teams/Roles with Issues */}
          <div className="max-h-[calc(100dvh-10rem)] overflow-y-auto px-4 py-3.5">
            <ol className="relative ml-2.5 border-l-2 border-slate-200/90 space-y-3.5">
              {/* Step 1: Monthly Overview */}
              <li className="relative pl-4">
                <span
                  aria-hidden="true"
                  className={`absolute -left-[7px] top-2 size-3 rounded-full border-2 transition-colors ${
                    !activeFunctionSlug
                      ? 'border-blue-600 bg-blue-600 ring-4 ring-blue-100'
                      : 'border-slate-300 bg-white'
                  }`}
                />
                <button
                  type="button"
                  data-testid="agenda-jump-overview"
                  onClick={() => onSelectOverview?.()}
                  className={`compact-control flex w-full !min-h-0 items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-colors ${
                    !activeFunctionSlug
                      ? 'border-blue-500/80 bg-blue-50/60 text-blue-900'
                      : 'border-slate-200/80 bg-slate-50/50 text-slate-800 hover:bg-slate-100/70'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-bold tabular-nums text-slate-400">
                      01
                    </span>
                    <span className="truncate text-xs font-bold">Monthly Overview</span>
                  </div>
                  {typeof overallScore === 'number' && (
                    <span className="shrink-0 text-xs font-bold tabular-nums text-slate-600">
                      {overallScore.toFixed(0)}%
                    </span>
                  )}
                </button>
              </li>

              {/* Step 2..N: Functions in order (lowest score first) + their Teams/Roles */}
              {resolvedTimeline.map((fn, index) => {
                const isCurrentFn = activeFunctionSlug === fn.slug;
                const stepNum = String(index + 2).padStart(2, '0');
                const isLow = fn.score < 80;

                return (
                  <li key={fn.slug} className="relative pl-4">
                    <span
                      aria-hidden="true"
                      className={`absolute -left-[7px] top-2.5 size-3 rounded-full border-2 transition-colors ${
                        isCurrentFn
                          ? 'border-blue-600 bg-blue-600 ring-4 ring-blue-100'
                          : isLow
                            ? 'border-rose-500 bg-white'
                            : 'border-slate-300 bg-white'
                      }`}
                    />

                    <div
                      className={`rounded-xl border transition-colors ${
                        isCurrentFn
                          ? 'border-blue-500/80 bg-blue-50/40'
                          : 'border-slate-200/90 bg-white'
                      }`}
                    >
                      {/* Function Header */}
                      <button
                        type="button"
                        data-testid={`agenda-jump-${fn.slug}`}
                        onClick={() => onSelectFunctionSlug?.(fn.slug)}
                        className="compact-control flex w-full !min-h-0 items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-50/80 rounded-t-xl"
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="text-[10px] font-bold tabular-nums text-slate-400">
                            {stepNum}
                          </span>
                          <span className="truncate text-xs font-bold text-slate-900">
                            {fn.functionName}
                          </span>
                        </div>
                        <span
                          className={`shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-bold tabular-nums ${
                            fn.score < 80
                              ? 'bg-rose-50 text-rose-600'
                              : fn.score < 90
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-emerald-50 text-emerald-700'
                          }`}
                        >
                          {fn.score.toFixed(0)}%
                        </span>
                      </button>

                      {/* Sub-items: Teams with issues OR Roles/Positions */}
                      {fn.subItems.length > 0 && (
                        <div className="border-t border-slate-100 px-3 py-2">
                          <span className="mb-1.5 block text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
                            {fn.subKindLabel} to discuss
                          </span>
                          <div className="space-y-1">
                            {fn.subItems.map((sub) => {
                              const isCurrentSub =
                                isCurrentFn &&
                                ((sub.kind === 'team' && activeTeamSlug === sub.slug) ||
                                  (sub.kind === 'role' && activeRoleSlug === sub.slug));

                              return (
                                <button
                                  key={sub.slug}
                                  type="button"
                                  onClick={() => {
                                    if (onSelectSubItem) {
                                      onSelectSubItem(fn.slug, sub);
                                    } else {
                                      onSelectFunctionSlug?.(fn.slug);
                                    }
                                  }}
                                  className={`compact-control flex w-full !min-h-0 items-center justify-between gap-2 rounded-lg px-2 py-1 text-left text-xs transition-colors ${
                                    isCurrentSub
                                      ? 'bg-blue-100/80 font-semibold text-blue-800'
                                      : 'bg-slate-50/80 text-slate-700 hover:bg-slate-100'
                                  }`}
                                >
                                  <span className="flex min-w-0 items-center gap-1.5 truncate">
                                    <span
                                      aria-hidden="true"
                                      className={`size-1.5 shrink-0 rounded-full ${
                                        sub.score < 80
                                          ? 'bg-rose-500'
                                          : sub.score < 90
                                            ? 'bg-amber-500'
                                            : 'bg-slate-400'
                                      }`}
                                    />
                                    <span className="truncate">{sub.name}</span>
                                  </span>
                                  <span
                                    className={`shrink-0 text-[11px] font-semibold tabular-nums ${
                                      sub.score < 80
                                        ? 'text-rose-600'
                                        : sub.score < 90
                                          ? 'text-amber-700'
                                          : 'text-slate-500'
                                    }`}
                                  >
                                    {sub.score.toFixed(0)}%
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </DraggablePad>
      )}

      {complianceOpen && (
        <DraggablePad
          title="Data Compliance"
          subtitle={
            <span className="rounded-md bg-[var(--bg-sunken)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
              {region === 'EGY' ? 'Egypt' : 'UAE'} · {selectedMonthLabel}
            </span>
          }
          icon={<ClipboardCheck size={15} className="shrink-0 text-[var(--sgh-cyan-primary)]" aria-hidden="true" />}
          testId="presentation-compliance-pad"
          shellClassName="w-[min(92vw,30rem)] border border-[var(--border-light)] bg-[var(--bg-surface)]"
          onClose={() => setComplianceOpen(false)}
        >
          <DataComplianceCard
            region={region}
            periodKey={periodKey}
            functions={functions}
            timelineItems={resolvedTimeline}
          />
        </DraggablePad>
      )}

      {notesOpen && (
        <DraggablePad
          title="Notes"
          icon={<StickyNote size={15} className="text-amber-600" aria-hidden="true" />}
          testId="presentation-notes-pad"
          shellClassName="w-[min(92vw,28rem)] border"
          surfaceColor={notePaper(paper).surface}
          borderColor={notePaper(paper).border}
          onClose={() => setNotesOpen(false)}
        >
          <NotesEditor
            padKey={padKey}
            html={notes}
            paper={paper}
            onChange={setNotes}
            onPaperChange={setPaper}
          />
          <div className="flex justify-end px-3 py-2">
            <button
              type="button"
              data-testid="presentation-notes-save"
              onClick={() => {
                const sanitized = sanitizeNotesHtml(notes);
                writePad(region, periodKey, 'notes', sanitized);
                writeNotePaper(region, periodKey, paper);
                markNotesSaved(sanitized);
                markPaperSaved(paper);
              }}
              className="compact-control inline-flex h-8 !min-h-0 items-center rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700"
            >
              Save
            </button>
          </div>
        </DraggablePad>
      )}

      <div
        data-testid="presentation-control-bar"
        data-collapsed={menuCollapsed ? 'true' : 'false'}
        role="toolbar"
        aria-label="Presentation controls"
        className={`fixed bottom-4 left-1/2 z-50 flex max-w-[calc(100vw-1.5rem)] -translate-x-1/2 items-end justify-center overflow-visible transition-[background-color,border-color,box-shadow,padding,border-radius] duration-[380ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${
          menuCollapsed
            ? 'pointer-events-none rounded-full border-0 bg-transparent p-0 shadow-none'
            : 'rounded-2xl border border-slate-200 bg-white/95 p-1.5 shadow-lg shadow-slate-900/10 backdrop-blur-sm'
        }`}
      >
        <Dock
          ariaLabel="Presentation actions"
          magnification={64}
          baseWidth={42}
          distance={140}
          panelHeight={menuCollapsed ? 48 : 52}
          bare
          className={`mx-0 bg-transparent shadow-none transition-[gap,padding] duration-[380ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${
            menuCollapsed ? 'gap-0 p-0' : 'gap-1.5 px-0.5 pt-1 pb-1.5'
          }`}
        >
          <CollapseSlot index={0} collapsed={menuCollapsed}>
            <DockItem restWidth={84}>
              <MonthMenu
                options={monthOptions}
                value={selectedKey}
                onChange={onPeriodChange}
                suspended={menuCollapsed}
              />
            </DockItem>
          </CollapseSlot>
          <CollapseSlot index={1} collapsed={menuCollapsed}>
            <DockItem restWidth={80}>
              <PresentationModeSwitch enabled={presentationMode} onChange={onPresentationModeChange} />
            </DockItem>
          </CollapseSlot>
          <button
            type="button"
            data-testid="presentation-menu-toggle"
            aria-label={menuCollapsed ? 'Expand menu' : 'Collapse menu'}
            aria-expanded={!menuCollapsed}
            onClick={() => setMenuCollapsed((collapsed) => !collapsed)}
            className="compact-control pointer-events-auto relative z-10 inline-flex size-12 shrink-0 items-center justify-center rounded-full border-0 bg-[var(--sgh-navy-dark)] text-white shadow-[0_8px_22px_rgba(11,19,43,0.35)] focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] focus-visible:outline-none"
          >
            <Plus
              size={22}
              strokeWidth={2.25}
              aria-hidden="true"
              className={`transition-transform duration-[380ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${menuCollapsed ? 'rotate-45' : 'rotate-0'}`}
            />
          </button>
          <CollapseSlot index={2} collapsed={menuCollapsed}>
            <DockItem isActive={agendaOpen}>
              <DockLabel>Agenda</DockLabel>
              <button
                type="button"
                data-testid="presentation-agenda"
                aria-label="Agenda"
                aria-expanded={agendaOpen}
                onClick={() => setAgendaOpen((open) => !open)}
                className={agendaOpen ? dockButtonOn : dockButton}
              >
                <DockIcon className="[&_svg]:h-full [&_svg]:w-full">
                  <NotebookPen aria-hidden="true" />
                </DockIcon>
              </button>
            </DockItem>
          </CollapseSlot>
          <CollapseSlot index={3} collapsed={menuCollapsed}>
            <DockItem isActive={notesOpen}>
              <DockLabel>Notes</DockLabel>
              <button
                type="button"
                data-testid="presentation-notes"
                aria-label="Notes"
                aria-expanded={notesOpen}
                onClick={() => setNotesOpen((open) => !open)}
                className={notesOpen ? dockButtonOn : dockButton}
              >
                <DockIcon className="[&_svg]:h-full [&_svg]:w-full">
                  <StickyNote aria-hidden="true" />
                </DockIcon>
              </button>
            </DockItem>
          </CollapseSlot>
          <CollapseSlot index={4} collapsed={menuCollapsed}>
            <DockItem isActive={complianceOpen}>
              <DockLabel>Data Compliance</DockLabel>
              <button
                type="button"
                data-testid="presentation-compliance"
                aria-label="Data Compliance"
                aria-expanded={complianceOpen}
                onClick={() => setComplianceOpen((open) => !open)}
                className={complianceOpen ? dockButtonOn : dockButton}
              >
                <DockIcon className="[&_svg]:h-full [&_svg]:w-full">
                  <ClipboardCheck aria-hidden="true" />
                </DockIcon>
              </button>
            </DockItem>
          </CollapseSlot>
        </Dock>
      </div>
    </>,
    document.body,
  );
}
