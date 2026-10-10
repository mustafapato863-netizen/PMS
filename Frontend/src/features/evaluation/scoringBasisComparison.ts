/**
 * Client-side mirror of Backend/services/scoring_basis_comparison.py.
 * It reads pinned KPI rows already on the records in hand. It does not fetch
 * another month or treat a version id as evidence that the rules changed.
 */

export type BasisState = 'unchanged' | 'changed' | 'mixed' | 'unknown' | 'unavailable';
export type BasisRaw = 'unchanged' | 'changed' | 'not_comparable' | 'unknown' | 'partial';
export type BasisMembership = 'stable' | 'changed' | 'none' | 'unknown';

export interface BasisComparisonContext {
  state: BasisState;
  like_for_like: boolean;
  raw_performance: BasisRaw;
  membership: BasisMembership;
  reasons: string[];
  message: string | null;
}

export interface BasisKpi {
  kpi_key?: string | null;
  key?: string | null;
  target_value?: unknown;
  target?: unknown;
  weight_applied?: unknown;
  weight?: unknown;
  weight_pct?: unknown;
  direction?: unknown;
  unit?: unknown;
  actual_value?: unknown;
  actual?: unknown;
  evaluation_pinned?: unknown;
  source?: unknown;
  target_source?: unknown;
  achievement_source?: unknown;
  formula?: unknown;
  score_formula?: unknown;
  aggregation?: unknown;
  [key: string]: unknown;
}

export interface BasisRecord {
  employee_id?: string | null;
  employeeId?: string | null;
  team?: string | null;
  position?: string | null;
  performance_level?: string | null;
  level?: string | null;
  year?: number | null;
  month?: string | null;
  kpi_values?: BasisKpi[] | null;
  kpis?: BasisKpi[] | null;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const SETTINGS = 'Scores can be affected by evaluation settings.';
const FULL_UNCHANGED = 'Comparable raw performance is unchanged.';
const FULL_CHANGED = 'Comparable raw performance changed.';
const SHARED_UNCHANGED = 'Shared comparable KPI values are unchanged.';
const SHARED_CHANGED = 'Shared comparable KPI values changed.';
const RAW_UNAVAILABLE = 'Comparable raw performance is not available.';
const PARTIAL = 'Some KPI actuals are not comparable.';
const MEMBERSHIP = 'The compared employee population changed, so this score movement is not a matched-cohort comparison.';
const UNIDENTIFIED = 'Some records have no employee identity, so raw performance is not confirmed for a matched cohort.';
const UNKNOWN = 'Evaluation settings for this comparison are unavailable, so this score movement is not confirmed as like-for-like.';
const UNAVAILABLE = 'Evaluation settings comparison is unavailable for the exact previous month.';
const NO_SCOPE = 'The compared populations do not share a team, position, and level, so this score movement is not confirmed as like-for-like.';
const MIXED = `Evaluation settings are mixed in this comparison, so scores are not like-for-like. ${SETTINGS}`;
const DIRECTION_ALIASES: Record<string, 'higher_better' | 'lower_better'> = {
  higher_better: 'higher_better', higher_is_better: 'higher_better', higher: 'higher_better', high: 'higher_better',
  increase: 'higher_better', max: 'higher_better', maximize: 'higher_better', up: 'higher_better', asc: 'higher_better',
  lower_better: 'lower_better', lower_is_better: 'lower_better', lower: 'lower_better', low: 'lower_better',
  decrease: 'lower_better', min: 'lower_better', minimize: 'lower_better', down: 'lower_better', desc: 'lower_better', inverse: 'lower_better',
};

type Rule = [string, string, string, string, string, string | null, string | null, string | null];
type ActualMap = Map<string, Map<string, string | null>>;

function text(value: unknown): string {
  return String(value ?? '').trim();
}

function present(row: BasisKpi, name: string): boolean {
  return Object.prototype.hasOwnProperty.call(row, name) && row[name] != null;
}

function canonicalDecimal(value: unknown): string | null {
  if (typeof value === 'boolean' || value == null) return null;
  if (typeof value === 'number') {
    if (Object.is(value, -0)) return '0';
    if (!Number.isFinite(value)) return null;
    return expandDecimal(String(value));
  }
  if (typeof value !== 'string') return null;
  return expandDecimal(value);
}

/** Plain decimal form. 1e-7 and 0.0000001 match; 0.65 and 65 do not. -0 is 0. */
function expandDecimal(value: string): string | null {
  const match = /^([+-])?(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(value.trim());
  if (!match) return null;
  const negative = match[1] === '-';
  const exponent = match[5] ? Number(match[5]) : 0;
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 10000) return null;
  const fractionPart = match[4] != null ? match[4] : (match[3] ?? '');
  let digits = `${match[2] ?? ''}${fractionPart}`.replace(/^0+/, '');
  if (!digits) return '0';
  const scale = fractionPart.length - exponent;
  let body: string;
  if (scale > 0) {
    if (digits.length <= scale) digits = digits.padStart(scale + 1, '0');
    const whole = digits.slice(0, digits.length - scale).replace(/^0+(?=\d)/, '') || '0';
    const fraction = digits.slice(digits.length - scale).replace(/0+$/, '');
    body = fraction ? `${whole}.${fraction}` : whole;
  } else {
    body = `${digits}${'0'.repeat(-scale)}`.replace(/^0+(?=\d)/, '') || '0';
  }
  if (body === '0') return '0';
  return negative ? `-${body}` : body;
}

function normalizeDirection(value: unknown): 'higher_better' | 'lower_better' | null {
  if (value == null) return null;
  const normalized = String(value).trim().toLowerCase().replace(/-/g, ' ').split(/\s+/).join('_');
  return DIRECTION_ALIASES[normalized] ?? null;
}

function explicitToken(row: BasisKpi, names: string[]): string | null {
  const found = names.filter((name) => present(row, name)).map((name) => [name, text(row[name])]);
  return found.length ? JSON.stringify(found) : null;
}

function numberField(row: BasisKpi, names: string[]): string | null {
  for (const name of names) {
    if (present(row, name)) return canonicalDecimal(row[name]);
  }
  return null;
}

function rowsOf(record: BasisRecord): BasisKpi[] {
  return record.kpi_values ?? record.kpis ?? [];
}

function parseRule(row: BasisKpi): { rule: Rule; actual: string | null } | null {
  if (row.evaluation_pinned !== true) return null;
  const key = text(row.kpi_key || row.key).toLowerCase();
  const direction = normalizeDirection(row.direction);
  const unit = text(row.unit).toLowerCase();
  const target = numberField(row, ['target_value', 'target']);
  const weight = numberField(row, ['weight_applied', 'weight', 'weight_pct']);
  if (!key || (direction !== 'higher_better' && direction !== 'lower_better') || !unit || target == null || weight == null) return null;
  return {
    rule: [key, target, weight, direction, unit, explicitToken(row, ['source', 'target_source', 'achievement_source']), explicitToken(row, ['formula', 'score_formula']), explicitToken(row, ['aggregation'])],
    actual: numberField(row, ['actual_value', 'actual']),
  };
}

function recordRules(record: BasisRecord): { status: 'uniform' | 'mixed' | 'unknown'; rules: Rule[] | null; actuals: Map<string, string | null> | null } {
  const rows = rowsOf(record);
  if (!rows.length) return { status: 'unknown', rules: null, actuals: null };
  const byKey = new Map<string, Rule>();
  const actuals = new Map<string, string | null>();
  for (const row of rows) {
    const parsed = parseRule(row);
    if (!parsed) return { status: 'unknown', rules: null, actuals: null };
    const previous = byKey.get(parsed.rule[0]);
    if (previous && previous.join('\u0000') !== parsed.rule.join('\u0000')) return { status: 'mixed', rules: null, actuals: null };
    byKey.set(parsed.rule[0], parsed.rule);
    if (actuals.has(parsed.rule[0]) && actuals.get(parsed.rule[0]) !== parsed.actual) actuals.set(parsed.rule[0], null);
    else actuals.set(parsed.rule[0], parsed.actual);
  }
  return { status: 'uniform', rules: [...byKey.values()].sort((left, right) => left[0].localeCompare(right[0])), actuals };
}

function employeeId(record: BasisRecord): string | null {
  return text(record.employee_id || record.employeeId) || null;
}

function scopeKey(record: BasisRecord): string {
  return [text(record.team), text(record.position), text(record.performance_level || record.level)].join('\u0000');
}

function trustedScope(record: BasisRecord): boolean {
  return Boolean(text(record.team) && text(record.performance_level || record.level));
}

function groupRecords(rows: BasisRecord[]): { groups: Map<string, BasisRecord[]>; untrusted: boolean } {
  const groups = new Map<string, BasisRecord[]>();
  let untrusted = false;
  rows.forEach((record) => {
    if (!trustedScope(record)) {
      untrusted = true;
      return;
    }
    const key = scopeKey(record);
    const bucket = groups.get(key);
    if (bucket) bucket.push(record);
    else groups.set(key, [record]);
  });
  return { groups, untrusted };
}

function sliceRules(records: BasisRecord[]): { status: string; rules: Rule[] | null; actuals: ActualMap; unidentified: boolean } {
  if (!records.length) return { status: 'empty', rules: null, actuals: new Map(), unidentified: false };
  const actuals: ActualMap = new Map();
  let signature: string | null = null;
  let rules: Rule[] | null = null;
  let unidentified = false;
  for (const record of records) {
    const parsed = recordRules(record);
    if (parsed.status !== 'uniform' || !parsed.rules || !parsed.actuals) {
      return { status: parsed.status, rules: null, actuals: new Map(), unidentified: true };
    }
    const encoded = parsed.rules.map((rule) => rule.join('\u0000')).join('\u0001');
    if (signature == null) {
      signature = encoded;
      rules = parsed.rules;
    } else if (signature !== encoded) {
      return { status: 'mixed', rules: null, actuals: new Map(), unidentified: true };
    }
    const id = employeeId(record);
    if (!id) {
      unidentified = true;
      continue;
    }
    const current = actuals.get(id) ?? new Map<string, string | null>();
    parsed.actuals.forEach((actual, key) => {
      if (current.has(key) && current.get(key) !== actual) current.set(key, null);
      else if (!current.has(key)) current.set(key, actual);
    });
    actuals.set(id, current);
  }
  return { status: 'uniform', rules, actuals, unidentified };
}

function ruleMap(rules: Rule[] | null): Map<string, Rule> {
  return new Map((rules ?? []).map((rule) => [rule[0], rule]));
}

function reasonsOf(left: Rule[], right: Rule[]): { reasons: string[]; unknownOptional: boolean } {
  const before = ruleMap(left);
  const after = ruleMap(right);
  const reasons: string[] = [];
  let unknownOptional = false;
  const beforeKeys = new Set(before.keys());
  const afterKeys = new Set(after.keys());
  if ([...beforeKeys].sort().join() !== [...afterKeys].sort().join()) reasons.push('kpi_set');
  const labels = ['target', 'weight', 'direction', 'unit', 'source', 'formula', 'aggregation'] as const;
  for (const key of beforeKeys) {
    if (!after.has(key)) continue;
    const leftRule = before.get(key)!;
    const rightRule = after.get(key)!;
    labels.forEach((label, index) => {
      const leftValue = leftRule[index + 1];
      const rightValue = rightRule[index + 1];
      if ((label === 'source' || label === 'formula' || label === 'aggregation') && (leftValue == null || rightValue == null)) {
        if (leftValue != null || rightValue != null) unknownOptional = true;
        return;
      }
      if (leftValue !== rightValue) reasons.push(label);
    });
  }
  return { reasons, unknownOptional };
}

function rawBetween(leftRules: Rule[] | null, leftActuals: ActualMap, rightRules: Rule[] | null, rightActuals: ActualMap): { status: BasisRaw; proven: 'unchanged' | 'changed' | null; kpiGap: boolean } {
  const before = ruleMap(leftRules);
  const after = ruleMap(rightRules);
  const sharedKeys = [...before.keys()].filter((key) => after.has(key));
  const sharedIds = [...leftActuals.keys()].filter((id) => rightActuals.has(id));
  let kpiGap = [...before.keys()].some((key) => !after.has(key)) || [...after.keys()].some((key) => !before.has(key));
  const proven: Array<'unchanged' | 'changed'> = [];
  let blocked = false;
  if (!sharedIds.length) return { status: 'unknown', proven: null, kpiGap };
  for (const key of sharedKeys) {
    const leftRule = before.get(key)!;
    const rightRule = after.get(key)!;
    const explicitDiffers = [5, 6, 7].some((index) => leftRule[index] != null && rightRule[index] != null && leftRule[index] !== rightRule[index]);
    if (leftRule[3] !== rightRule[3] || leftRule[4] !== rightRule[4] || explicitDiffers) {
      blocked = true;
      kpiGap = true;
      continue;
    }
    for (const id of sharedIds) {
      const leftMap = leftActuals.get(id);
      const rightMap = rightActuals.get(id);
      const left = leftMap?.get(key);
      const right = rightMap?.get(key);
      if (!leftMap?.has(key) || !rightMap?.has(key) || left == null || right == null) {
        kpiGap = true;
        continue;
      }
      proven.push(left === right ? 'unchanged' : 'changed');
    }
  }
  const note = proven.includes('changed') ? 'changed' : proven.length ? 'unchanged' : null;
  if (proven.length && (blocked || kpiGap)) return { status: 'partial', proven: note, kpiGap: true };
  if (proven.includes('changed')) return { status: 'changed', proven: 'changed', kpiGap: false };
  if (proven.length) return { status: 'unchanged', proven: 'unchanged', kpiGap: false };
  if (blocked) return { status: 'not_comparable', proven: null, kpiGap: true };
  return { status: 'unknown', proven: null, kpiGap };
}

function messageFor(state: BasisState, raw: BasisRaw, membership: BasisMembership, proven: 'unchanged' | 'changed' | null, kpiGap: boolean): string | null {
  if (state === 'unavailable') return UNAVAILABLE;
  if (state === 'unknown') return membership === 'none' ? NO_SCOPE : UNKNOWN;
  if (state === 'unchanged' && membership === 'stable' && (raw === 'unchanged' || raw === 'changed')) return null;
  const parts: string[] = [];
  if (state === 'mixed') parts.push(MIXED);
  else if (state === 'changed') parts.push(SETTINGS);
  if (membership === 'changed') parts.push(MEMBERSHIP);
  else if (membership === 'unknown') parts.push(UNIDENTIFIED);
  if (raw === 'partial') {
    if (proven === 'unchanged') parts.push(SHARED_UNCHANGED);
    else if (proven === 'changed') parts.push(SHARED_CHANGED);
    if (kpiGap) parts.push(PARTIAL);
  } else if (raw === 'unchanged' && state !== 'unchanged') parts.push(FULL_UNCHANGED);
  else if (raw === 'changed' && state !== 'unchanged') parts.push(FULL_CHANGED);
  else if (raw === 'not_comparable' || raw === 'unknown') parts.push(RAW_UNAVAILABLE);
  return parts.join(' ') || null;
}

function context(
  state: BasisState,
  raw: BasisRaw,
  reasons: string[],
  membership: BasisMembership,
  proven: 'unchanged' | 'changed' | null = null,
  kpiGap = false,
): BasisComparisonContext {
  let nextRaw = raw;
  let nextProven = proven;
  if (state === 'unknown' || state === 'unavailable') {
    nextRaw = 'unknown';
    nextProven = null;
    kpiGap = false;
  }
  if (state === 'mixed') {
    nextRaw = 'not_comparable';
    nextProven = null;
  }
  if ((membership === 'changed' || membership === 'unknown') && state !== 'unknown' && state !== 'unavailable' && state !== 'mixed' && (nextRaw === 'unchanged' || nextRaw === 'changed')) {
    nextProven = nextProven ?? nextRaw;
    nextRaw = 'partial';
  }
  return {
    state,
    like_for_like: state === 'unchanged' && membership === 'stable' && (nextRaw === 'unchanged' || nextRaw === 'changed'),
    raw_performance: nextRaw,
    membership: state === 'unavailable' ? 'none' : membership,
    reasons: state === 'changed' ? [...new Set(reasons)].sort() : [],
    message: messageFor(state, nextRaw, membership, nextProven, kpiGap),
  };
}

export function compareScoringBasis(current: BasisRecord[] | null | undefined, previous: BasisRecord[] | null | undefined): BasisComparisonContext {
  const currentRows = current ?? [];
  const previousRows = previous ?? [];
  if (!currentRows.length || !previousRows.length) return context('unavailable', 'unknown', [], 'none');
  const currentGrouped = groupRecords(currentRows);
  const previousGrouped = groupRecords(previousRows);
  const currentGroups = currentGrouped.groups;
  const previousGroups = previousGrouped.groups;
  const shared = [...currentGroups.keys()].filter((key) => previousGroups.has(key)).sort();
  const oneSided = [...currentGroups.keys()].some((key) => !previousGroups.has(key)) || [...previousGroups.keys()].some((key) => !currentGroups.has(key));
  const untrusted = currentGrouped.untrusted || previousGrouped.untrusted;
  if (!shared.length) return context('unknown', 'unknown', [], 'none');
  const coverageGap = oneSided || untrusted;
  const states: BasisState[] = [];
  const raws: Array<{ status: BasisRaw; proven: 'unchanged' | 'changed' | null; kpiGap: boolean }> = [];
  const memberships: BasisMembership[] = [];
  const reasons: string[] = [];
  for (const key of shared) {
    const currentSlice = sliceRules(currentGroups.get(key) ?? []);
    const previousSlice = sliceRules(previousGroups.get(key) ?? []);
    if (currentSlice.status === 'unknown' || previousSlice.status === 'unknown') {
      states.push('unknown');
      raws.push({ status: 'unknown', proven: null, kpiGap: false });
      memberships.push('stable');
      continue;
    }
    if (currentSlice.status === 'mixed' || previousSlice.status === 'mixed') {
      states.push('mixed');
      raws.push({ status: 'not_comparable', proven: null, kpiGap: true });
      memberships.push('stable');
      continue;
    }
    const difference = reasonsOf(previousSlice.rules ?? [], currentSlice.rules ?? []);
    if (difference.unknownOptional && difference.reasons.length) states.push('mixed');
    else if (difference.unknownOptional) states.push('unknown');
    else {
      states.push(difference.reasons.length ? 'changed' : 'unchanged');
      reasons.push(...difference.reasons);
    }
    const currentIds = new Set(currentSlice.actuals.keys());
    const previousIds = new Set(previousSlice.actuals.keys());
    const sameIds = currentIds.size === previousIds.size && [...currentIds].every((id) => previousIds.has(id));
    if (currentSlice.unidentified || previousSlice.unidentified) memberships.push('unknown');
    else if (!sameIds) memberships.push('changed');
    else memberships.push('stable');
    raws.push(rawBetween(currentSlice.rules, currentSlice.actuals, previousSlice.rules, previousSlice.actuals));
  }
  if (coverageGap) memberships.push('changed');
  const state: BasisState = states.some((item) => item === 'changed') && states.some((item) => item === 'unknown' || item === 'mixed')
    ? 'mixed'
    : states.includes('unknown') ? 'unknown' : states.includes('mixed') ? 'mixed' : states.includes('changed') ? 'changed' : 'unchanged';
  const notes = raws.map((item) => item.proven).filter((item): item is 'unchanged' | 'changed' => Boolean(item));
  const statuses = raws.map((item) => item.status);
  const kpiGap = raws.some((item) => item.kpiGap) || statuses.some((item) => item === 'partial' || item === 'not_comparable' || item === 'unknown');
  const proven = notes.includes('changed') ? 'changed' : notes.includes('unchanged') ? 'unchanged' : null;
  let raw: BasisRaw;
  let rawProven: 'unchanged' | 'changed' | null = null;
  let rawGap = false;
  if (state === 'unknown') {
    raw = 'unknown';
  } else if (state === 'mixed') {
    raw = 'not_comparable';
  } else if (statuses.some((item) => item === 'partial') || (proven && statuses.some((item) => item === 'unknown' || item === 'not_comparable'))) {
    raw = 'partial';
    rawProven = proven;
    rawGap = true;
  } else if (statuses.includes('changed')) {
    raw = 'changed';
    rawProven = 'changed';
  } else if (statuses.length && statuses.every((item) => item === 'unchanged')) {
    raw = 'unchanged';
    rawProven = 'unchanged';
  } else if (statuses.includes('not_comparable')) {
    raw = 'not_comparable';
    rawGap = true;
  } else {
    raw = 'unknown';
    rawGap = kpiGap;
  }
  if (coverageGap) rawGap = true;
  const membership: BasisMembership = memberships.includes('changed') ? 'changed' : memberships.includes('unknown') ? 'unknown' : 'stable';
  return context(state, raw, reasons, membership, rawProven, rawGap);
}

export function previousCalendarMonth(year: number, month: string): { year: number; month: string } | null {
  const index = MONTHS.indexOf(month);
  if (index < 0) return null;
  if (index === 0) return { year: year - 1, month: MONTHS[11] };
  return { year, month: MONTHS[index - 1] };
}

export function dedupeBasisMessages(messages: Array<string | null | undefined>): string[] {
  const unique: string[] = [];
  messages.forEach((message) => {
    const value = message?.trim();
    if (value && !unique.includes(value)) unique.push(value);
  });
  return unique;
}
