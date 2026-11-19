import { describe, expect, it } from 'vitest';
import { pageForLegacyTab, pageForSlug, settingsPathFor } from './settingsNavigation';

describe('settings slugs', () => {
  it('maps every URL slug to its existing section id', () => {
    expect(pageForSlug('overview')).toBe('overview');
    expect(pageForSlug('data')).toBe('upload');
    expect(pageForSlug('corrective-actions')).toBe('corrective_actions');
    expect(pageForSlug('evaluation')).toBe('kpis');
    expect(pageForSlug('users')).toBe('users');
    expect(pageForSlug('system-errors')).toBe('system_errors');
    expect(pageForSlug('ai-feedback')).toBe('ai_feedback');
    expect(pageForSlug('ai-models')).toBe('ai_models');
  });

  it('gives no page for a missing or unknown slug', () => {
    expect(pageForSlug(undefined)).toBeNull();
    expect(pageForSlug('')).toBeNull();
    expect(pageForSlug('teams')).toBeNull();
    expect(pageForSlug('constructor')).toBeNull();
  });

  it('builds the path for each navigable page', () => {
    expect(settingsPathFor('overview')).toBe('/settings/overview');
    expect(settingsPathFor('kpis')).toBe('/settings/evaluation');
    expect(settingsPathFor('upload')).toBe('/settings/data');
    expect(settingsPathFor('ai_feedback')).toBe('/settings/ai-feedback');
    expect(settingsPathFor('ai_models')).toBe('/settings/ai-models');
  });

  it('maps the legacy tab shortcuts to their sections and ignores anything else', () => {
    expect(pageForLegacyTab('upload')).toBe('upload');
    expect(pageForLegacyTab('users')).toBe('users');
    expect(pageForLegacyTab('corrective_actions')).toBe('corrective_actions');
    expect(pageForLegacyTab('ai_feedback')).toBe('ai_feedback');
    expect(pageForLegacyTab('ai_models')).toBe('ai_models');
    expect(pageForLegacyTab('teams')).toBeNull();
    expect(pageForLegacyTab('unknown')).toBeNull();
    expect(pageForLegacyTab(null)).toBeNull();
  });
});
