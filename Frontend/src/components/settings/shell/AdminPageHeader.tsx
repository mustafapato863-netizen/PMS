import type { ReactNode } from 'react';

interface AdminPageHeaderProps {
  title: string;
  description?: string;
  badge?: ReactNode;
  actions?: ReactNode;
}

export function AdminPageHeader({ title, description, badge, actions }: AdminPageHeaderProps) {
  return (
    <header className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-[-0.03em] text-[var(--insights-heading)]">{title}</h1>
          {badge}
        </div>
        {description && <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
