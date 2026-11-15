import { describe, expect, it } from 'vitest';
import { buildFallbackStarterPrompts, mergeStarterScenarios } from './starterPrompts';

describe('buildFallbackStarterPrompts', () => {
  it('does not fall back to Call Center wording when no function is selected', () => {
    const prompts = buildFallbackStarterPrompts({ functionName: null, team: null, branch: null });
    expect(prompts).toHaveLength(10);
    const categories = new Set(prompts.map((item) => item.category));
    expect(categories).toEqual(new Set(['team', 'people', 'branch', 'kpi', 'governance']));
    const text = prompts.map((item) => `${item.label} ${item.subtitle ?? ''} ${item.prompt}`).join('\n');
    expect(text).toContain('All authorized departments');
    expect(text).not.toMatch(/call center/i);
    expect(text).not.toMatch(/UAE/i);
  });

  it('uses the active function instead of Call Center', () => {
    const prompts = buildFallbackStarterPrompts({ functionName: 'Pharmacy', team: null, branch: null });
    expect(prompts[0]?.label).toBe('Which team in Pharmacy dropped most?');
    expect(prompts.map((item) => item.prompt).join(' ')).not.toMatch(/call center/i);
  });

  it('keeps Call Center prompts when that function is selected and tailors KPI cards by team without fake percentages', () => {
    const ccDefault = buildFallbackStarterPrompts({ functionName: 'Call Center', team: null, branch: null });
    expect(ccDefault).toHaveLength(10);
    expect(ccDefault.some((item) => item.label === 'Which Call Center team dropped most?')).toBe(true);
    const ccText = ccDefault.map((item) => `${item.label} ${item.subtitle ?? ''}`).join(' ');
    expect(ccText).not.toContain('100%');
    expect(ccText).not.toContain('56.6%');

    const inbound = buildFallbackStarterPrompts({ functionName: 'Call Center', team: 'Inbound', branch: null });
    expect(inbound.some((item) => item.id === 'inbound-kpi-decisions')).toBe(true);

    const support = buildFallbackStarterPrompts({ functionName: 'Call Center', team: 'Support Positions', branch: null });
    expect(support.some((item) => item.id === 'support-kpi-decisions')).toBe(true);
    const supportText = support.map((item) => `${item.label} ${item.subtitle ?? ''} ${item.prompt}`).join(' ');
    expect(supportText).not.toMatch(/UAE|Dubai|Sharjah|Ajman|Clinics/i);
    expect(supportText).not.toMatch(/Attendance gap/i);

    const egyCc = buildFallbackStarterPrompts({ functionName: 'Call Center', team: null, branch: null, region: 'EGY' });
    expect(egyCc).toHaveLength(10);
    const egyText = egyCc.map((item) => `${item.label} ${item.subtitle ?? ''} ${item.prompt}`).join(' ');
    expect(egyText).not.toMatch(/UAE|Dubai|Sharjah|Ajman|Clinics/i);
  });

  it('merges server and fallback prompts so every category has at least 2 entries', () => {
    const fallback = buildFallbackStarterPrompts({ functionName: 'Call Center', team: 'Inbound' });
    const serverOnlyTwo = fallback.slice(0, 2);
    const merged = mergeStarterScenarios(serverOnlyTwo, fallback);
    for (const cat of ['team', 'people', 'branch', 'kpi', 'governance'] as const) {
      expect(merged.filter((item) => item.category === cat).length).toBeGreaterThanOrEqual(2);
    }
  });
});
