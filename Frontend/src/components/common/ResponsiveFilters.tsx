import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ChevronDown, SlidersHorizontal, X } from 'lucide-react';

interface ResponsiveFiltersProps {
  children: ReactNode;
  activeCount?: number;
  label?: string;
  className?: string;
}

/**
 * Keeps the desktop filter bar visible while turning the same controls into a
 * focused bottom sheet on small screens. The controls are rendered once so
 * native accessibility/test selectors remain stable across breakpoints.
 */
const ResponsiveFilters = ({
  children,
  activeCount = 0,
  label = 'Filters',
  className = '',
}: ResponsiveFiltersProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const titleId = useId();
  const headingId = `${titleId}-heading`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const safeActiveCount = Math.max(0, activeCount);

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

  return (
    <div className={`responsive-filter-surface ${className}`.trim()}>
      <button
        ref={triggerRef}
        type="button"
        className="responsive-filter-trigger"
        aria-label={safeActiveCount > 0 ? `${label}, ${safeActiveCount} active filters` : label}
        aria-expanded={isOpen}
        aria-controls={titleId}
        onClick={() => setIsOpen((open) => !open)}
      >
        <SlidersHorizontal size={17} aria-hidden="true" />
        <span>{label}</span>
        {safeActiveCount > 0 && (
          <span className="responsive-filter-count" aria-label={`${safeActiveCount} active filters`}>
            {safeActiveCount}
          </span>
        )}
        <ChevronDown size={16} className={isOpen ? 'rotate-180' : ''} aria-hidden="true" />
      </button>

      {isOpen && (
        <button
          type="button"
          className="responsive-filter-scrim"
          aria-label={`Close ${label.toLowerCase()}`}
          onClick={close}
        />
      )}

      <div
        id={titleId}
        ref={panelRef}
        className="responsive-filter-panel"
        role={isOpen ? 'dialog' : undefined}
        aria-modal={isOpen ? true : undefined}
        aria-labelledby={isOpen ? headingId : undefined}
      >
        <div className="responsive-filter-panel__header">
          <div>
            <p id={headingId} className="responsive-filter-panel__title">{label}</p>
            <p className="responsive-filter-panel__hint">
              {safeActiveCount > 0 ? `${safeActiveCount} active filter${safeActiveCount === 1 ? '' : 's'}` : 'Refine the dashboard view'}
            </p>
          </div>
          <button ref={closeButtonRef} type="button" className="responsive-filter-panel__close" aria-label={`Close ${label.toLowerCase()}`} onClick={close}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="responsive-filter-panel__fields rf-filter-bar">
          {children}
        </div>

        <div className="responsive-filter-panel__footer">
          <button type="button" className="responsive-filter-panel__done" onClick={close}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default ResponsiveFilters;
