import { useId, type ReactNode } from 'react';

interface AdminSectionProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}

/** One elevation level: a token border on the surface colour, no nested glass panels. */
export function AdminSection({ title, description, actions, children }: AdminSectionProps) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="min-w-0 space-y-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 id={titleId} className="text-lg font-bold text-[var(--text-primary)]">{title}</h2>
          {description && <p className="text-sm text-[var(--text-secondary)]">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
