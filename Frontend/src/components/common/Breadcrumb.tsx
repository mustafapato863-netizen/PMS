import React from 'react';
import { Link } from 'react-router-dom';
import { Home, Users, ChevronRight, Calendar, LayoutDashboard, User } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  href?: string;
  icon?: 'home' | 'teams' | 'team' | 'employee' | 'calendar' | 'dashboard';
}

const ICON_MAP = {
  home: Home,
  dashboard: LayoutDashboard,
  teams: Users,
  team: Users,
  employee: User,
  calendar: Calendar,
};

interface BreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

/**
 * Soft Colored Breadcrumb — Option 3 style.
 * - Simple icons on key segments
 * - Blue accent on current (last) page with a soft pill background
 * - No outer card — fits inline below page headers
 * - Supports dark mode
 */
const Breadcrumb: React.FC<BreadcrumbProps> = ({ items, className = '' }) => {
  if (!items || items.length === 0) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className={`flex items-center flex-wrap gap-0.5 text-[13px] font-medium ${className}`}
    >
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1;
        const IconComponent = item.icon ? ICON_MAP[item.icon] : null;

        return (
          <React.Fragment key={idx}>
            {idx > 0 && (
              <ChevronRight
                size={13}
                className="text-[var(--text-muted)] opacity-50 mx-0.5 shrink-0"
                aria-hidden
              />
            )}

            {isLast ? (
              /* Current page — soft blue pill */
              <span
                aria-current="page"
                className="inline-flex max-w-full items-center gap-1.5 px-2.5 py-0.5 rounded-full
                           bg-blue-50 dark:bg-blue-500/10
                           text-blue-700 dark:text-blue-400
                           font-semibold tracking-wide min-w-0"
              >
                {IconComponent && (
                  <IconComponent
                    size={13}
                    className="shrink-0 text-blue-500 dark:text-blue-400"
                    aria-hidden
                  />
                )}
                <span className="truncate max-w-[220px] sm:max-w-[360px]">{item.label}</span>
              </span>
            ) : item.href ? (
              /* Clickable ancestor */
              <Link
                to={item.href}
                className="inline-flex max-w-full items-center gap-1.5 px-1.5 py-0.5 rounded-md
                           text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                           hover:bg-[var(--bg-sunken)]
                           transition-colors duration-150 min-w-0"
              >
                {IconComponent && (
                  <IconComponent
                    size={13}
                    className="shrink-0 text-[var(--text-muted)]"
                    aria-hidden
                  />
                )}
                <span className="truncate max-w-[140px] sm:max-w-[220px]">{item.label}</span>
              </Link>
            ) : (
              /* Non-clickable ancestor */
              <span
                className="inline-flex max-w-full items-center gap-1.5 px-1.5 py-0.5
                           text-[var(--text-secondary)] min-w-0"
              >
                {IconComponent && (
                  <IconComponent
                    size={13}
                    className="shrink-0 text-[var(--text-muted)]"
                    aria-hidden
                  />
                )}
                <span className="truncate max-w-[140px] sm:max-w-[220px]">{item.label}</span>
              </span>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
};

export default Breadcrumb;
