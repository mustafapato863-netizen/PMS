import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { TeamConfigSchema } from './teamConfig.schema';

describe('published role scorecard configurations', () => {
  it.each(['pharmacy', 'finance'])('loads the configured measures for %s', (team) => {
    const file = join(process.cwd(), '..', 'Backend', 'config', 'teams', team + '.json');
    const source = JSON.parse(readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
    const result = TeamConfigSchema.parse(source);
    const measures = Object.values(result.performance_levels?.Employee?.positions ?? {}).flatMap(role => role.kpis);
    expect(measures.length).toBeGreaterThan(0);
    if (team === 'pharmacy') {
      expect(measures.find(kpi => kpi.label === 'Pharmacy Waiting Time')?.unit).toBe('min');
    }
  });
});
