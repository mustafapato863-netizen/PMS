import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Bold, CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, Italic, NotebookPen, StickyNote, Underline, X } from 'lucide-react';
import { Dock, DockIcon, DockItem, DockLabel } from '../../../components/ui/dock';
import { periodFromKey } from '../model';
import { PresentationModeSwitch } from './PresentationModeSwitch';

const MENU_SPRING = { mass: 0.1, stiffness: 150, damping: 12 };

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
}: {
  options: Array<{ key: string; label: string }>;
  value: string;
  onChange: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.key === value));
  const selected = options[selectedIndex];

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
  const [pad, setPad] = useState(() => ({
    key: padKey,
    agenda: readPad(region, periodKey, 'agenda'),
    notes: readPad(region, periodKey, 'notes'),
  }));

  if (pad.key !== padKey) {
    setPad({
      key: padKey,
      agenda: readPad(region, periodKey, 'agenda'),
      notes: readPad(region, periodKey, 'notes'),
    });
  }

  return {
    agenda: pad.agenda,
    notes: pad.notes,
    setAgenda: (agenda: string) => setPad((current) => ({ ...current, agenda })),
    setNotes: (notes: string) => setPad((current) => ({ ...current, notes })),
  };
}

function DraggablePad({
  title,
  icon,
  testId,
  shellClassName,
  onClose,
  children,
}: {
  title: string;
  icon: ReactNode;
  testId: string;
  shellClassName: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('button')) return;
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
      className={`fixed bottom-24 left-1/2 z-50 flex w-[min(92vw,26rem)] flex-col overflow-hidden rounded-2xl shadow-xl shadow-slate-900/15 ${shellClassName}`}
      style={{ transform: `translate(calc(-50% + ${offset.x}px), ${offset.y}px)` }}
    >
      <header
        className="flex cursor-grab touch-none items-center justify-between gap-2 px-3 py-2 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <h2 className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800">
          {icon}
          {title}
        </h2>
        <button
          type="button"
          aria-label={`Close ${title}`}
          data-testid={`${testId}-close`}
          onClick={onClose}
          className="compact-control inline-flex size-7 items-center justify-center rounded-lg text-slate-500 hover:bg-black/5 hover:text-slate-800"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </header>
      {children}
    </section>
  );
}

function NotesEditor({
  padKey,
  html,
  onChange,
}: {
  padKey: string;
  html: string;
  onChange: (html: string) => void;
}) {
  const editorRef = useRef<HTMLDivElement>(null);
  const htmlRef = useRef(html);
  htmlRef.current = html;

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.innerHTML = sanitizeNotesHtml(htmlRef.current);
  }, [padKey]);

  const apply = (command: 'bold' | 'italic' | 'underline') => {
    try {
      document.execCommand(command);
    } catch {
      // Some environments reject execCommand; the selection stays as it was.
    }
    onChange(sanitizeNotesHtml(editorRef.current?.innerHTML ?? ''));
  };

  return (
    <>
      <div className="flex items-center gap-1 border-b border-amber-200/80 px-2 py-1.5">
        {([
          ['bold', 'Bold', Bold],
          ['italic', 'Italic', Italic],
          ['underline', 'Underline', Underline],
        ] as const).map(([command, label, Icon]) => (
          <button
            key={command}
            type="button"
            aria-label={label}
            data-testid={`presentation-notes-${command}`}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => apply(command)}
            className="compact-control inline-flex size-7 items-center justify-center rounded-md text-slate-700 hover:bg-amber-100"
          >
            <Icon size={14} aria-hidden="true" />
          </button>
        ))}
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
}) {
  const { agenda, notes, setAgenda, setNotes } = usePadDrafts(region, periodKey);
  const [agendaOpen, setAgendaOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const padKey = `${region}:${periodKey}`;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      if (event.key === 'ArrowLeft') onPrevious();
      else onNext();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onNext, onPrevious]);

  const selectedKey = monthOptions.some((option) => option.key === periodKey) ? periodKey : (monthOptions[0]?.key ?? '');
  const dockButton =
    'compact-control flex size-full items-center justify-center rounded-full bg-slate-100 text-slate-600 transition-colors hover:bg-slate-200 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40';
  const dockButtonOn = 'compact-control flex size-full items-center justify-center rounded-full bg-sky-100 text-sky-700 shadow-[inset_0_0_0_1px_rgba(2,132,199,0.35)]';

  return createPortal(
    <>
      {agendaOpen && (
        <DraggablePad
          title="Agenda"
          icon={<NotebookPen size={15} className="text-slate-500" aria-hidden="true" />}
          testId="presentation-agenda-pad"
          shellClassName="border border-slate-200 bg-[#fbfaf6]"
          onClose={() => setAgendaOpen(false)}
        >
          <div className="px-3 pb-3">
            <textarea
              data-testid="presentation-agenda-text"
              aria-label="Agenda"
              value={agenda}
              onChange={(event) => setAgenda(event.target.value)}
              className="min-h-48 w-full resize-y rounded-lg border border-slate-200 bg-white/70 px-3 py-2 text-sm text-slate-800 outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              style={{
                lineHeight: '28px',
                backgroundImage: 'repeating-linear-gradient(to bottom, transparent 0 27px, #e2e8f0 27px 28px)',
                backgroundAttachment: 'local',
              }}
            />
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                data-testid="presentation-agenda-save"
                onClick={() => writePad(region, periodKey, 'agenda', agenda)}
                className="compact-control inline-flex h-8 items-center rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700"
              >
                Save
              </button>
            </div>
          </div>
        </DraggablePad>
      )}

      {notesOpen && (
        <DraggablePad
          title="Notes"
          icon={<StickyNote size={15} className="text-amber-600" aria-hidden="true" />}
          testId="presentation-notes-pad"
          shellClassName="border border-amber-200 bg-[#fff6cc]"
          onClose={() => setNotesOpen(false)}
        >
          <NotesEditor padKey={padKey} html={notes} onChange={setNotes} />
          <div className="flex justify-end px-3 py-2">
            <button
              type="button"
              data-testid="presentation-notes-save"
              onClick={() => writePad(region, periodKey, 'notes', sanitizeNotesHtml(notes))}
              className="compact-control inline-flex h-8 items-center rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700"
            >
              Save
            </button>
          </div>
        </DraggablePad>
      )}

      <div
        data-testid="presentation-control-bar"
        role="toolbar"
        aria-label="Presentation controls"
        className="fixed bottom-4 left-1/2 z-50 flex max-w-[calc(100vw-1.5rem)] -translate-x-1/2 items-end justify-center overflow-visible rounded-2xl border border-slate-200 bg-white/95 p-1.5 shadow-lg shadow-slate-900/10 backdrop-blur-sm"
      >
        <Dock
          ariaLabel="Presentation actions"
          magnification={64}
          baseWidth={42}
          distance={140}
          panelHeight={52}
          bare
          className="mx-0 gap-1.5 px-0.5 pt-1 pb-1.5"
        >
          <DockItem restWidth={84}>
            <MonthMenu options={monthOptions} value={selectedKey} onChange={onPeriodChange} />
          </DockItem>
          <DockItem restWidth={80}>
            <PresentationModeSwitch enabled={presentationMode} onChange={onPresentationModeChange} />
          </DockItem>
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
          <DockItem>
            <DockLabel>Previous</DockLabel>
            <button
              type="button"
              data-testid="presentation-prev"
              aria-label="Previous"
              disabled={previousDisabled}
              onClick={onPrevious}
              className={dockButton}
            >
              <DockIcon className="[&_svg]:h-full [&_svg]:w-full">
                <ChevronLeft aria-hidden="true" />
              </DockIcon>
            </button>
          </DockItem>
          <DockItem>
            <DockLabel>Next</DockLabel>
            <button
              type="button"
              data-testid="presentation-next"
              aria-label="Next"
              disabled={nextDisabled}
              onClick={onNext}
              className={dockButton}
            >
              <DockIcon className="[&_svg]:h-full [&_svg]:w-full">
                <ChevronRight aria-hidden="true" />
              </DockIcon>
            </button>
          </DockItem>
        </Dock>
      </div>
    </>,
    document.body,
  );
}
