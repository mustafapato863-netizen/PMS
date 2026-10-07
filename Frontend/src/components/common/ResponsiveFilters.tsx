import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Eraser, Filter, X } from 'lucide-react';
import './ResponsiveFilters.css';

interface ResponsiveFiltersProps {
  children: ReactNode;
  activeCount?: number;
  clearableCount?: number;
  onClear?: () => void;
  label?: string;
  className?: string;
}

interface FloatingPosition {
  x: number;
  y: number;
}

const FILTER_POSITION_KEY = 'pms:responsive-filter-position:v1';

function filterButtonSize() {
  return window.innerWidth <= 639 ? 50 : 54;
}

function clampPosition(position: FloatingPosition): FloatingPosition {
  if (typeof window === 'undefined') return position;
  const size = filterButtonSize();
  return {
    x: Math.round(Math.max(0, Math.min(position.x, window.innerWidth - size))),
    y: Math.round(Math.max(0, Math.min(position.y, window.innerHeight - size))),
  };
}

function defaultFilterPosition(): FloatingPosition {
  if (typeof window === 'undefined') return { x: 0, y: 0 };
  const size = filterButtonSize();
  const edge = window.innerWidth <= 639 ? 12 : 14;
  return clampPosition({
    x: window.innerWidth - size - edge,
    y: edge,
  });
}

function initialFilterPosition(): FloatingPosition {
  const fallback = defaultFilterPosition();
  if (typeof window === 'undefined') return fallback;
  try {
    const stored = window.localStorage.getItem(FILTER_POSITION_KEY);
    if (!stored) return fallback;
    const parsed = JSON.parse(stored) as Partial<FloatingPosition>;
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') return fallback;
    return clampPosition({ x: parsed.x, y: parsed.y });
  } catch {
    return fallback;
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
}: ResponsiveFiltersProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState(initialFilterPosition);
  const [isDragging, setIsDragging] = useState(false);
  const titleId = useId();
  const panelId = `${titleId}-panel`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origin: FloatingPosition; moved: boolean } | null>(null);
  const suppressClickRef = useRef(false);
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
    const handleResize = () => setPosition((current) => clampPosition(current));
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(FILTER_POSITION_KEY, JSON.stringify(position));
      } catch {
        // The floating button remains usable when browser storage is unavailable.
      }
    }, 100);
    return () => window.clearTimeout(timer);
  }, [position]);

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
      setPosition(defaultFilterPosition());
      return;
    }
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    setPosition((current) => clampPosition({ x: current.x + move.x, y: current.y + move.y }));
  };

  const close = useCallback(() => {
    setIsOpen(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!isOpen) return undefined;

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
  }, [close, isOpen]);

  if (typeof document === 'undefined') return null;

  const transition = reduceMotion
    ? { duration: 0.01 }
    : { duration: 0.24, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] };
  const panelHalfHeight = typeof window === 'undefined' ? 0 : window.innerHeight * 0.42;
  const panelTop = typeof window === 'undefined'
    ? 0
    : Math.max(panelHalfHeight + 12, Math.min(position.y + buttonSize / 2, window.innerHeight - panelHalfHeight - 12));
  const panelStyle = isCompact ? undefined : {
    top: `${panelTop}px`,
    left: panelOpensRight ? `${position.x + buttonSize + 12}px` : 'auto',
    right: panelOpensRight ? 'auto' : `${window.innerWidth - position.x + 12}px`,
    width: `${panelWidth}px`,
    transformOrigin: panelOpensRight ? 'left center' : 'right center',
  };

  return createPortal(
    <>
      <div className={`responsive-filter-launcher ${className}`.trim()} style={{ left: position.x, top: position.y }}>
        <button
          ref={triggerRef}
          type="button"
          className={`responsive-filter-trigger${isDragging ? ' is-dragging' : ''}`}
          aria-label={`${accessibleLabel}. Drag to move; use Alt plus arrow keys, or Alt plus Home to reset`}
          aria-expanded={isOpen}
          aria-controls={panelId}
          aria-haspopup="dialog"
          aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown Alt+ArrowLeft Alt+ArrowRight Alt+Home"
          title={`${label} · drag to move · Alt+arrow keys to reposition`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onKeyDown={handleLauncherKeyDown}
          onClick={(event) => {
            if (suppressClickRef.current) {
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

      <AnimatePresence initial={false}>
        {isOpen && (
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
              className="responsive-filter-panel"
              style={panelStyle}
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, x: panelOpensRight ? -24 : 24, scale: 0.98 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={reduceMotion ? { opacity: 0 } : { opacity: 0, x: panelOpensRight ? -18 : 18, scale: 0.98 }}
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
    </>,
    document.body,
  );
};

export default ResponsiveFilters;
