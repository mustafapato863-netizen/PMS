import React, { useState, useRef, useEffect } from 'react';
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

  const parsedOptions: Array<DropdownOption<T>> = options.map((opt) =>
    typeof opt === 'string' || typeof opt === 'number'
      ? { value: opt as T, label: String(opt) }
      : opt,
  );

  const selectedOption = parsedOptions.find((opt) => opt.value === value) ?? {
    value,
    label: String(value ?? placeholder ?? 'Select'),
  };

  /* Close popover on outside click */
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
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
      <AnimatePresence>
        {isOpen && !disabled && (
          <motion.div
            aria-hidden="true"
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 4 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="absolute right-0 z-50 mt-1 min-w-[160px] max-h-60 overflow-y-auto rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-1.5 shadow-[0_16px_40px_rgba(15,23,42,0.18)] backdrop-blur-2xl dark:bg-slate-900/95 custom-scrollbar"
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
        )}
      </AnimatePresence>
    </div>
  );
}

export default CustomDropdown;
