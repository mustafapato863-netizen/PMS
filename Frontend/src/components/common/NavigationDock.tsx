import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { Dock, DockIcon, DockItem, DockLabel } from '../ui/dock';
import '../ui/dock.css';

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

/** Apple-style magnifying dock navigation for tablet and mobile viewports. */
export default function NavigationDock({ items, onOpenMenu, hidden = false }: NavigationDockProps) {
  return (
    <Dock
      ariaLabel="Quick navigation"
      hidden={hidden}
      inert={hidden}
      magnification={68}
      baseWidth={44}
      distance={130}
      panelHeight={58}
      className="navigation-dock"
    >
      {items.map((item) => (
        <DockItem
          key={item.destination}
          isActive={item.active}
          className={item.tabletOnly ? 'navigation-dock-tablet-only' : undefined}
        >
          <DockLabel>{item.label}</DockLabel>
          <Link
            to={item.destination}
            aria-label={`Go to ${item.label}`}
            aria-current={item.active ? 'page' : undefined}
            title={item.title || item.label}
            className={`navigation-dock-item ${item.active ? 'is-active' : ''} ${
              item.tabletOnly ? 'navigation-dock-tablet-only' : ''
            }`}
          >
            <DockIcon className="navigation-dock-icon">{item.icon}</DockIcon>
          </Link>
        </DockItem>
      ))}
      <DockItem className="navigation-dock-menu-slot">
        <DockLabel>Menu</DockLabel>
        <button
          type="button"
          className="navigation-dock-item navigation-dock-menu"
          aria-label="Open full navigation"
          aria-haspopup="dialog"
          aria-controls="responsive-navigation"
          aria-expanded={hidden}
          onClick={onOpenMenu}
        >
          <DockIcon className="navigation-dock-icon">
            <Menu size={20} />
          </DockIcon>
        </button>
      </DockItem>
    </Dock>
  );
}
