import { useEffect, useState, type ReactNode } from 'react';
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

const PHONE_QUERY = '(max-width: 767px)';

/** True below 768px, where the dock shows a stacked icon + label instead of icon-only. */
function usePhoneViewport(): boolean {
  const [isPhone, setIsPhone] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia(PHONE_QUERY).matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(PHONE_QUERY);
    const onChange = () => setIsPhone(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isPhone;
}

/** Apple-style magnifying dock navigation for tablet and mobile viewports. */
export default function NavigationDock({ items, onOpenMenu, hidden = false }: NavigationDockProps) {
  const isPhone = usePhoneViewport();
  const [autoHidden, setAutoHidden] = useState(false);

  // Auto-hide the dock while scrolling down; it reappears on scroll up, so it
  // never sits on top of page content mid-scroll. End-of-page clearance is
  // unchanged (.has-navigation-dock .app-route-padding). Never auto-hides when
  // the user prefers reduced motion.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let lastY = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const y = window.scrollY;
        const dy = y - lastY;
        lastY = y;
        if (y <= 96) {
          setAutoHidden(false);
          return;
        }
        if (dy > 8) setAutoHidden(true);
        else if (dy < -8) setAutoHidden(false);
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <Dock
      ariaLabel="Quick navigation"
      hidden={hidden}
      inert={hidden}
      magnification={68}
      baseWidth={isPhone ? 52 : 44}
      distance={130}
      panelHeight={isPhone ? 64 : 58}
      className={autoHidden ? 'navigation-dock dock-auto-hidden' : 'navigation-dock'}
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
            <span className="navigation-dock-label" aria-hidden="true">
              {item.label}
            </span>
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
          <span className="navigation-dock-label" aria-hidden="true">
            Menu
          </span>
        </button>
      </DockItem>
    </Dock>
  );
}
