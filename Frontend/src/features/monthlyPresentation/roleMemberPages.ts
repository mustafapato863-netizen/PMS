/** People rows shown at once on a role or team detail. All rows are already loaded client-side. */
export const ROLE_MEMBER_PAGE_SIZE = 10;
export const TEAM_AGENT_PAGE_SIZE = 10;

export interface MemberPageWindow<T> {
  page: number;
  pageCount: number;
  pageSize: number;
  visible: readonly T[];
  cachedNext: readonly T[];
  rangeStart: number;
  rangeEnd: number;
}

/**
 * Returns a local page window with pre-cached next page buffer; paging never triggers another data request.
 */
export function memberPageWindow<T>(
  items: readonly T[],
  page: number,
  pageSize = ROLE_MEMBER_PAGE_SIZE,
): MemberPageWindow<T> {
  const size = Math.max(1, pageSize);
  const pageCount = Math.max(1, Math.ceil(items.length / size));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const visible = items.slice(safePage * size, safePage * size + size);
  const cachedNext =
    safePage + 1 < pageCount
      ? items.slice((safePage + 1) * size, (safePage + 2) * size)
      : [];
  return {
    page: safePage,
    pageCount,
    pageSize: size,
    visible,
    cachedNext,
    rangeStart: items.length === 0 ? 0 : safePage * size + 1,
    rangeEnd: Math.min(items.length, (safePage + 1) * size),
  };
}
