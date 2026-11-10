import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Check, ChevronDown } from 'lucide-react';

export interface AiScopeOption {
  value: string;
  label: string;
  badge?: string;
}

interface AiScopeDropdownProps {
  ariaLabel: string;
  prefix: string;
  value: string;
  defaultValue: string;
  options: AiScopeOption[];
  icon: ReactNode;
  onChange: (nextValue: string) => void;
}

export default function AiScopeDropdown({
  ariaLabel,
  prefix,
  value,
  defaultValue,
  options,
  icon,
  onChange,
}: AiScopeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption =
    options.find((opt) => opt.value === value) || options[0];
  const isFiltered = value !== defaultValue;

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        disabled={options.length === 0}
        onClick={() => setIsOpen((prev) => !prev)}
        className={`group inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] transition-all ${
          isOpen
            ? 'border-blue-500 bg-sky-50/70 text-slate-900 shadow-xs ring-3 ring-blue-500/10'
            : isFiltered
              ? 'border-sky-300 bg-sky-50/60 text-slate-900 shadow-2xs hover:border-blue-400'
              : 'border-slate-200/90 bg-white/95 text-slate-700 shadow-2xs hover:border-sky-300 hover:bg-slate-50/70'
        }`}
      >
        <span
          className={`shrink-0 transition-colors ${
            isOpen || isFiltered
              ? 'text-blue-600'
              : 'text-slate-400 group-hover:text-blue-600'
          }`}
        >
          {icon}
        </span>
        <span className="font-semibold text-slate-400">{prefix}:</span>
        <span
          className={`font-extrabold ${
            isFiltered ? 'text-blue-700' : 'text-slate-800'
          }`}
        >
          {selectedOption?.label ?? 'Unavailable'}
        </span>
        {isFiltered && (
          <span
            className="h-1.5 w-1.5 rounded-full bg-blue-600"
            aria-hidden="true"
          />
        )}
        <ChevronDown
          size={13}
          className={`ml-0.5 shrink-0 text-slate-400 transition-transform duration-150 ${
            isOpen ? 'rotate-180 text-blue-600' : 'group-hover:text-slate-600'
          }`}
        />
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          className="absolute right-0 top-[calc(100%+6px)] z-50 min-w-[210px] origin-top-right rounded-2xl border border-slate-200/90 bg-white/98 p-1.5 shadow-[0_16px_36px_-6px_rgba(15,23,42,0.14)] backdrop-blur-xl ring-1 ring-slate-900/5"
        >
          <div className="px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
            Select {prefix}
          </div>
          <div className="mt-0.5 space-y-0.5">
            {options.map((opt) => {
              const active = opt.value === value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`flex w-full items-center justify-between gap-3 rounded-xl px-2.5 py-1.5 text-left text-xs transition-all ${
                    active
                      ? 'bg-gradient-to-r from-blue-50 via-sky-50/90 to-emerald-50/40 font-extrabold text-blue-700 shadow-2xs ring-1 ring-sky-200/80'
                      : 'font-semibold text-slate-700 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        active ? 'bg-blue-600' : 'bg-slate-300'
                      }`}
                      aria-hidden="true"
                    />
                    <span>{opt.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {opt.badge && (
                      <span
                        className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                          active
                            ? 'bg-white/90 text-blue-700'
                            : 'bg-slate-100 text-slate-500'
                        }`}
                      >
                        {opt.badge}
                      </span>
                    )}
                    {active && (
                      <Check
                        size={13}
                        className="shrink-0 text-blue-600"
                        strokeWidth={2.5}
                      />
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
