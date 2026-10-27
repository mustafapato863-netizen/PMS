import { useId, type ReactNode } from 'react';

interface AdminSectionProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  /** Overview sections sit on the page. Other admin sections keep their own surface. */
  plain?: boolean;
}

/** One elevation level: a token border on the surface colour, no nested glass panels. */
export function AdminSection({ title, description, actions, children, plain = false }: AdminSectionProps) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className={plain ? 'flex min-w-0 flex-col gap-[12px]' : 'min-w-0 space-y-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4'}>
      <div className="flex min-w-0 flex-col gap-[4px] sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 id={titleId} className={plain ? 'text-[17px] font-bold text-[var(--insights-heading)]' : 'text-lg font-bold text-[var(--text-primary)]'}>{title}</h2>
          {description && <p className={plain ? 'max-w-3xl text-[12px] leading-[1.5] text-[var(--text-muted)]' : 'text-sm text-[var(--text-secondary)]'}>{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
