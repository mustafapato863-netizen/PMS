import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Command, Search, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import { useGlobalSearch } from '../../hooks/api/useGlobalSearch';
import type { SearchResultItem } from '../../lib/searchNavigation';
import GlobalSearchResults from './GlobalSearchResults';

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return target.isContentEditable || tagName === 'input' || tagName === 'textarea' || tagName === 'select';
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const media = window.matchMedia(query);
    const listener = () => setMatches(media.matches);
    listener();
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [query]);

  return matches;
}

export default function GlobalSearch() {
  const navigate = useNavigate();
  const location = useLocation();
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const isMobile = useMediaQuery('(max-width: 1279px)');
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const isMac = useMemo(() => /Mac|iPhone|iPad/.test(window.navigator.platform), []);

  const { groupedResults, flatResults, isLoading, error } = useGlobalSearch({
    open,
    query,
    role,
    currentUser,
  });

  useEffect(() => {
    queueMicrotask(() => {
      setOpen(false);
      setQuery('');
      setActiveIndex(0);
    });
  }, [location.pathname, location.search]);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen(true);
        window.setTimeout(() => inputRef.current?.focus(), 0);
        return;
      }

      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (!open || isMobile) {
      return;
    }

    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [isMobile, open]);

  useEffect(() => {
    if (open) {
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open, isMobile]);

  const selectItem = (item: SearchResultItem) => {
    setOpen(false);
    setQuery('');
    navigate(item.path);
  };

  const updateQuery = (value: string) => {
    setQuery(value);
    setActiveIndex(0);
  };

  const onInputKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((current) => (flatResults.length ? (current + 1) % flatResults.length : 0));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((current) => (flatResults.length ? (current - 1 + flatResults.length) % flatResults.length : 0));
      return;
    }
    if (event.key === 'Enter' && flatResults[activeIndex]) {
      event.preventDefault();
      selectItem(flatResults[activeIndex]);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (!open && !isEditableTarget(event.target)) {
      setOpen(true);
    }
  };

  const desktopPanel = (
    <AnimatePresence>
      {open && !isMobile && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="absolute left-0 right-0 top-[calc(100%+0.7rem)] z-50 overflow-hidden rounded-[28px] border border-[var(--border-light)] bg-[var(--bg-surface)]/96 shadow-[0_18px_60px_rgba(15,23,42,0.16)] backdrop-blur-2xl"
        >
          <GlobalSearchResults
            groupedResults={groupedResults}
            activeIndex={activeIndex}
            onHover={setActiveIndex}
            onSelect={selectItem}
            loading={isLoading}
            error={error}
            query={query}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );

  return (
    <>
      <div ref={rootRef} className="relative min-w-0 flex-1 lg:max-w-[320px] xl:max-w-sm 2xl:max-w-md">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex shrink-0 items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)]/86 px-2 py-1.5 text-left shadow-sm backdrop-blur-xl transition-all hover:border-blue-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 sm:px-3 xl:hidden"
          aria-label="Open global search"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-300 shrink-0">
            <Search size={15} />
          </span>
          <span className="hidden sm:inline-block min-w-0 flex-1 truncate text-xs font-semibold text-[var(--text-muted)] max-w-[120px]">
            Search PMS…
          </span>
        </button>

        <div className="hidden xl:block">
          <div
            className={`flex items-center gap-2.5 rounded-[20px] border border-[var(--border-light)] bg-[var(--bg-surface)]/88 px-2.5 py-2 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl transition-all ${open ? 'border-blue-300 shadow-[0_14px_34px_rgba(37,99,235,0.14)]' : 'hover:border-blue-200'}`}
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-300">
              <Search size={15} />
            </span>
            <input
              ref={inputRef}
              value={query}
              onFocus={() => setOpen(true)}
              onChange={(event) => updateQuery(event.target.value)}
              onKeyDown={onInputKeyDown}
              placeholder="Search employees, teams, pages, or actions…"
              className="min-w-0 flex-1 bg-transparent text-[13px] font-semibold text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
              aria-label="Search employees, teams, pages, or actions"
            />
            <span className="flex items-center gap-1 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/80 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--text-secondary)]">
              {isMac ? <Command size={12} /> : null}
              {!isMac ? 'Ctrl' : null}
              <span>K</span>
            </span>
          </div>
          {desktopPanel}
        </div>
      </div>

      <AnimatePresence>
        {open && isMobile && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-slate-950/48 backdrop-blur-sm xl:hidden"
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                setOpen(false);
              }
            }}
          >
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 18 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="mx-3 mt-4 overflow-hidden rounded-[30px] border border-[var(--border-light)] bg-[var(--bg-surface)]/98 shadow-[0_24px_70px_rgba(15,23,42,0.24)]"
            >
              <div className="flex items-center gap-3 border-b border-[var(--border-light)] px-4 py-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-300">
                  <Search size={17} />
                </span>
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(event) => updateQuery(event.target.value)}
                  onKeyDown={onInputKeyDown}
                  placeholder="Search employees, teams, pages…"
                  className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                  aria-label="Search employees, teams, pages, or actions"
                />
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/80 text-[var(--text-muted)]"
                  aria-label="Close search"
                >
                  <X size={16} />
                </button>
              </div>
              <GlobalSearchResults
                groupedResults={groupedResults}
                activeIndex={activeIndex}
                onHover={setActiveIndex}
                onSelect={selectItem}
                loading={isLoading}
                error={error}
                query={query}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
