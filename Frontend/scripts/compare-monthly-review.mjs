// Offline parity check. Only aggregate findings are written to stdout.
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';

const input = JSON.parse(readFileSync(0, 'utf8'));
const server = await createServer({
  configFile: false,
  logLevel: 'silent',
  server: { middlewareMode: true, hmr: false, watch: null },
  appType: 'custom',
});
try {
  const { mapScopedPerformanceRecord } = await server.ssrLoadModule('/src/hooks/usePerformanceData.ts');
  const { toExecRecords } = await server.ssrLoadModule('/src/features/executive/compose.ts');
  const deck = await server.ssrLoadModule('/src/features/monthlyPresentation/teamDeepDiveData.ts');
  const functions = await server.ssrLoadModule('/src/features/monthlyPresentation/callCenterDeepDiveData.ts');
  const { executiveFunctionForTeam } = await server.ssrLoadModule('/src/features/executive/functions.ts');
  const { TeamConfigSchema } = await server.ssrLoadModule('/src/schemas/teamConfig.schema.ts');
  const records = toExecRecords(input.records.map(mapScopedPerformanceRecord));
  const comparisons = [];
  for (const cell of input.cells) {
    const scoped = records.filter(row => row.level === cell.level);
    let official = null;
    let basis = null;
    if (cell.entity === 'team') {
      const view = deck.buildTeamDeepDiveFromRecords(cell.name, scoped, [], cell.region, cell.period);
      if (view.periodKey === cell.period && view.scoringRecords?.some(row => row.period.key === cell.period)) {
        const config = input.configs[deck.selectedTeamConfigSource(view)];
        const parsed = config && TeamConfigSchema.safeParse(config);
        const resolved = parsed?.data ?? deck.defaultTeamTrendConfig(view);
        const applied = resolved ? deck.applyTeamTrendConfig(view, resolved) : deck.unavailableTeamTrend(view);
        const point = applied.scoreTrend?.points.find(p => p.periodKey === cell.period);
        official = point?.score ?? null;
        basis = parsed?.success === false ? 'Configuration rejected by Monthly Review' : point?.basisDetail ?? null;
      }
    } else {
      const slug = functions.normalizeFunctionSlug(cell.name);
      const hasRecords = functions.scopeRecordsToRegion(scoped, cell.region).some(row => {
        const parent = executiveFunctionForTeam(row.team);
        return row.period.key === cell.period && (
          (parent && functions.normalizeFunctionSlug(parent) === slug)
          || functions.normalizeFunctionSlug(row.team) === slug
        );
      });
      if (hasRecords) {
        const view = functions.buildFunctionDeepDiveFromRecords(slug, scoped, [], cell.region, cell.period);
        const point = view.scoreTrend?.points.find(p => p.periodKey === cell.period && p.selected);
        if (!view.isEmpty && view.periodKey === cell.period) official = point?.score ?? null;
      }
    }
    comparisons.push({ ...cell, official, basis });
  }
  process.stdout.write(JSON.stringify(comparisons));
} finally {
  await server.close();
}
