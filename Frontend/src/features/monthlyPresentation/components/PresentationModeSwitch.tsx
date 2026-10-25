import { Presentation } from 'lucide-react';

export function PresentationModeSwitch({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <div className="h-full w-full">
      <div
        title="Presentation Mode"
        onClick={() => onChange(!enabled)}
        className={`flex h-full w-full cursor-pointer items-center justify-center gap-1.5 rounded-full px-2 select-none ${
          enabled ? 'bg-sky-100 text-sky-800' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
        }`}
      >
        <Presentation
          size={15}
          className={enabled ? 'text-blue-600' : 'text-slate-500'}
          aria-hidden="true"
        />
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Presentation Mode"
          data-testid="presentation-mode-switch"
          onClick={(e) => {
            e.stopPropagation();
            onChange(!enabled);
          }}
          className={`compact-control relative inline-flex !h-5 !min-h-0 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none ${
            enabled ? 'bg-blue-600' : 'bg-slate-200'
          }`}
        >
          <span
            className={`pointer-events-none absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow-xs transition-transform duration-150 ${
              enabled ? 'translate-x-4' : 'translate-x-0'
            }`}
          />
        </button>
      </div>
    </div>
  );
}

