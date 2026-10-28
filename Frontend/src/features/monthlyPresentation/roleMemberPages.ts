/** People rows shown at once on a role detail. The next page is sliced ahead of the click. */
export const ROLE_MEMBER_PAGE_SIZE = 10;

export interface MemberPageWindow<T> {
  page: number;
  pageCount: number;
  pageSize: number;
  visible: readonly T[];
  rangeStart: number;
  rangeEnd: number;
}

/**
 * Returns one page and stores the following page in `cache`.
 * A later call for that following page reuses the stored rows.
 */
export function memberPageWindow<T>(
  items: readonly T[],
  page: number,
  cache: Map<string, readonly T[]>,
  listKey: string,
  pageSize = ROLE_MEMBER_PAGE_SIZE,
): MemberPageWindow<T> {
  const size = Math.max(1, pageSize);
  const pageCount = Math.max(1, Math.ceil(items.length / size));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const load = (index: number) => {
    const key = `${listKey}:${index}`;
    const stored = cache.get(key);
    if (stored) return stored;
    const slice = items.slice(index * size, index * size + size);
    cache.set(key, slice);
    return slice;
  };
  const visible = load(safePage);
  if (safePage + 1 < pageCount) load(safePage + 1);
  return {
    page: safePage,
    pageCount,
    pageSize: size,
    visible,
    rangeStart: items.length === 0 ? 0 : safePage * size + 1,
    rangeEnd: Math.min(items.length, (safePage + 1) * size),
  };
}
