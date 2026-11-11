import { describe, expect, it } from 'vitest';
import { buildFallbackStarterPrompts } from './starterPrompts';

describe('buildFallbackStarterPrompts', () => {
  it('does not fall back to Call Center wording when no function is selected', () => {
    const prompts = buildFallbackStarterPrompts({ functionName: null, team: null, branch: null });
    const text = prompts.map((item) => `${item.label} ${item.prompt}`).join('\n');
    expect(text).toContain('All authorized departments');
    expect(text).not.toMatch(/call center/i);
    expect(text).not.toMatch(/UAE/i);
  });

  it('uses the active function instead of Call Center', () => {
    const prompts = buildFallbackStarterPrompts({ functionName: 'Pharmacy', team: null, branch: null });
    expect(prompts[0]?.label).toBe('Which team in Pharmacy dropped most?');
    expect(prompts.map((item) => item.prompt).join(' ')).not.toMatch(/call center/i);
  });

  it('keeps Call Center prompts when that function is selected', () => {
    const prompts = buildFallbackStarterPrompts({ functionName: 'Call Center', team: null, branch: null });
    expect(prompts.some((item) => item.label === 'Which Call Center team dropped most?')).toBe(true);
  });
});
