import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Database, SlidersHorizontal, Users, type LucideIcon } from 'lucide-react';
import { AdminSection } from './AdminSection';
import { settingsPathFor, type SettingsRoutePage } from './settingsNavigation';

interface OverviewArea {
  page: SettingsRoutePage;
  title: string;
  description: string;
  action: string;
  icon: LucideIcon;
}

// Navigation only: no data is fetched on this page yet.
const AREAS: OverviewArea[] = [
  {
    page: 'upload',
    title: 'Data',
    description: 'Upload employee and management workbooks, and back up or restore corrective action records.',
    action: 'Open data uploads',
    icon: Database,
  },
  {
    page: 'kpis',
    title: 'Evaluation',
    description: 'Set monthly targets, weights and direction for each scope, then approve and apply the month.',
    action: 'Open evaluation settings',
    icon: SlidersHorizontal,
  },
  {
    page: 'users',
    title: 'Access',
    description: 'Manage user accounts, their roles and their access to teams.',
    action: 'Manage users',
    icon: Users,
  },
  {
    page: 'system_errors',
    title: 'System',
    description: 'Review recent server failures and trace each one to the request that caused it.',
    action: 'Review system errors',
    icon: Activity,
  },
];

export function AdminOverview() {
  return (
    <AdminSection title="Areas" description="Choose an area to configure. Each area has its own address, so you can return to it directly.">
      <ul className="grid gap-3 md:grid-cols-2">
        {AREAS.map(({ page, title, description, action, icon: Icon }) => (
          <li key={page}>
            <article className="flex h-full flex-col gap-3 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4">
              <div className="flex items-center gap-3">
                <span className="shrink-0 rounded-xl bg-blue-500/10 p-2 text-blue-600 dark:text-blue-400">
                  <Icon size={18} aria-hidden="true" />
                </span>
                <h3 className="text-base font-bold text-[var(--text-primary)]">{title}</h3>
              </div>
              <p className="text-sm text-[var(--text-secondary)]">{description}</p>
              <Link
                to={settingsPathFor(page)}
                className="mt-auto inline-flex min-h-11 w-fit items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-sm font-bold text-[var(--text-primary)] transition-colors duration-200 hover:border-blue-500/30 hover:text-blue-600 motion-reduce:transition-none dark:hover:text-blue-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)]"
              >
                {action}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </article>
          </li>
        ))}
      </ul>
    </AdminSection>
  );
}
