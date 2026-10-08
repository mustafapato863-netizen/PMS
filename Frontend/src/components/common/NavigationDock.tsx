import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';

export interface NavigationDockItem {
  label: string;
  destination: string;
  icon: ReactNode;
  active: boolean;
  tabletOnly?: boolean;
  title?: string;
}

interface NavigationDockProps {
  items: NavigationDockItem[];
  onOpenMenu: () => void;
  hidden?: boolean;
}

/** Touch-first adaptation of the dock reference: no pointer tracking or springs. */
export default function NavigationDock({ items, onOpenMenu, hidden = false }: NavigationDockProps) {
  return (
    <nav className="navigation-dock" aria-label="Quick navigation" hidden={hidden} inert={hidden}>
      {items.map((item) => (
        <Link
          key={item.destination}
          to={item.destination}
          aria-label={`Go to ${item.label}`}
          aria-current={item.active ? 'page' : undefined}
          title={item.title || item.label}
          className={`navigation-dock-item ${item.active ? 'is-active' : ''} ${item.tabletOnly ? 'navigation-dock-tablet-only' : ''}`}
        >
          <span className="navigation-dock-icon" aria-hidden="true">{item.icon}</span>
          <span className="navigation-dock-label">{item.label}</span>
        </Link>
      ))}
      <button
        type="button"
        className="navigation-dock-item navigation-dock-menu"
        aria-label="Open full navigation"
        aria-haspopup="dialog"
        aria-controls="responsive-navigation"
        aria-expanded={hidden}
        onClick={onOpenMenu}
      >
        <span className="navigation-dock-icon" aria-hidden="true"><Menu size={20} /></span>
        <span>Menu</span>
      </button>
    </nav>
  );
}
