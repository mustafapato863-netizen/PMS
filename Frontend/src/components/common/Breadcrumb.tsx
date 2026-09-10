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

const Breadcrumb: React.FC<BreadcrumbProps> = ({ items, className = '' }) => {
  if (!items || items.length === 0) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className={`breadcrumbs ${className}`}
    >
      <ol className="breadcrumbs__list">
        {items.map((item, idx) => {
        const isLast = idx === items.length - 1;
        const IconComponent = item.icon ? ICON_MAP[item.icon] : null;

        return (
          <li className="breadcrumbs__item" key={`${item.label}-${idx}`}>
            {idx > 0 && (
              <span className="breadcrumbs__separator" aria-hidden="true">
                <ChevronRight size={13} />
              </span>
            )}

            {isLast ? (
              <span
                aria-current="page"
                className="breadcrumbs__current"
              >
                {IconComponent && (
                  <IconComponent
                    size={13}
                    className="breadcrumbs__icon"
                    aria-hidden
                  />
                )}
                <span className="breadcrumbs__label">{item.label}</span>
              </span>
            ) : item.href ? (
              <Link
                to={item.href}
                className="breadcrumbs__link"
              >
                {IconComponent && (
                  <IconComponent
                    size={13}
                    className="breadcrumbs__icon"
                    aria-hidden
                  />
                )}
                <span className="breadcrumbs__label">{item.label}</span>
              </Link>
            ) : (
              <span
                className="breadcrumbs__text"
              >
                {IconComponent && (
                  <IconComponent
                    size={13}
                    className="breadcrumbs__icon"
                    aria-hidden
                  />
                )}
                <span className="breadcrumbs__label">{item.label}</span>
              </span>
            )}
          </li>
        );
        })}
      </ol>
    </nav>
  );
};

export default Breadcrumb;
