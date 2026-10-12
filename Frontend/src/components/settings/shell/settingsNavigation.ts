import type { SettingsSection } from '../types';

/** Every page the shell renders. Each one has a URL slug, including the Access section `teams`. */
export type SettingsRoutePage = 'overview' | SettingsSection;

export type SettingsPage = SettingsRoutePage;

const PAGE_SLUGS: Record<SettingsRoutePage, string> = {
  overview: 'overview',
  upload: 'data',
  corrective_actions: 'corrective-actions',
  kpis: 'evaluation',
  users: 'users',
  teams: 'teams',
  system_errors: 'system-errors',
};

const SLUG_PAGES = new Map<string, SettingsRoutePage>(
  (Object.entries(PAGE_SLUGS) as Array<[SettingsRoutePage, string]>).map(([page, slug]) => [slug, page]),
);

/** Search shortcuts such as `/settings?tab=users` predate the URL sections and must keep landing on their section. */
const LEGACY_TABS = new Map<string, SettingsRoutePage>([
  ['upload', 'upload'],
  ['corrective_actions', 'corrective_actions'],
  ['kpis', 'kpis'],
  ['users', 'users'],
  ['system_errors', 'system_errors'],
]);

export function settingsPathFor(page: SettingsRoutePage): string {
  return `/settings/${PAGE_SLUGS[page]}`;
}

/** Returns null for an unknown or missing slug. */
export function pageForSlug(slug: string | undefined): SettingsPage | null {
  if (slug === undefined) return null;
  return SLUG_PAGES.get(slug) ?? null;
}

export function pageForLegacyTab(tab: string | null): SettingsRoutePage | null {
  if (tab === null) return null;
  return LEGACY_TABS.get(tab) ?? null;
}
