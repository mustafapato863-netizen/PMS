import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';

const SECTION_SELECTOR = '[data-section-label]';

type SectionMark = { id: string; label: string };

function readSections(root: HTMLElement): SectionMark[] {
  return [...root.querySelectorAll<HTMLElement>(SECTION_SELECTOR)]
    .filter((node) => node.id && node.dataset.sectionLabel)
    .map((node) => ({ id: node.id, label: node.dataset.sectionLabel ?? node.id }));
}

function sameSections(left: SectionMark[], right: SectionMark[]): boolean {
  return left.length === right.length && left.every((item, index) => item.id === right[index]?.id && item.label === right[index]?.label);
}

export function SectionRail({
  rootRef,
  viewKey,
}: {
  rootRef: RefObject<HTMLElement | null>;
  viewKey: string;
}) {
  const [sections, setSections] = useState<SectionMark[]>([]);
  const [activeId, setActiveId] = useState('');
  const lockRef = useRef<string | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const collect = () => {
      const next = readSections(root);
      setSections((current) => (sameSections(current, next) ? current : next));
      setActiveId((current) => (next.some((section) => section.id === current) ? current : next[0]?.id ?? ''));
    };
    collect();
    const observer = new MutationObserver(collect);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [rootRef, viewKey]);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const nodes = sections
      .map((section) => document.getElementById(section.id))
      .filter((node): node is HTMLElement => node instanceof HTMLElement);
    if (!nodes.length) return;

    const tops = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        if (lockRef.current) return;
        for (const entry of entries) {
          if (entry.isIntersecting) tops.set(entry.target.id, entry.boundingClientRect.top);
          else tops.delete(entry.target.id);
        }
        const ranked = [...tops.entries()].sort((left, right) => left[1] - right[1]);
        const current = ranked.find(([, top]) => top >= 64) ?? ranked[0];
        if (current) setActiveId(current[0]);
      },
      { rootMargin: '-12% 0px -40% 0px', threshold: [0.15, 0.4] },
    );
    for (const node of nodes) observer.observe(node);
    return () => observer.disconnect();
  }, [sections]);

  useEffect(() => {
    const release = () => {
      lockRef.current = null;
    };
    window.addEventListener('scrollend', release);
    return () => window.removeEventListener('scrollend', release);
  }, []);

  const jump = (id: string) => {
    lockRef.current = id;
    setActiveId(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.setTimeout(() => {
      if (lockRef.current === id) lockRef.current = null;
    }, 800);
  };

  if (sections.length < 2) return null;

  return (
    <div className="pointer-events-none sticky top-20 z-20 h-0 overflow-visible">
      <nav
        aria-label="Page sections"
        data-testid="presentation-section-rail"
        className="pointer-events-auto absolute top-0 right-1 flex h-[calc(100vh-10.5rem)] w-10 overflow-visible sm:right-2"
      >
        <div className="relative h-full w-full overflow-visible">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 rounded-full border border-white/70 bg-white/40 shadow-[0_8px_28px_-18px_rgba(15,23,42,0.45)] backdrop-blur-md"
          >
            <span className="absolute top-4 bottom-4 left-1/2 w-px -translate-x-1/2 bg-slate-300/80" />
          </div>
          <div className="relative flex h-full flex-col items-center justify-between overflow-visible px-1 py-4">
            {sections.map((section) => {
              const active = section.id === activeId;
              return (
                <button
                  key={section.id}
                  type="button"
                  aria-current={active ? 'true' : undefined}
                  aria-label={section.label}
                  onClick={() => jump(section.id)}
                  className="group relative z-10 inline-flex size-6 cursor-pointer items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  <span
                    className={`block rounded-full transition-transform duration-150 ease-out group-hover:scale-150 group-focus-visible:scale-150 ${
                      active ? 'size-2.5 bg-blue-600 shadow-[0_0_0_4px_rgba(37,99,235,0.16)]' : 'size-1.5 bg-slate-300 group-hover:bg-slate-500'
                    }`}
                  />
                  <span className="pointer-events-none absolute top-1/2 right-[calc(100%+0.45rem)] -translate-y-1/2">
                    <span
                      data-section-tip={section.label}
                      className="block translate-x-1 rounded-md border border-white/80 bg-white/95 px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap text-slate-600 opacity-0 shadow-sm transition-[opacity,transform] duration-150 ease-out group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100"
                    >
                      {section.label}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </nav>
    </div>
  );
}

export function PresentationSectionFrame({
  viewKey,
  children,
}: {
  viewKey: string;
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  return (
    <div ref={rootRef} className="relative sm:pr-12">
      <SectionRail rootRef={rootRef} viewKey={viewKey} />
      {children}
    </div>
  );
}
