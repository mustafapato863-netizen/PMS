import { useState, useEffect, useCallback } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import {
  CalendarDays,
  ChevronDown,
  Menu,
  LogOut,
  Sparkles,
  UserRound,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { MonthKey } from '../../types';
import ThemeToggle from './ThemeToggle';
import GlobalSearch from './GlobalSearch';
import { useUserRole } from '../../context/RoleContext';
import { useAuth } from '../../context/auth';
import { NotificationBell } from '../notifications';
import { usePerformanceCatalog } from '../../hooks/api/usePerformanceCatalog';
import { ProfileSettingsModal } from './ProfileSettingsModal';

// ── route config ──────────────────────────────────────────────────────────────

const ROUTE_TITLES: Record<string, { title: string; subtitle: string }> = {
  '/executive': { title: 'Executive Summary', subtitle: 'Performance overview across all teams' },
  '/operational': { title: 'Team Performance', subtitle: 'CRM-style action and tracking' },
  '/team': { title: 'Team Dashboard', subtitle: 'Deep dive into team performance' },
  '/employee': { title: 'Employee Profile', subtitle: 'Comprehensive history & records' },
  '/pi-management': { title: 'PI Management', subtitle: 'Performance Improvement Plans' },
  '/sip-management': { title: 'SIP Management', subtitle: 'Strict Improvement Plans' },
  '/rewards': { title: 'Rewards & Promotions', subtitle: 'Top performers and recognition' },
  '/reports': { title: 'Reports', subtitle: 'Generate and manage performance reports' },
  '/insights': { title: 'Insights', subtitle: 'Understand what drives performance' },
  '/planning': { title: 'Planning', subtitle: 'Create, track and manage performance plans' },
  '/design-system': { title: 'Design System', subtitle: 'Admin reference for reusable workspace surfaces' },
};

// ── helpers ───────────────────────────────────────────────────────────────────

function getInitials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

function resolveRoute(pathname: string) {
  if (ROUTE_TITLES[pathname]) return ROUTE_TITLES[pathname];
  if (pathname.startsWith('/employee')) return ROUTE_TITLES['/employee'];
  if (pathname.startsWith('/team')) return ROUTE_TITLES['/team'];
  return ROUTE_TITLES['/executive'];
}

// ── sub-components ────────────────────────────────────────────────────────────

import CustomDropdown from './CustomDropdown';

/** Month select */
function MonthSelect({
  value,
  months,
  onChange,
}: {
  value: MonthKey;
  months: string[];
  onChange: (v: string) => void;
}) {
  return (
    <CustomDropdown
      value={value}
      options={['All', ...months]}
      onChange={(v) => onChange(String(v))}
      icon={<CalendarDays size={13} />}
      ariaLabel="Filter by month"
      size="sm"
    />
  );
}

/** Profile dropdown */
function ProfileMenu({
  name,
  username,
  role,
  accessibleTeamCount,
  totalTeamCount,
  isGeneralManager,
  onEditProfile,
  onLogout,
}: {
  name: string;
  username?: string;
  role: string;
  accessibleTeamCount?: number;
  totalTeamCount?: number;
  isGeneralManager?: boolean;
  onEditProfile: () => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const initials = getInitials(name);

  const close = useCallback(() => setOpen(false), []);

  return (
    <div className="relative">
      <motion.button
        whileHover={{ scale: 1.02 }}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="Open user menu"
        className="flex items-center gap-1.5 bg-[var(--bg-surface)]/40 backdrop-blur-sm hover:bg-[var(--bg-surface)]/80 border
          border-[var(--border-light)] rounded-xl px-2 py-1 transition-all shadow-sm"
      >
        <div
          className="w-7 h-7 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center
            justify-center text-[10px] font-bold text-white shadow-sm"
          aria-hidden="true"
        >
          {initials}
        </div>
        <div className="hidden sm:flex flex-col text-left">
          <span className="text-xs font-bold text-[var(--text-primary)] leading-none">{name}</span>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider font-semibold">
              {role}
            </span>
            <span
              className="text-[8px] uppercase tracking-[0.18em] font-extrabold px-1.5 py-0.5 rounded-full border"
              style={{
                color: role === 'Admin' ? 'rgb(109, 40, 217)' : role === 'Manager' ? 'rgb(5, 150, 105)' : role === 'Executive' ? 'rgb(217, 119, 6)' : 'rgb(100, 116, 139)',
                background: role === 'Admin' ? 'rgba(167, 139, 250, 0.12)' : role === 'Manager' ? 'rgba(16, 185, 129, 0.12)' : role === 'Executive' ? 'rgba(251, 191, 36, 0.12)' : 'rgba(148, 163, 184, 0.12)',
                borderColor: role === 'Admin' ? 'rgba(167, 139, 250, 0.28)' : role === 'Manager' ? 'rgba(16, 185, 129, 0.28)' : role === 'Executive' ? 'rgba(251, 191, 36, 0.28)' : 'rgba(148, 163, 184, 0.28)',
              }}
            >
              Active
            </span>
          </div>
        </div>
        <motion.div
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="hidden sm:block"
          aria-hidden="true"
        >
          <ChevronDown size={11} className="text-[var(--text-muted)]" />
        </motion.div>
      </motion.button>

      <AnimatePresence>
        {open && (
          <>
            {/* backdrop — closes menu on outside click */}
            <div
              className="fixed inset-0 z-40"
              onClick={close}
              aria-hidden="true"
            />

            <motion.div
              initial={{ opacity: 0, y: -6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.97 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              role="menu"
              aria-label="User menu"
              className="absolute right-0 mt-2 w-52 bg-[var(--bg-surface)]/95 backdrop-blur-xl rounded-2xl
                shadow-xl border border-[var(--border-light)] p-1.5 z-50"
            >
              {/* user info */}
              <div className="px-3 py-2.5 border-b border-[var(--border-light)] mb-1">
                <p className="text-xs font-bold text-[var(--text-primary)] leading-snug">{name}</p>
                {username && (
                  <p className="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">@{username}</p>
                )}
                <p className="text-[10px] font-bold uppercase tracking-wider mt-1" style={{
                  color: role === 'Admin' ? 'rgb(109, 40, 217)' : role === 'Manager' ? 'rgb(5, 150, 105)' : role === 'Executive' ? 'rgb(217, 119, 6)' : 'rgb(100, 116, 139)',
                }}>
                  {role} access
                </p>
                {role === 'Manager' && (
                  <p className="text-[10px] text-[var(--text-muted)] mt-1">
                    {isGeneralManager
                      ? 'General manager: full team access'
                      : `${accessibleTeamCount || 0} / ${totalTeamCount || 0} teams accessible`}
                  </p>
                )}
              </div>

              <motion.button
                role="menuitem"
                whileHover={{ backgroundColor: 'rgba(59,130,246,0.08)' }}
                onClick={() => { close(); onEditProfile(); }}
                className="mb-1 flex w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] transition-all"
              >
                <UserRound size={13} className="text-blue-500" aria-hidden="true" />
                My profile
              </motion.button>

              <motion.button
                role="menuitem"
                whileHover={{ backgroundColor: 'rgba(239,68,68,0.08)' }}
                onClick={() => { close(); onLogout(); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-semibold
                  text-red-600 rounded-xl transition-all text-left cursor-pointer"
              >
                <LogOut size={13} className="text-red-500" aria-hidden="true" />
                Log out
              </motion.button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

interface HeaderProps {
  onMenuClick?: () => void;
}

const Header = ({ onMenuClick }: HeaderProps) => {
  const { pathname } = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [isScrolled, setIsScrolled] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const { role } = useUserRole();
  const { currentUser, logout, updateProfile, changePassword } = useAuth();
  const { data: performanceCatalog } = usePerformanceCatalog();
  const uniqueMonths = performanceCatalog?.months || [];

  const { title, subtitle } = resolveRoute(pathname);
  const currentMonth = (searchParams.get('month') || 'All') as MonthKey;

  // scroll detection — throttled to animation frame to avoid forced reflow
  useEffect(() => {
    let rafId: number | undefined;
    const handleScroll = () => {
      if (rafId !== undefined) return;
      rafId = requestAnimationFrame(() => {
        setIsScrolled(window.scrollY > 10);
        rafId = undefined;
      });
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (rafId !== undefined) cancelAnimationFrame(rafId);
    };
  }, []);

  const updateFilter = useCallback(
    (key: string, value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set(key, value);
        return next;
      });
    },
    [setSearchParams]
  );

  const handleLogout = useCallback(() => {
    logout();
    window.location.href = '/login';
  }, [logout]);

  return (
    <>
      <motion.header
        initial={{ y: -80, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        aria-label="Application header"
        style={{
          background: 'var(--header-bg)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderColor: 'var(--border-light)',
          willChange: 'transform, box-shadow',
        }}
        className={`sticky top-0 z-30 w-full flex flex-row items-center justify-between
          border-b border-[var(--border-light)]
          transition-[box-shadow,backdrop-filter,background] duration-300 ease-in-out
          h-14 sm:h-16 px-3 sm:px-4 md:px-6 shadow-sm
          ${isScrolled ? 'shadow-[0_4px_24px_rgba(0,0,0,0.09)] backdrop-blur-xl' : ''}`}
      >
        {/* ── Left: title ── */}
        <div className="flex min-w-0 items-center gap-2 sm:gap-2.5 shrink-0 max-w-[160px] sm:max-w-[240px] lg:max-w-none lg:w-[220px] xl:w-[260px]">
          {/* mobile menu trigger */}
          <button
            onClick={onMenuClick}
            aria-label="Open navigation sidebar"
            className="-ml-1 flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-xl p-1.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 xl:hidden"
          >
            <Menu size={20} aria-hidden="true" />
          </button>

          {/* colour accent bar */}
          <div
            className="hidden lg:block h-6 w-[3px] flex-shrink-0 rounded-full bg-gradient-to-b from-blue-500 to-indigo-500"
            aria-hidden="true"
          />

          <div className="min-w-0 flex-1">
            <h1
              className={`font-bold text-[var(--text-primary)] tracking-tight truncate transition-all duration-300
                ${isScrolled ? 'text-sm lg:text-[15px]' : 'text-[15px] lg:text-base'}`}
            >
              {title}
            </h1>
            <p className="mt-0.5 hidden sm:flex items-center gap-1 truncate text-[10px] font-semibold text-blue-600 dark:text-blue-400">
              <Sparkles size={10} className="text-blue-400 flex-shrink-0" aria-hidden="true" />
              {subtitle}
            </p>
          </div>
        </div>

        {/* ── Centre: global search ── */}
        <div className="flex items-center justify-center shrink-0 lg:flex-1 lg:min-w-0 lg:max-w-md lg:mx-auto">
          <GlobalSearch />
        </div>

        {/* ── Right: controls ── */}
        <div className="flex items-center justify-end gap-1.5 md:gap-2 shrink-0">
          <div className="hidden sm:block">
            <MonthSelect
              value={currentMonth}
              months={uniqueMonths || []}
              onChange={(v) => updateFilter('month', v)}
            />
          </div>

          {/* divider */}
          <div className="h-5 w-px bg-[var(--border-light)] hidden sm:block" aria-hidden="true" />

          <NotificationBell />

          <ThemeToggle />

          {currentUser && (
            <ProfileMenu
              name={currentUser.name}
              username={currentUser.username}
              role={role}
              accessibleTeamCount={currentUser.accessible_team_count}
              totalTeamCount={currentUser.total_team_count}
              isGeneralManager={currentUser.is_general_manager}
              onEditProfile={() => setProfileOpen(true)}
              onLogout={handleLogout}
            />
          )}
        </div>
      </motion.header>
      {profileOpen && currentUser && (
        <ProfileSettingsModal
          user={currentUser}
          onClose={() => setProfileOpen(false)}
          onUpdateProfile={updateProfile}
          onChangePassword={changePassword}
        />
      )}
    </>
  );
};

export default Header;
