/**
 * User-facing team name versus the stored source name.
 *
 * Coding, Submission and Re-Submission each exist once per country. Egypt keeps
 * its own source rows (Coding EGY, Submission EGY, Resubmission, Re-Submission EGY).
 * UAE keeps Coding, Submission and Re-Submission. The page shows the business
 * name and carries the country in the region filter.
 *
 * Pre-Approvals IP and Pre-Approvals IP Offshore are not aliases. Both are Egypt
 * teams with different workbook columns and KPI definitions, so they stay separate.
 */

export type TeamCountry = 'EGY' | 'UAE';

type CountryAlias = {
  business: string;
  routeId: string;
  sources: Record<TeamCountry, readonly string[]>;
};

const COUNTRY_ALIASES: readonly CountryAlias[] = [
  {
    business: 'Coding',
    routeId: 'coding',
    sources: { EGY: ['Coding EGY'], UAE: ['Coding'] },
  },
  {
    business: 'Submission',
    routeId: 'submission',
    sources: { EGY: ['Submission EGY'], UAE: ['Submission'] },
  },
  {
    business: 'Re-Submission',
    routeId: 're-submission',
    sources: { EGY: ['Resubmission', 'Re-Submission EGY'], UAE: ['Re-Submission'] },
  },
];

const LEGACY_ROUTES: Record<string, { routeId: string; region: TeamCountry }> = {
  'coding-egy': { routeId: 'coding', region: 'EGY' },
  'submission-egy': { routeId: 'submission', region: 'EGY' },
  resubmission: { routeId: 're-submission', region: 'EGY' },
  're-submission-egy': { routeId: 're-submission', region: 'EGY' },
};

const exactKey = (value: string | null | undefined) =>
  String(value ?? '').trim().toLowerCase().replace(/\s+/g, ' ');

export const EGYPT_RESUBMISSION_TEAM_ALIASES = ['Resubmission', 'Re-Submission EGY'] as const;

export function isEgyptResubmissionTeam(value: string | null | undefined): boolean {
  const key = exactKey(value);
  return key === 'resubmission' || key === 're-submission egy';
}

export function canonicalEgyptResubmissionTeam(value: string | null | undefined): string {
  return isEgyptResubmissionTeam(value) ? 'Resubmission' : String(value ?? '').trim();
}

export function dedupeEgyptResubmissionRecords<T>(
  records: readonly T[],
  getIdentity: (record: T) => {
    team?: string | null;
    employeeId?: string | null;
    periodKey?: string | null;
    year?: number | string | null;
    month?: string | null;
    level?: string | null;
  } = (record: T) => {
    const anyRec = record as Record<string, unknown>;
    const identity = (anyRec.identity ?? {}) as Record<string, unknown>;
    const period = (anyRec.period ?? {}) as Record<string, unknown>;
    return {
      team: String(anyRec.team ?? identity.team ?? ''),
      employeeId: String(anyRec.employeeId ?? anyRec.employee_id ?? identity.employee_id ?? identity.name ?? ''),
      periodKey: typeof period.key === 'string' ? period.key : undefined,
      year: (anyRec.year ?? period.year) as number | string | null | undefined,
      month: String(anyRec.month ?? period.month ?? identity.month ?? ''),
      level: String(anyRec.level ?? anyRec.performance_level ?? 'Employee'),
    };
  },
): T[] {
  // Upload status and timestamps are only available on the server. Never let
  // array ordering choose between conflicting records in a client projection.
  void getIdentity;
  return [...records];
}

export function parseTeamCountry(value: string | null | undefined): TeamCountry | null {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'egy' || raw === 'egypt') return 'EGY';
  if (raw === 'uae' || raw === 'united arab emirates') return 'UAE';
  return null;
}

function aliasByIdentity(name: string | null | undefined): { alias: CountryAlias; country: TeamCountry } | null {
  const raw = String(name ?? '').trim();
  if (!raw || COUNTRY_ALIASES.some((alias) => alias.routeId === raw.toLowerCase() && raw === raw.toLowerCase())) {
    return null;
  }
  const key = exactKey(raw);
  if (!key) return null;
  const legacy = LEGACY_ROUTES[key];
  if (legacy) {
    const alias = COUNTRY_ALIASES.find((item) => item.routeId === legacy.routeId);
    if (alias) return { alias, country: legacy.region };
  }
  for (const alias of COUNTRY_ALIASES) {
    for (const country of ['EGY', 'UAE'] as const) {
      if (alias.sources[country].some((source) => exactKey(source) === key)) {
        return { alias, country };
      }
    }
  }
  return null;
}

function aliasByBusiness(name: string | null | undefined): CountryAlias | null {
  const key = exactKey(name);
  const route = String(name ?? '').trim().toLowerCase();
  return COUNTRY_ALIASES.find((alias) => alias.routeId === route || exactKey(alias.business) === key) ?? null;
}

/** Business name. Stored source names such as "Coding EGY" stay out of the label. */
export function businessTeamName(name: string | null | undefined): string {
  return aliasByIdentity(name)?.alias.business ?? aliasByBusiness(name)?.business ?? String(name ?? '').trim();
}

/** Country implied by a stored source name. A bare business name is not a country. */
export function countryForStoredTeam(name: string | null | undefined): TeamCountry | null {
  return aliasByIdentity(name)?.country ?? null;
}

export function sourceNamesFor(name: string | null | undefined, country: TeamCountry): readonly string[] {
  const alias = aliasByIdentity(name)?.alias ?? aliasByBusiness(name);
  return alias ? alias.sources[country] : [];
}

export function sameCountryBusinessTeam(
  left: string | null | undefined,
  right: string | null | undefined,
  country: TeamCountry,
): boolean {
  const leftBusiness = businessTeamName(left);
  const rightBusiness = businessTeamName(right);
  if (leftBusiness && leftBusiness === rightBusiness && aliasByBusiness(leftBusiness)) {
    const leftCountry = countryForStoredTeam(left);
    const rightCountry = countryForStoredTeam(right);
    return (leftCountry === null || leftCountry === country) && (rightCountry === null || rightCountry === country);
  }
  return exactKey(left) !== '' && exactKey(left) === exactKey(right);
}

/** Route for a stored source name, including the country that name belongs to. */
export function sharedTeamRoute(name: string | null | undefined): { routeId: string; region: TeamCountry } | null {
  const found = aliasByIdentity(name);
  if (!found) return null;
  return { routeId: found.alias.routeId, region: found.country };
}

/** Old country-suffixed URLs. /team/coding itself stays the UAE Coding page. */
export function legacySharedTeamRedirect(routeId: string | null | undefined): { routeId: string; region: TeamCountry } | null {
  return LEGACY_ROUTES[String(routeId ?? '').trim().toLowerCase()] ?? null;
}

/**
 * Country for a shared route. A locked role wins over the URL. /team/coding with
 * no region remains UAE, which is what that URL meant before the shared route.
 */
export function countryForSharedRoute(
  routeId: string | null | undefined,
  urlRegion: string | null | undefined,
  lockedRegion?: string | null,
): TeamCountry | null {
  if (!aliasByBusiness(routeId)) return null;
  return parseTeamCountry(lockedRegion) ?? parseTeamCountry(urlRegion) ?? 'UAE';
}

/** Label for a list that may contain both countries of one business team. */
export function sidebarTeamLabel(name: string, siblings: readonly string[]): string {
  const business = businessTeamName(name);
  const country = countryForStoredTeam(name);
  const shared = siblings.filter((other) => businessTeamName(other) === business).length > 1;
  if (shared && country) return `${business} · ${country === 'EGY' ? 'Egypt' : 'UAE'}`;
  return business;
}

/** Business name. The country stays in the region filter, not in the label. */
export function presentationTeamName(name: string, _region?: string | null): string {
  // Some callers still pass the current filter; labels are country-independent.
  void _region;
  return businessTeamName(name);
}

export function distinctCatalogTeams<T extends { team: string; performance_levels?: string[] }>(
  teams: readonly T[],
  country: TeamCountry,
): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  for (const team of teams) {
    const sources = sourceNamesFor(team.team, country);
    const level = (team.performance_levels ?? ['Employee']).map((item) => item.toLowerCase()).sort().join(',');
    const key = sources.length
      ? `alias:${exactKey(businessTeamName(team.team))}:${country}:${level}`
      : `raw:${exactKey(team.team)}:${level}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(team);
  }
  return result;
}

export function recordMatchesCatalogTeam(input: {
  recordTeam: string;
  recordRegion?: string | null;
  recordLevel?: string | null;
  catalogTeam: string;
  catalogRegion?: string | null;
  levels?: string[];
}): boolean {
  const recordCountry = parseTeamCountry(input.recordRegion);
  const catalogCountry = parseTeamCountry(input.catalogRegion);
  if (recordCountry && catalogCountry && recordCountry !== catalogCountry) return false;
  const levels = input.levels ?? ['Employee'];
  const level = String(input.recordLevel || 'Employee').toLowerCase();
  if (!levels.some((item) => item.toLowerCase() === level)) return false;
  const country = catalogCountry ?? recordCountry;
  if (country && sourceNamesFor(input.catalogTeam, country).length) {
    return sameCountryBusinessTeam(input.recordTeam, input.catalogTeam, country);
  }
  return exactKey(input.recordTeam) === exactKey(input.catalogTeam);
}
