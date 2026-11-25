import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Eraser, Filter, X } from 'lucide-react';
import './ResponsiveFilters.css';

export type ResponsiveFiltersVariant = 'floating' | 'docked';
export type ResponsiveFiltersDockPlacement = 'auto' | 'above' | 'below';

interface ResponsiveFiltersProps {
  children: ReactNode;
  activeCount?: number;
  clearableCount?: number;
  onClear?: () => void;
  label?: string;
  className?: string;
  /**
   * 'floating' (default) is the draggable portal launcher used by every page.
   * 'docked' renders the trigger in-flow (e.g. inside a toolbar) with no drag,
   * no stored position and no safe-area clamping; only the panel stays portaled.
   */
  variant?: ResponsiveFiltersVariant;
  /** Preferred panel anchor direction when variant="docked". Defaults to 'auto'. */
  dockPlacement?: ResponsiveFiltersDockPlacement;
  /** Disables opening the filter panel (e.g., when docked inside a collapsed bar). */
  disabled?: boolean;
}

interface FloatingPosition {
  x: number;
  y: number;
}

type DockedAnchor =
  | { placement: 'below'; top: number; right: number; maxHeight: number }
  | { placement: 'above'; bottom: number; left: number; maxHeight: number };

interface SafeArea {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

const FILTER_POSITION_KEY = 'pms:responsive-filter-position:v1';

function filterButtonSize() {
  return window.innerWidth <= 639 ? 44 : 54;
}

function edgeMargin() {
  return window.innerWidth <= 639 ? 12 : 14;
}

/**
 * Where the launcher may sit: below the app header, above the bottom dock when the dock is shown, and inset by the
 * edge margin on every side. Measured from the DOM, so the compact scale is respected. Where the header or dock is
 * not mounted (login, tests), that side has nothing to clear and only the window edge limits the launcher.
 */
function safeArea(): SafeArea {
  const edge = edgeMargin();
  const size = filterButtonSize();
  const header = document.querySelector<HTMLElement>('header.app-header');
  const headerBottom = header ? header.offsetHeight : 0;
  const dock = document.querySelector<HTMLElement>('nav.navigation-dock');
  const dockShown = dock !== null && !dock.hidden && window.getComputedStyle(dock).display !== 'none';
  const dockTop = dockShown ? dock.getBoundingClientRect().top : window.innerHeight;
  const minX = edge;
  const maxX = Math.max(minX, window.innerWidth - size - edge);
  const minY = headerBottom + edge;
  const maxY = Math.max(minY, dockTop - size - edge);
  return { minX, maxX, minY, maxY };
}

function clampPosition(position: FloatingPosition): FloatingPosition {
  if (typeof window === 'undefined') return position;
  const area = safeArea();
  return {
    x: Math.round(Math.min(Math.max(position.x, area.minX), area.maxX)),
    y: Math.round(Math.min(Math.max(position.y, area.minY), area.maxY)),
  };
}

/** The top-right corner of the safe area. */
function defaultFilterPosition(): FloatingPosition {
  if (typeof window === 'undefined') return { x: 0, y: 0 };
  const area = safeArea();
  return { x: area.maxX, y: area.minY };
}

function readStoredPosition(): FloatingPosition | null {
  try {
    const stored = window.localStorage.getItem(FILTER_POSITION_KEY);
    if (!stored) return null;
    const parsed = JSON.parse(stored) as Partial<FloatingPosition>;
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') return null;
    return { x: parsed.x, y: parsed.y };
  } catch {
    return null;
  }
}

/** A persistent floating launcher for the current page's filter controls. */
const ResponsiveFilters = ({
  children,
  activeCount = 0,
  clearableCount,
  onClear,
  label = 'Filters',
  className = '',
  variant = 'floating',
  dockPlacement = 'auto',
  disabled = false,
}: ResponsiveFiltersProps) => {
  const isDocked = variant === 'docked';
  const [isOpen, setIsOpen] = useState(false);
  const panelOpen = isOpen && !disabled;
  const [initial] = useState(() => {
    // A docked trigger never moves, so it has no stored position to read.
    if (variant === 'docked') return { stored: null, position: { x: 0, y: 0 } };
    const stored = readStoredPosition();
    return { stored, position: stored ? clampPosition(stored) : defaultFilterPosition() };
  });
  const [position, setPosition] = useState<FloatingPosition>(initial.position);
  // Until the user moves the launcher it stays at the top-right of the safe area and follows the window.
  const followDefault = useRef(initial.stored === null);
  const [isDragging, setIsDragging] = useState(false);
  const titleId = useId();
  const panelId = `${titleId}-panel`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origin: FloatingPosition; moved: boolean } | null>(null);
  const suppressClickRef = useRef(false);
  // Docked panel anchor: above or below its trigger depending on available viewport space.
  const [dockedAnchor, setDockedAnchor] = useState<DockedAnchor | null>(null);
  const reduceMotion = useReducedMotion();
  const safeActiveCount = Math.max(0, activeCount);
  const safeClearableCount = Math.max(0, clearableCount ?? safeActiveCount);
  const isCompact = typeof window !== 'undefined' && window.innerWidth <= 639;
  const buttonSize = isCompact ? 50 : 54;
  const accessibleLabel = safeActiveCount > 0
    ? `${label}, ${safeActiveCount} active filters`
    : label;
  const leftSpace = position.x - 12;
  const rightSpace = (typeof window === 'undefined' ? 0 : window.innerWidth) - position.x - buttonSize - 12;
  const panelOpensRight = rightSpace >= leftSpace;
  const panelWidth = typeof window === 'undefined'
    ? 470
    : Math.max(220, Math.min(470, window.innerWidth - 24, panelOpensRight ? rightSpace : leftSpace));

  useEffect(() => {
    if (isDocked) return undefined;
    const handleResize = () => setPosition((current) => (followDefault.current ? defaultFilterPosition() : clampPosition(current)));
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isDocked]);

  // The header and dock can mount in the same commit as the launcher, so measure again once they are in the DOM.
  useLayoutEffect(() => {
    if (isDocked) return undefined;
    setPosition((current) => (followDefault.current ? defaultFilterPosition() : clampPosition(current)));
  }, [isDocked]);

  // Keep the docked panel anchored relative to its trigger while open.
  useLayoutEffect(() => {
    if (!isDocked || !panelOpen) return undefined;
    const updateAnchor = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const panelW = Math.max(220, Math.min(470, vw - 24));
      const spaceBelow = vh - rect.bottom;
      const opensAbove = dockPlacement === 'above'
        ? true
        : dockPlacement === 'below'
          ? false
          : rect.height > 0 && spaceBelow < 320 && rect.top > spaceBelow;

      if (opensAbove) {
        const noLayoutRect = rect.height === 0 && rect.top === 0;
        const left = noLayoutRect
          ? Math.max(12, Math.round((vw - panelW) / 2))
          : Math.round(Math.min(Math.max(12, rect.left + rect.width / 2 - panelW / 2), Math.max(12, vw - panelW - 12)));
        const bottom = noLayoutRect ? 84 : Math.max(12, Math.round(vh - rect.top + 12));
        const availableH = noLayoutRect ? vh - 108 : rect.top - 24;
        setDockedAnchor({
          placement: 'above',
          bottom,
          left,
          maxHeight: Math.max(220, Math.min(availableH, 760)),
        });
        return;
      }

      setDockedAnchor({
        placement: 'below',
        top: rect.bottom + 8,
        right: Math.max(12, vw - rect.right),
        maxHeight: Math.max(220, Math.min(spaceBelow - 20, 760)),
      });
    };
    updateAnchor();
    window.addEventListener('resize', updateAnchor);
    window.addEventListener('scroll', updateAnchor, true);
    return () => {
      window.removeEventListener('resize', updateAnchor);
      window.removeEventListener('scroll', updateAnchor, true);
    };
  }, [dockPlacement, isDocked, panelOpen]);

  useEffect(() => {
    if (isDocked) return undefined;
    const timer = window.setTimeout(() => {
      try {
        if (followDefault.current) {
          window.localStorage.removeItem(FILTER_POSITION_KEY);
          return;
        }
        window.localStorage.setItem(FILTER_POSITION_KEY, JSON.stringify(position));
      } catch {
        // The floating button remains usable when browser storage is unavailable.
      }
    }, 100);
    return () => window.clearTimeout(timer);
  }, [isDocked, position]);

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    suppressClickRef.current = false;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origin: position,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(deltaX, deltaY) < 5) return;
    drag.moved = true;
    followDefault.current = false;
    suppressClickRef.current = true;
    setIsDragging(true);
    event.preventDefault();
    setPosition(clampPosition({ x: drag.origin.x + deltaX, y: drag.origin.y + deltaY }));
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    if (dragRef.current.moved) suppressClickRef.current = true;
    dragRef.current = null;
    setIsDragging(false);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
  };

  const handleLauncherKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!event.altKey) return;
    const step = event.shiftKey ? 48 : 24;
    const moves: Record<string, FloatingPosition> = {
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
    };
    if (event.key === 'Home') {
      event.preventDefault();
      followDefault.current = true;
      setPosition(defaultFilterPosition());
      return;
    }
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    followDefault.current = false;
    setPosition((current) => clampPosition({ x: current.x + move.x, y: current.y + move.y }));
  };

  const close = useCallback(() => {
    setIsOpen(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!panelOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;

      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), select:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      ));
      if (!focusable.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);
    window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [close, panelOpen]);

  if (typeof document === 'undefined') return null;

  const transition = reduceMotion
    ? { duration: 0.01 }
    : { duration: 0.24, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] };
  const panelHalfHeight = typeof window === 'undefined' ? 0 : window.innerHeight * 0.42;
  const panelTop = typeof window === 'undefined'
    ? 0
    : Math.max(panelHalfHeight + 12, Math.min(position.y + buttonSize / 2, window.innerHeight - panelHalfHeight - 12));
  // Docked: above or below its trigger depending on viewport space. Compact
  // screens keep the existing full-width bottom-sheet CSS (panelStyle stays undefined there).
  const dockedPanelWidth = typeof window === 'undefined'
    ? 470
    : Math.max(220, Math.min(470, window.innerWidth - 24));
  const dockedOpensAbove = isDocked && dockedAnchor?.placement === 'above';
  const panelStyle = isCompact
    ? undefined
    : isDocked
      ? dockedAnchor
        ? dockedAnchor.placement === 'above'
          ? {
              top: 'auto',
              bottom: `${dockedAnchor.bottom}px`,
              left: `${dockedAnchor.left}px`,
              right: 'auto',
              width: `${dockedPanelWidth}px`,
              maxHeight: `${dockedAnchor.maxHeight}px`,
              transformOrigin: 'center bottom',
            }
          : {
              top: `${dockedAnchor.top}px`,
              left: 'auto',
              right: `${dockedAnchor.right}px`,
              width: `${dockedPanelWidth}px`,
              maxHeight: `${dockedAnchor.maxHeight}px`,
              transformOrigin: 'right top',
            }
        : undefined
      : {
          top: `${panelTop}px`,
          left: panelOpensRight ? `${position.x + buttonSize + 12}px` : 'auto',
          right: panelOpensRight ? 'auto' : `${window.innerWidth - position.x + 12}px`,
          width: `${panelWidth}px`,
          transformOrigin: panelOpensRight ? 'left center' : 'right center',
        };
  // A below-docked panel enters from the right; an above-docked panel rises from the bar.
  const panelEnterX = isDocked ? (dockedOpensAbove ? 0 : 24) : panelOpensRight ? -24 : 24;
  const panelEnterY = dockedOpensAbove ? 12 : 0;

  const trigger = (
    <div
      className={isDocked
        ? `responsive-filter-docked ${className}`.trim()
        : `responsive-filter-launcher ${className}`.trim()}
      style={isDocked ? undefined : { left: position.x, top: position.y }}
    >
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        className={isDocked
          ? `responsive-filter-trigger responsive-filter-trigger--docked${safeActiveCount > 0 ? ' has-active-filters' : ''}`
          : `responsive-filter-trigger${isDragging ? ' is-dragging' : ''}`}
        aria-label={isDocked
          ? accessibleLabel
          : `${accessibleLabel}. Drag to move; use Alt plus arrow keys, or Alt plus Home to reset`}
        aria-expanded={panelOpen}
        aria-controls={panelId}
        aria-haspopup="dialog"
        {...(isDocked
          ? {}
          : {
              'aria-keyshortcuts': 'Alt+ArrowUp Alt+ArrowDown Alt+ArrowLeft Alt+ArrowRight Alt+Home',
              title: `${label} · drag to move · Alt+arrow keys to reposition`,
              onPointerDown: handlePointerDown,
              onPointerMove: handlePointerMove,
              onPointerUp: handlePointerUp,
              onPointerCancel: handlePointerUp,
              onKeyDown: handleLauncherKeyDown,
            })}
        onClick={(event) => {
          if (disabled) return;
          if (!isDocked && suppressClickRef.current) {
            suppressClickRef.current = false;
            event.preventDefault();
            return;
          }
          setIsOpen((open) => !open);
        }}
      >
        <Filter size={20} aria-hidden="true" />
        {safeActiveCount > 0 && (
          <span className="responsive-filter-count" aria-hidden="true">{safeActiveCount}</span>
        )}
        <span className="responsive-filter-tooltip" aria-hidden="true">{label}</span>
      </button>
    </div>
  );

  const overlay = (
    <AnimatePresence initial={false}>
      {panelOpen && (
        <>
          <motion.button
            key="filter-scrim"
            type="button"
            className="responsive-filter-scrim"
            aria-label={`Close ${label.toLowerCase()}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={transition}
            onClick={close}
          />
          <motion.aside
            key="filter-panel"
            id={panelId}
            ref={panelRef}
            className={`responsive-filter-panel${isDocked ? ' responsive-filter-panel--docked' : ''}`}
            style={panelStyle}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, x: panelEnterX, y: panelEnterY, scale: 0.98 }}
            animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, x: panelEnterX * 0.75, y: panelEnterY * 0.75, scale: 0.98 }}
            transition={transition}
          >
            <div className="responsive-filter-panel__header">
              <div>
                <h2 id={titleId} className="responsive-filter-panel__title">{label}</h2>
                <p className="responsive-filter-panel__hint" aria-live="polite">
                  {safeActiveCount > 0
                    ? `${safeActiveCount} active filter${safeActiveCount === 1 ? '' : 's'} · changes apply as you choose`
                    : 'Refine this view · changes apply as you choose'}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {onClear && (
                  <button
                    type="button"
                    className="responsive-filter-panel__clear"
                    aria-label="Clear filters"
                    title="Clear filters"
                    disabled={safeClearableCount === 0}
                    onClick={() => {
                      onClear();
                      window.requestAnimationFrame(() => closeButtonRef.current?.focus());
                    }}
                  >
                    <Eraser size={18} aria-hidden="true" />
                  </button>
                )}
                <button
                  ref={closeButtonRef}
                  type="button"
                  className="responsive-filter-panel__close"
                  aria-label={`Close ${label.toLowerCase()}`}
                  onClick={close}
                >
                  <X size={19} aria-hidden="true" />
                </button>
              </div>
            </div>

            <div className="responsive-filter-panel__fields">
              {children}
            </div>

            <div className="responsive-filter-panel__footer">
              <button type="button" className="responsive-filter-panel__done" onClick={close}>
                Done
              </button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );

  // Docked: the trigger renders in-flow where the component sits; only the
  // scrim + panel are portaled. Floating keeps the old portal-everything shape.
  if (isDocked) {
    return (
      <>
        {trigger}
        {createPortal(overlay, document.body)}
      </>
    );
  }

  return createPortal(
    <>
      {trigger}
      {overlay}
    </>,
    document.body,
  );
};

export default ResponsiveFilters;
