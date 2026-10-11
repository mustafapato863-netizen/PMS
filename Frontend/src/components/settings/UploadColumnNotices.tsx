import {
  AMBIGUOUS_COLUMNS_DETAIL,
  AMBIGUOUS_COLUMNS_TITLE,
  OPTIONAL_COLUMNS_DETAIL,
  OPTIONAL_COLUMNS_TITLE,
  UNMAPPED_COLUMNS_DETAIL,
  UNMAPPED_COLUMNS_TITLE,
  type ColumnWarning,
  type ColumnWarningCode,
} from './uploadHeaderNotices';

const COPY: Record<ColumnWarningCode, { title: string; detail: string }> = {
  unmapped_columns: { title: UNMAPPED_COLUMNS_TITLE, detail: UNMAPPED_COLUMNS_DETAIL },
  optional_columns: { title: OPTIONAL_COLUMNS_TITLE, detail: OPTIONAL_COLUMNS_DETAIL },
  ambiguous_alias: { title: AMBIGUOUS_COLUMNS_TITLE, detail: AMBIGUOUS_COLUMNS_DETAIL },
};

function ColumnNoticeGroup({ code, warnings }: { code: ColumnWarningCode; warnings: ColumnWarning[] }) {
  const copy = COPY[code];
  const truncated = warnings.some((warning) => warning.truncated);
  return (
    <section aria-label={copy.title} className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-xs text-amber-900 dark:text-amber-100">
      <h4 className="font-extrabold">{copy.title}</h4>
      <p className="mt-1 leading-relaxed">{copy.detail}</p>
      <ul className="mt-2 max-h-48 list-disc space-y-1 overflow-y-auto pl-5">
        {warnings.flatMap((warning) => warning.headers.map((header) => (
          <li key={`${warning.sheet}-${header}`}>{`${warning.sheet}: ${header}`}</li>
        )))}
      </ul>
      {truncated && <p className="mt-2 leading-relaxed">Some column names were left out of this notice.</p>}
    </section>
  );
}

export function UploadColumnNotices({ warnings }: { warnings: ColumnWarning[] }) {
  const groups = (['unmapped_columns', 'optional_columns', 'ambiguous_alias'] as const)
    .map((code) => ({ code, warnings: warnings.filter((warning) => warning.code === code) }))
    .filter((group) => group.warnings.length > 0);
  if (!groups.length) return null;
  return (
    <div className="space-y-2">
      {groups.map((group) => <ColumnNoticeGroup key={group.code} code={group.code} warnings={group.warnings} />)}
    </div>
  );
}
