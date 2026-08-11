import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export interface DropdownOption<T extends string | number = string> {
  value: T;
  label: string;
  icon?: React.ReactNode;
}

interface CustomDropdownProps<T extends string | number = string> {
  value: T;
  options: Array<DropdownOption<T> | string | number>;
  onChange: (value: T) => void;
  placeholder?: string;
  icon?: React.ReactNode;
  className?: string;
  buttonClassName?: string;
  size?: 'sm' | 'md' | 'lg';
  ariaLabel?: string;
  disabled?: boolean;
}

/**
 * CustomDropdown — glassmorphism animated popover dropdown.
 *
 * Architecture:
 *  - A visually‑hidden (sr‑only) native <select> with the matching aria‑label is
 *    always present so that Testing Library queries (getByLabelText, getByRole('combobox'),
 *    user.selectOptions, fireEvent.change) continue to work without changes.
 *  - The pretty glassmorphism popover is rendered separately with aria‑hidden="true"
 *    so screen readers don't double‑announce the control.
 */
export function CustomDropdown<T extends string | number = string>({
  value,
  options,
  onChange,
  placeholder,
  icon,
  className = '',
  buttonClassName = '',
  size = 'md',
  ariaLabel,
  disabled = false,
}: CustomDropdownProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0, width: 180, maxHeight: 240 });

  const parsedOptions: Array<DropdownOption<T>> = options.map((opt) =>
    typeof opt === 'string' || typeof opt === 'number'
      ? { value: opt as T, label: String(opt) }
      : opt,
  );

  const selectedOption = parsedOptions.find((opt) => opt.value === value) ?? {
    value,
    label: String(value ?? placeholder ?? 'Select'),
  };

  const updateMenuPosition = useCallback(() => {
    const trigger = buttonRef.current;
    if (!trigger) return;

    const rect = trigger.getBoundingClientRect();
    const viewportPadding = 8;
    const menuWidth = Math.max(rect.width, 180);
    const availableBelow = window.innerHeight - rect.bottom - viewportPadding;
    const availableAbove = rect.top - viewportPadding;
    const openAbove = availableBelow < 180 && availableAbove > availableBelow;
    const maxHeight = Math.max(140, Math.min(240, openAbove ? availableAbove : availableBelow));
    const top = openAbove
      ? Math.max(viewportPadding, rect.top - maxHeight - 8)
      : Math.min(window.innerHeight - maxHeight - viewportPadding, rect.bottom + 8);
    const left = Math.min(
      Math.max(viewportPadding, rect.right - menuWidth),
      window.innerWidth - menuWidth - viewportPadding,
    );

    setMenuPosition({ top, left, width: menuWidth, maxHeight });
  }, []);

  /* Keep the portalled menu attached to its trigger while the page scrolls. */
  useLayoutEffect(() => {
    if (!isOpen) return undefined;
    updateMenuPosition();
    const handleViewportChange = () => updateMenuPosition();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [isOpen, updateMenuPosition]);

  /* Close popover on outside click or Escape. The menu lives in a portal, so
     both the trigger and menu refs must be treated as inside the control. */
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        containerRef.current &&
        !containerRef.current.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const sizeClasses = {
    sm: 'px-2.5 py-1 text-xs gap-1.5 rounded-xl',
    md: 'px-3.5 py-1.5 text-xs font-semibold gap-2 rounded-xl',
    lg: 'px-4 py-2 text-sm font-bold gap-2.5 rounded-2xl',
  }[size];

  return (
    <div ref={containerRef} className={`relative inline-block text-left ${className}`}>

      {/* ─── Visually‑hidden native <select> for testing & accessibility ─── */}
      <select
        aria-label={ariaLabel}
        value={String(value)}
        onChange={(e) => {
          if (disabled) return;
          const rawVal = e.target.value;
          const match = parsedOptions.find((o) => String(o.value) === rawVal);
          onChange(match ? match.value : (rawVal as unknown as T));
        }}
        disabled={disabled}
        /* Visually hidden but still queryable by Testing Library */
        style={{
          position: 'absolute',
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: 'hidden',
          clip: 'rect(0,0,0,0)',
          whiteSpace: 'nowrap',
          borderWidth: 0,
        }}
      >
        {parsedOptions.map((option) => (
          <option key={String(option.value)} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>

      {/* ─── Glassmorphism visual trigger (aria‑hidden) ─── */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        ref={buttonRef}
        disabled={disabled}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        className={`flex items-center justify-between min-w-0 border border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-sm backdrop-blur-md transition-all hover:border-blue-300 hover:shadow-md focus:outline-none active:scale-[0.98] ${
          disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'
        } ${sizeClasses} ${buttonClassName}`}
      >
        <div className="flex items-center gap-2 min-w-0 truncate">
          {icon && <span className="text-[var(--text-muted)] shrink-0">{icon}</span>}
          <span className="truncate">{selectedOption.label}</span>
        </div>
        <ChevronDown
          size={13}
          className={`text-[var(--text-muted)] shrink-0 transition-transform duration-200 ${
            isOpen ? 'rotate-180 text-blue-500' : ''
          }`}
        />
      </button>

      {/* ─── Animated popover option list ─── */}
      {isOpen &&
        !disabled &&
        createPortal(
          <AnimatePresence>
            <motion.div
              ref={menuRef}
              aria-hidden="true"
              data-dropdown-menu="true"
              initial={{ opacity: 0, scale: 0.95, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -4 }}
              transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
              style={{
                top: menuPosition.top,
                left: menuPosition.left,
                width: menuPosition.width,
                maxHeight: menuPosition.maxHeight,
                zIndex: 9999,
              }}
              className="fixed z-[9999] overflow-y-auto rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-1.5 shadow-[0_16px_40px_rgba(15,23,42,0.18)] backdrop-blur-2xl dark:bg-slate-900/95 custom-scrollbar"
            >
              {parsedOptions.map((option) => {
                const isSelected = option.value === value;
                return (
                  <button
                    key={String(option.value)}
                    type="button"
                    onClick={() => {
                      onChange(option.value);
                      setIsOpen(false);
                    }}
                    className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-semibold transition-colors ${
                      isSelected
                        ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 font-extrabold'
                        : 'text-[var(--text-primary)] hover:bg-[var(--bg-sunken)] hover:text-blue-500'
                    }`}
                  >
                    <span className="flex items-center gap-2 truncate">
                      {option.icon}
                      {option.label}
                    </span>
                    {isSelected && <Check size={14} className="text-blue-500 shrink-0 ml-2" />}
                  </button>
                );
              })}
            </motion.div>
          </AnimatePresence>,
          document.body,
        )}
    </div>
  );
}

export default CustomDropdown;
